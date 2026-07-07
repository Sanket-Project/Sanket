"""Automate range-partition creation for historical_sales / forecast_results.

The original schema (sql/002_schema.sql) materialised a *static* set of quarterly
partitions inside a one-shot ``DO`` block — 2022-2027 for ``historical_sales`` and
2024-2027 for ``forecast_results``. That is a latent production outage: the first
INSERT whose ``sale_time`` / ``forecast_date`` falls past the last declared
partition fails with *"no partition of relation … found for row"*, and at
enterprise ingest volumes nobody notices until the calendar rolls over.

This migration replaces the manual approach with a self-maintaining function:

* ``sanket_ensure_quarterly_partitions(parent, lookback, lookahead)`` creates any
  missing quarterly partitions in a rolling window around *now* (idempotent — it
  only creates partitions that don't already exist, so it is safe to run on every
  deploy and on a schedule).
* ``sanket_maintain_partitions()`` applies that to both partitioned tables.

It is ``SECURITY DEFINER`` so the unprivileged runtime role (``sanket_app``) can
call it as a self-healing net at startup, while the k8s CronJob
(``infra/cron/partition-maintenance-cronjob.yaml``) runs it on a schedule so new
quarters always exist *before* the first row needs them.

Revision ID: 0013
Revises: 64b00842a1e6
Create Date: 2026-06-14
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0013"
down_revision: str | None = "64b00842a1e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# asyncpg cannot prepare more than one statement per execute, so each CREATE
# FUNCTION is issued separately rather than as one bundled script.
_CREATE_ENSURE_FN = r"""
-- Create any missing quarterly partitions of `parent` in a rolling window of
-- [now - lookback_quarters, now + lookahead_quarters]. Returns the number of
-- partitions actually created. Idempotent and safe to call repeatedly.
CREATE OR REPLACE FUNCTION sanket_ensure_quarterly_partitions(
    parent              regclass,
    lookback_quarters   int DEFAULT 1,
    lookahead_quarters  int DEFAULT 4
) RETURNS int
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    parent_schema text;
    parent_name   text;
    base_q        date := date_trunc('quarter', now())::date;
    i             int;
    qs            date;
    qe            date;
    part_name     text;
    created       int  := 0;
BEGIN
    IF lookback_quarters < 0 OR lookahead_quarters < 0 THEN
        RAISE EXCEPTION 'lookback/lookahead quarters must be >= 0';
    END IF;

    -- Resolve the parent's real schema + name from the catalog. New partitions
    -- are created explicitly in the parent's schema; we never rely on
    -- search_path for object *creation* (search_path is pinned pg_catalog-first
    -- only so builtin functions can't be shadowed in a SECURITY DEFINER body).
    SELECT n.nspname, c.relname
      INTO parent_schema, parent_name
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE c.oid = parent;

    FOR i IN -lookback_quarters .. lookahead_quarters LOOP
        qs := (base_q + (i * INTERVAL '3 months'))::date;
        qe := (qs + INTERVAL '3 months')::date;
        part_name := format('%s_%s_q%s',
                            parent_name,
                            extract(year   FROM qs)::int,
                            extract(quarter FROM qs)::int);

        -- to_regclass() is NULL when the partition does not exist yet.
        IF to_regclass(format('%I.%I', parent_schema, part_name)) IS NULL THEN
            EXECUTE format(
                'CREATE TABLE %I.%I PARTITION OF %I.%I FOR VALUES FROM (%L) TO (%L)',
                parent_schema, part_name, parent_schema, parent_name, qs, qe
            );
            created := created + 1;
        END IF;
    END LOOP;

    RETURN created;
END;
$$;
"""


_CREATE_MAINTAIN_FN = r"""
-- Maintain partitions for every partitioned table the platform owns. Called at
-- app startup (best-effort) and by the partition-maintenance CronJob.
CREATE OR REPLACE FUNCTION sanket_maintain_partitions()
RETURNS TABLE (parent text, created int)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    parent := 'historical_sales';
    created := sanket_ensure_quarterly_partitions('historical_sales'::regclass, 1, 4);
    RETURN NEXT;

    parent := 'forecast_results';
    created := sanket_ensure_quarterly_partitions('forecast_results'::regclass, 1, 4);
    RETURN NEXT;
END;
$$;
"""


def upgrade() -> None:
    op.execute(_CREATE_ENSURE_FN)
    op.execute(_CREATE_MAINTAIN_FN)
    # Extend the window immediately so a database that is already near the end of
    # its statically-declared partitions is covered the moment this migration runs.
    op.execute("SELECT sanket_maintain_partitions()")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS sanket_maintain_partitions()")
    op.execute(
        "DROP FUNCTION IF EXISTS sanket_ensure_quarterly_partitions(regclass, int, int)"
    )
