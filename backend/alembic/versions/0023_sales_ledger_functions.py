"""Narrow, tenant-checked write paths for the append-only sales ledger.

``sanket_app`` holds only SELECT and INSERT on ``historical_sales`` (see
sql/003_rls_policies.sql): sales history is append-only for the application,
like ``audit_log``. Two operations still have to change stored rows, and both
are provably narrow, so they get SECURITY DEFINER functions instead of a
blanket UPDATE/DELETE grant:

* ``sanket_correct_sale`` — apply a corrected re-upload of one keyed sale. It
  only touches a row that is the *sole* holder of its ``record_key`` in the
  caller's tenant and never changes the key.
* ``sanket_dedupe_sales`` — list (dry run) or remove copies created by
  replayed imports. It only ever deletes rows that share a ``record_key`` with
  an identical copy, keeps one copy per group (lowest id in text order —
  deterministic; the copies are identical, so which one survives changes no
  total), and reports groups whose copies differ without touching them.

Both refuse to run without ``app.current_tenant_id`` and filter on it
explicitly, because a SECURITY DEFINER body is not subject to the caller's RLS.
Neither creates temporary objects: a definer body must not use anything the
caller could have pre-created in their own session.

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-26
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_SIGNATURE_CORRECT = (
    "sanket_correct_sale(uuid, timestamptz, text, timestamptz, text, text, text, "
    "integer, numeric, numeric, boolean, integer, jsonb)"
)
_SIGNATURE_DEDUPE = "sanket_dedupe_sales(industry_code, boolean)"

_CORRECT_SALE = r"""
CREATE OR REPLACE FUNCTION sanket_correct_sale(
    p_id            uuid,
    p_sale_time     timestamptz,
    p_record_key    text,
    p_new_sale_time timestamptz,
    p_channel       text,
    p_region        text,
    p_location      text,
    p_units         integer,
    p_gross         numeric,
    p_net           numeric,
    p_in_stock      boolean,
    p_returns       integer,
    p_metadata      jsonb
) RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_tenant  uuid := public.current_tenant_id();
    v_holders bigint;
    v_count   integer;
BEGIN
    IF v_tenant IS NULL THEN
        RAISE EXCEPTION 'sanket_correct_sale requires app.current_tenant_id';
    END IF;
    IF p_record_key IS NULL THEN
        RAISE EXCEPTION 'sanket_correct_sale only corrects keyed sales';
    END IF;

    SELECT count(*) INTO v_holders
      FROM public.historical_sales h
     WHERE h.tenant_id = v_tenant AND h.record_key = p_record_key;
    IF v_holders <> 1 THEN
        RETURN 0;  -- duplicate copies or a vanished row: not provably the same sale
    END IF;

    UPDATE public.historical_sales h
       SET sale_time     = p_new_sale_time,
           channel       = p_channel,
           region        = p_region,
           location      = p_location,
           units_sold    = p_units,
           gross_revenue = p_gross,
           net_revenue   = p_net,
           in_stock      = p_in_stock,
           returns       = p_returns,
           metadata      = p_metadata
     WHERE h.tenant_id  = v_tenant
       AND h.id         = p_id
       AND h.sale_time  = p_sale_time
       AND h.record_key = p_record_key;
    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$;
"""

_DEDUPE_SALES = r"""
CREATE OR REPLACE FUNCTION sanket_dedupe_sales(
    p_industry industry_code,
    p_dry_run  boolean DEFAULT TRUE
) RETURNS TABLE (
    record_key     text,
    sku_id         uuid,
    sale_time      timestamptz,
    copies         bigint,
    identical      boolean,
    keep_id        text,
    units_per_copy bigint
)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    v_tenant uuid := public.current_tenant_id();
BEGIN
    IF v_tenant IS NULL THEN
        RAISE EXCEPTION 'sanket_dedupe_sales requires app.current_tenant_id';
    END IF;

    RETURN QUERY
    WITH grp AS (
        SELECT h.record_key                                     AS g_key,
               min(h.sku_id::text)::uuid                        AS g_sku,
               min(h.sale_time)                                 AS g_time,
               count(*)                                         AS g_copies,
               count(DISTINCT md5(concat_ws('|',
                   h.sku_id::text, h.sale_time::text, h.channel,
                   COALESCE(h.region, ''), COALESCE(h.location, ''),
                   h.units_sold::text, COALESCE(h.gross_revenue::text, ''),
                   COALESCE(h.net_revenue::text, ''), h.returns::text,
                   COALESCE(h.in_stock::text, ''), h.promo_flag::text,
                   COALESCE(h.markdown_pct::text, '')))) = 1       AS g_identical,
               min(h.id::text)                                  AS g_keep,
               max(h.units_sold)::bigint                        AS g_units
          FROM public.historical_sales h
         WHERE h.tenant_id = v_tenant
           AND h.industry = p_industry
           AND h.record_key IS NOT NULL
         GROUP BY h.record_key
        HAVING count(*) > 1
    ),
    removed AS (
        DELETE FROM public.historical_sales d
         USING grp
         WHERE NOT p_dry_run
           AND grp.g_identical
           AND d.tenant_id = v_tenant
           AND d.industry = p_industry
           AND d.record_key = grp.g_key
           AND d.id::text <> grp.g_keep
        RETURNING d.id
    )
    SELECT grp.g_key, grp.g_sku, grp.g_time, grp.g_copies, grp.g_identical,
           grp.g_keep, grp.g_units
      FROM grp;
END;
$$;
"""

# Interpolates only the module-level signature constants above.
_GRANT_TO_APP = f"""
DO $grant$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sanket_app') THEN
        GRANT EXECUTE ON FUNCTION {_SIGNATURE_CORRECT} TO sanket_app;
        GRANT EXECUTE ON FUNCTION {_SIGNATURE_DEDUPE} TO sanket_app;
    END IF;
END
$grant$;
"""  # noqa: S608


def upgrade() -> None:
    # asyncpg prepares one statement per execute.
    op.execute(_CORRECT_SALE)
    op.execute(_DEDUPE_SALES)
    op.execute(f"REVOKE ALL ON FUNCTION {_SIGNATURE_CORRECT} FROM PUBLIC")
    op.execute(f"REVOKE ALL ON FUNCTION {_SIGNATURE_DEDUPE} FROM PUBLIC")
    op.execute(_GRANT_TO_APP)


def downgrade() -> None:
    op.execute(f"DROP FUNCTION IF EXISTS {_SIGNATURE_DEDUPE}")
    op.execute(f"DROP FUNCTION IF EXISTS {_SIGNATURE_CORRECT}")
