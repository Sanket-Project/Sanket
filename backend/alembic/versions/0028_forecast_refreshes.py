"""Durable tenant forecast refresh state and input invalidation.

Revision ID: 0028
Revises: 0027
"""
from alembic import op

revision = '0028'
down_revision = '0027'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE forecast_refreshes (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            industry industry_code NOT NULL,
            horizon_weeks smallint NOT NULL CHECK (horizon_weeks BETWEEN 1 AND 104),
            force_zero_shot boolean NOT NULL DEFAULT true,
            status text NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','running','completed','failed')),
            operation text NOT NULL DEFAULT 'generate' CHECK (operation IN ('generate','split')),
            base_run_id uuid REFERENCES forecast_runs(id) ON DELETE SET NULL,
            error text,
            created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            completed_at timestamptz
        )
    """)
    op.execute("CREATE UNIQUE INDEX uq_forecast_refresh_active ON forecast_refreshes (tenant_id) "
               "WHERE status IN ('pending','running')")
    op.execute("CREATE INDEX ix_forecast_refresh_latest ON forecast_refreshes "
               "(tenant_id, industry, created_at DESC)")
    op.execute("""
        CREATE TABLE forecast_input_changes (
            tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
            industry industry_code NOT NULL,
            changed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY (tenant_id, industry)
        )
    """)
    for table in ('forecast_refreshes', 'forecast_input_changes'):
        op.execute(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE {table} FORCE ROW LEVEL SECURITY')
        op.execute(f'CREATE POLICY {table}_isolation ON {table} '
                   'USING (tenant_id = current_tenant_id()) '
                   'WITH CHECK (tenant_id = current_tenant_id())')
        op.execute(f'GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO sanket_app')
    # Statement transition tables invalidate once per affected tenant/industry
    # per batch, covering CSV, POS and connectors without row-by-row writes.
    op.execute("""
        CREATE FUNCTION sanket_forecast_inputs_changed() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            INSERT INTO forecast_input_changes (tenant_id,industry,changed_at)
            SELECT DISTINCT tenant_id,industry,clock_timestamp() FROM
                (SELECT DISTINCT tenant_id,industry FROM changed_sales) affected
            ON CONFLICT (tenant_id,industry) DO UPDATE SET changed_at=clock_timestamp();
            RETURN NULL;
        END $$
    """)
    for event, transition in (('INSERT', 'NEW'), ('UPDATE', 'NEW'), ('DELETE', 'OLD')):
        op.execute(f'CREATE TRIGGER forecast_inputs_{event.lower()} AFTER {event} ON historical_sales '
                   f'REFERENCING {transition} TABLE AS changed_sales FOR EACH STATEMENT '
                   'EXECUTE FUNCTION sanket_forecast_inputs_changed()')
    op.execute("CREATE INDEX ix_forecast_runs_latest_production ON forecast_runs "
               "(tenant_id, industry, completed_at DESC) WHERE status='completed' "
               "AND (metrics->>'mode' IS NULL OR metrics->>'mode' <> 'backtest')")
    op.execute('CREATE INDEX ix_forecast_results_run_sku_date ON forecast_results '
               '(run_id, sku_id, forecast_date)')


def downgrade() -> None:
    for event in ('insert', 'update', 'delete'):
        op.execute(f'DROP TRIGGER forecast_inputs_{event} ON historical_sales')
    op.execute('DROP FUNCTION sanket_forecast_inputs_changed()')
    op.execute('DROP INDEX ix_forecast_results_run_sku_date')
    op.execute('DROP INDEX ix_forecast_runs_latest_production')
    op.execute('DROP TABLE forecast_input_changes')
    op.execute('DROP TABLE forecast_refreshes')
