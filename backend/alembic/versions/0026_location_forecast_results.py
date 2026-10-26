"""Add location_forecast_results — per-(SKU, location) forecasts (location spec §4.3).

Kept apart from forecast_results on purpose: every existing reader aggregates
forecast_results by sku_id, and location rows there would be double counted.
Quarterly RANGE partitions on forecast_date, maintained by
sanket_maintain_partitions() exactly like forecast_results.

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-26
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _maintain_fn(include_location: bool) -> str:
    location = (
        """
    parent := 'location_forecast_results';
    created := sanket_ensure_quarterly_partitions('location_forecast_results'::regclass, 1, 4);
    RETURN NEXT;
"""
        if include_location
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

    parent := 'trend_signals';
    created := sanket_ensure_monthly_partitions('trend_signals'::regclass, 2, 3);
    RETURN NEXT;
{location}END;
$$;
"""


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE location_forecast_results (
            id             UUID          NOT NULL DEFAULT gen_random_uuid(),
            tenant_id      UUID          NOT NULL,
            run_id         UUID          NOT NULL REFERENCES forecast_runs (id) ON DELETE CASCADE,
            sku_id         UUID          NOT NULL,
            location_id    UUID          NOT NULL,
            forecast_date  DATE          NOT NULL,
            p10            NUMERIC(18,4) NOT NULL,
            p50            NUMERIC(18,4) NOT NULL,
            p90            NUMERIC(18,4) NOT NULL,
            share          NUMERIC(9,6)  NOT NULL,
            share_basis    TEXT          NOT NULL,
            method         TEXT          NOT NULL,
            created_at     TIMESTAMPTZ   NOT NULL DEFAULT now(),
            PRIMARY KEY (id, forecast_date),
            CONSTRAINT ck_lfr_basis CHECK (share_basis IN ('sku_history', 'blended', 'category_prior')),
            CONSTRAINT ck_lfr_method CHECK (method IN ('share_split_v1', 'middle_out_mint'))
        ) PARTITION BY RANGE (forecast_date)
        """
    )
    op.execute("CREATE INDEX idx_lfr_run_sku_loc ON location_forecast_results "
               "(run_id, sku_id, location_id, forecast_date)")
    op.execute("CREATE INDEX idx_lfr_tenant_loc ON location_forecast_results "
               "(tenant_id, location_id, forecast_date)")
    op.execute("ALTER TABLE location_forecast_results ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE location_forecast_results FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY location_forecast_results_isolation ON location_forecast_results "
        "USING (bypass_rls() OR tenant_id = current_tenant_id())"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON location_forecast_results TO sanket_app")
    op.execute(_maintain_fn(include_location=True))
    op.execute("SELECT sanket_maintain_partitions()")


def downgrade() -> None:
    op.execute(_maintain_fn(include_location=False))
    op.execute("DROP TABLE IF EXISTS location_forecast_results CASCADE")
