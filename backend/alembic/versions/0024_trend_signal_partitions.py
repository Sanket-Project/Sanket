"""Rolling monthly partitions for trend_signals.

``trend_signals`` is range-partitioned by month on ``captured_at``, but only
May–August 2026 were ever created (sql/006_phase6_trends_alerts.sql) and the
rolling maintenance added in 0013 covers the quarterly tables only. From
September 2026 every signal insert failed with "no partition of relation
trend_signals found for row" (audit F05, 25 Oct 2026), so the Trends page had
zero samples.

* ``sanket_ensure_monthly_partitions(parent, lookback, lookahead, anchor)``
  creates any missing ``<parent>_YYYY_MM`` partitions in a window around
  ``anchor`` (default today). Idempotent; SECURITY DEFINER with a pinned
  search_path, exactly like the quarterly variant, so the unprivileged app role
  can run it as a self-healing net at startup.
* ``sanket_maintain_partitions()`` now also maintains ``trend_signals``
  (2 months back for late-arriving samples, 3 ahead), so startup and the
  partition-maintenance CronJob keep future months provisioned.

Retention is deliberately not automated: no partition is ever dropped here.

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-26
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_CREATE_MONTHLY_FN = r"""
CREATE OR REPLACE FUNCTION sanket_ensure_monthly_partitions(
    parent            regclass,
    lookback_months   int  DEFAULT 2,
    lookahead_months  int  DEFAULT 3,
    anchor            date DEFAULT current_date
) RETURNS int
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
DECLARE
    parent_schema text;
    parent_name   text;
    base_m        date := date_trunc('month', anchor)::date;
    i             int;
    ms            date;
    me            date;
    part_name     text;
    created       int  := 0;
BEGIN
    IF lookback_months < 0 OR lookahead_months < 0 THEN
        RAISE EXCEPTION 'lookback/lookahead months must be >= 0';
    END IF;

    SELECT n.nspname, c.relname
      INTO parent_schema, parent_name
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE c.oid = parent;

    FOR i IN -lookback_months .. lookahead_months LOOP
        ms := (base_m + (i * INTERVAL '1 month'))::date;
        me := (ms + INTERVAL '1 month')::date;
        part_name := format('%s_%s', parent_name, to_char(ms, 'YYYY_MM'));

        IF to_regclass(format('%I.%I', parent_schema, part_name)) IS NULL THEN
            EXECUTE format(
                'CREATE TABLE %I.%I PARTITION OF %I.%I FOR VALUES FROM (%L) TO (%L)',
                parent_schema, part_name, parent_schema, parent_name, ms, me
            );
            created := created + 1;
        END IF;
    END LOOP;

    RETURN created;
END;
$$;
"""


def _maintain_fn(include_trend_signals: bool) -> str:
    trend = (
        """
    parent := 'trend_signals';
    created := sanket_ensure_monthly_partitions('trend_signals'::regclass, 2, 3);
    RETURN NEXT;
"""
        if include_trend_signals
        else ""
    )
    return f"""
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
{trend}END;
$$;
"""


def upgrade() -> None:
    op.execute(_CREATE_MONTHLY_FN)
    op.execute(_maintain_fn(include_trend_signals=True))
    # Provision the current window immediately: a database already past its last
    # trend partition starts accepting signals the moment this migration runs.
    op.execute("SELECT sanket_maintain_partitions()")


def downgrade() -> None:
    op.execute(_maintain_fn(include_trend_signals=False))
    op.execute(
        "DROP FUNCTION IF EXISTS sanket_ensure_monthly_partitions(regclass, int, int, date)"
    )
