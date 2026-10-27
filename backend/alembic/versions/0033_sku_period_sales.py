"""Per-SKU sales totals for a date range (report exports without per-sale dates), FORCE RLS."""
from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE sku_period_sales (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        sku_id uuid NOT NULL REFERENCES skus(id) ON DELETE CASCADE,
        location text NOT NULL DEFAULT 'default',
        period_start date NOT NULL,
        period_end date NOT NULL,
        -- Net of returns: negative when a period's returns exceed its sales.
        units numeric(18,4) NOT NULL,
        net_value numeric(18,4),
        cost_value numeric(18,4),
        source text NOT NULL,
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        CHECK (period_end >= period_start),
        UNIQUE (tenant_id, sku_id, location, period_start, period_end)
    )""")
    op.execute("ALTER TABLE sku_period_sales ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE sku_period_sales FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY sku_period_sales_isolation ON sku_period_sales
        USING (tenant_id=current_tenant_id()) WITH CHECK (tenant_id=current_tenant_id())""")
    op.execute("GRANT SELECT,INSERT,UPDATE,DELETE ON sku_period_sales TO sanket_app")


def downgrade():
    op.execute("DROP TABLE sku_period_sales")
