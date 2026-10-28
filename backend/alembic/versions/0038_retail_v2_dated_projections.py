"""Rebuild V2 analytics with canonical UUIDs and credit-date recognition.

Revision ID: 0038
Revises: 0037

Data repair only. Run with MIGRATION_DATABASE_URL credentials that can see all
tenants. Canonical events (including already-approved credit amounts) remain
the audit authority; this migration does not silently change issued credits.
"""

from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname=current_user
                           AND (rolsuper OR rolbypassrls)) THEN
                RAISE EXCEPTION 'V2 projection repair requires MIGRATION_DATABASE_URL with cross-tenant migration privileges';
            END IF;
        END $$
    """)
    # Prevent uploads from committing a mixture of the old and new projection.
    op.execute("LOCK TABLE v2_sales_events, v2_return_events, historical_sales IN SHARE ROW EXCLUSIVE MODE")
    op.execute("""
        CREATE TEMP TABLE retail_v2_projection_tenants ON COMMIT DROP AS
        SELECT DISTINCT tenant_id FROM historical_sales WHERE metadata->>'source'='retail_v2'
    """)
    op.execute("""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM historical_sales h
                WHERE h.metadata->>'source'='retail_v2'
                  AND NOT EXISTS (SELECT 1 FROM v2_sales_events e
                                  WHERE e.tenant_id=h.tenant_id AND e.id::text=h.metadata->>'event_id')
                  AND NOT EXISTS (SELECT 1 FROM v2_return_events r
                                  WHERE r.tenant_id=h.tenant_id AND r.id::text=h.metadata->>'event_id')
            ) THEN
                RAISE EXCEPTION 'V2 history has no canonical event; reconcile before projection repair';
            END IF;
            IF EXISTS (
                SELECT 1 FROM v2_sales_events e
                JOIN retail_v2_projection_tenants t ON t.tenant_id=e.tenant_id
                WHERE (SELECT count(*) FROM skus s WHERE s.tenant_id=e.tenant_id
                       AND lower(s.sku_code)=lower(e.sku_code)) <> 1
            ) THEN
                RAISE EXCEPTION 'V2 canonical sale has an unresolved or ambiguous SKU; reconcile before projection repair';
            END IF;
        END $$
    """)
    op.execute("DELETE FROM historical_sales WHERE metadata->>'source'='retail_v2'")
    op.execute("""
        INSERT INTO historical_sales (
            id, tenant_id, sku_id, industry, sale_time, channel, region, units_sold,
            gross_revenue, net_revenue, returns, promo_flag, markdown_pct, in_stock,
            record_key, location, metadata
        )
        SELECT gen_random_uuid(), e.tenant_id, s.id, s.industry, e.transaction_at,
               e.channel_code, NULL, e.quantity_sold, e.gross_sales_ex_tax,
               e.net_sale_ex_tax, 0, false, NULL, NULL, 'v2:sale:' || e.id::text,
               e.location_code, jsonb_build_object('source','retail_v2',
                                                   'event_kind','sale','event_id',e.id::text)
        FROM v2_sales_events e
        JOIN retail_v2_projection_tenants t ON t.tenant_id=e.tenant_id
        JOIN skus s ON s.tenant_id=e.tenant_id AND lower(s.sku_code)=lower(e.sku_code)
    """)
    op.execute("""
        INSERT INTO historical_sales (
            id, tenant_id, sku_id, industry, sale_time, channel, region, units_sold,
            gross_revenue, net_revenue, returns, promo_flag, markdown_pct, in_stock,
            record_key, location, metadata
        )
        SELECT gen_random_uuid(), r.tenant_id, s.id, s.industry, r.return_at,
               e.channel_code, NULL, 0, 0, -r.return_value_ex_tax, r.returns,
               false, NULL, NULL, 'v2:return:' || r.id::text, r.location_code,
               jsonb_build_object('source','retail_v2','event_kind','return',
                                  'event_id',r.id::text,'sale_event_id',e.id::text)
        FROM v2_return_events r
        JOIN retail_v2_projection_tenants t ON t.tenant_id=r.tenant_id
        JOIN v2_sales_events e ON e.tenant_id=r.tenant_id AND e.id=r.sale_event_id
        JOIN skus s ON s.tenant_id=e.tenant_id AND lower(s.sku_code)=lower(e.sku_code)
        WHERE r.status='approved'
    """)


def downgrade():
    # Data corrections are retained; downgrading must not reintroduce lost sales
    # or restate historical revenue. No schema objects were added.
    pass
