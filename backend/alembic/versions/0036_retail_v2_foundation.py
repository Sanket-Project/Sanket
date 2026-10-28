"""Fashion Retail V2 foundation: Event registry, stock authorities, V2 sales, returns, and inventory snapshots.

FORCE ROW LEVEL SECURITY is enabled on every table with tenant isolation.
"""

from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Event Identity Registry
    op.execute("""CREATE TABLE event_identity_registry (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        source_system text NOT NULL,
        entity_kind text NOT NULL,
        external_event_id text NOT NULL,
        event_line_id text NOT NULL DEFAULT '',
        payload_hash text NOT NULL,
        target_id uuid,
        revision integer NOT NULL DEFAULT 1,
        status text NOT NULL DEFAULT 'committed',
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        UNIQUE (tenant_id, source_system, entity_kind, external_event_id, event_line_id)
    )""")
    op.execute("ALTER TABLE event_identity_registry ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE event_identity_registry FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY event_identity_registry_isolation ON event_identity_registry
        USING (tenant_id = current_tenant_id()) WITH CHECK (tenant_id = current_tenant_id())""")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON event_identity_registry TO sanket_app")

    # 2. Stock Authorities
    op.execute("""CREATE TABLE stock_authorities (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        location_code text NOT NULL,
        source_system text NOT NULL DEFAULT 'upload',
        authority_mode text NOT NULL CHECK (authority_mode IN ('external_snapshot', 'internal_ledger')),
        effective_from timestamptz NOT NULL DEFAULT clock_timestamp(),
        effective_to timestamptz,
        scope jsonb NOT NULL DEFAULT '{}'::jsonb,
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        UNIQUE (tenant_id, location_code, source_system, authority_mode)
    )""")
    op.execute("ALTER TABLE stock_authorities ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE stock_authorities FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY stock_authorities_isolation ON stock_authorities
        USING (tenant_id = current_tenant_id()) WITH CHECK (tenant_id = current_tenant_id())""")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON stock_authorities TO sanket_app")

    # 3. V2 Sales Events
    op.execute("""CREATE TABLE v2_sales_events (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        source_system text NOT NULL,
        transaction_id text NOT NULL,
        order_id text NOT NULL,
        order_line_id text NOT NULL,
        transaction_at timestamptz NOT NULL,
        sku_code text NOT NULL,
        location_code text NOT NULL,
        fulfillment_location_code text NOT NULL,
        channel_code text NOT NULL,
        quantity_sold integer NOT NULL CHECK (quantity_sold >= 0),
        unit_price_ex_tax numeric(18,4) NOT NULL CHECK (unit_price_ex_tax >= 0),
        mrp_incl_tax numeric(18,2),
        discount_ex_tax numeric(18,2) NOT NULL DEFAULT 0 CHECK (discount_ex_tax >= 0),
        gross_sales_ex_tax numeric(18,2) NOT NULL CHECK (gross_sales_ex_tax >= 0),
        net_sale_ex_tax numeric(18,2) NOT NULL CHECK (net_sale_ex_tax >= 0),
        tax_code text NOT NULL,
        tax_rate_pct numeric(7,4) NOT NULL CHECK (tax_rate_pct >= 0),
        tax_amount numeric(18,2) NOT NULL DEFAULT 0 CHECK (tax_amount >= 0),
        currency varchar(3) NOT NULL,
        order_status text NOT NULL CHECK (order_status IN ('completed', 'cancelled')),
        invoice_number text,
        place_of_supply_state_code text,
        payment_method text,
        payment_reference text,
        payment_amount numeric(18,2),
        cumulative_returned_qty integer NOT NULL DEFAULT 0 CHECK (cumulative_returned_qty >= 0),
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        UNIQUE (tenant_id, source_system, transaction_id, order_line_id)
    )""")
    op.execute("ALTER TABLE v2_sales_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE v2_sales_events FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY v2_sales_events_isolation ON v2_sales_events
        USING (tenant_id = current_tenant_id()) WITH CHECK (tenant_id = current_tenant_id())""")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON v2_sales_events TO sanket_app")

    # 4. V2 Return Events
    op.execute("""CREATE TABLE v2_return_events (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        source_system text NOT NULL,
        return_id text NOT NULL,
        return_line_id text NOT NULL,
        return_at timestamptz NOT NULL,
        original_source_system text NOT NULL,
        original_transaction_id text NOT NULL,
        original_order_line_id text NOT NULL,
        sale_event_id uuid REFERENCES v2_sales_events(id) ON DELETE RESTRICT,
        sku_code text NOT NULL,
        location_code text NOT NULL,
        returns integer NOT NULL CHECK (returns > 0),
        return_value_ex_tax numeric(18,2) NOT NULL CHECK (return_value_ex_tax >= 0),
        tax_code text NOT NULL,
        tax_amount numeric(18,2) NOT NULL DEFAULT 0 CHECK (tax_amount >= 0),
        currency varchar(3) NOT NULL,
        reason_code text NOT NULL,
        disposition text NOT NULL CHECK (disposition IN ('restock', 'quarantine', 'damaged', 'no_receipt')),
        status text NOT NULL CHECK (status IN ('approved', 'draft', 'rejected')),
        credit_note_number text,
        refund_reference text,
        refund_amount numeric(18,2),
        refund_method text,
        refund_at timestamptz,
        exchange_order_id text,
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        UNIQUE (tenant_id, source_system, return_id, return_line_id)
    )""")
    op.execute("ALTER TABLE v2_return_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE v2_return_events FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY v2_return_events_isolation ON v2_return_events
        USING (tenant_id = current_tenant_id()) WITH CHECK (tenant_id = current_tenant_id())""")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON v2_return_events TO sanket_app")

    # 5. V2 Inventory Snapshots
    op.execute("""CREATE TABLE v2_inventory_snapshots (
        id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
        tenant_id uuid NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
        snapshot_id text NOT NULL,
        as_of timestamptz NOT NULL,
        sku_code text NOT NULL,
        location_code text NOT NULL,
        on_hand_qty integer NOT NULL CHECK (on_hand_qty >= 0),
        reserved_qty integer NOT NULL DEFAULT 0 CHECK (reserved_qty >= 0),
        damaged_qty integer NOT NULL DEFAULT 0 CHECK (damaged_qty >= 0),
        quarantine_qty integer NOT NULL DEFAULT 0 CHECK (quarantine_qty >= 0),
        in_transit_qty integer NOT NULL DEFAULT 0 CHECK (in_transit_qty >= 0),
        open_po_qty integer NOT NULL DEFAULT 0 CHECK (open_po_qty >= 0),
        source_system text NOT NULL,
        count_reference text,
        reported_stock_value_ex_tax numeric(18,4),
        currency varchar(3),
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        UNIQUE (tenant_id, snapshot_id, sku_code, location_code)
    )""")
    op.execute("ALTER TABLE v2_inventory_snapshots ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE v2_inventory_snapshots FORCE ROW LEVEL SECURITY")
    op.execute("""CREATE POLICY v2_inventory_snapshots_isolation ON v2_inventory_snapshots
        USING (tenant_id = current_tenant_id()) WITH CHECK (tenant_id = current_tenant_id())""")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON v2_inventory_snapshots TO sanket_app")


def downgrade():
    op.execute("DROP TABLE IF EXISTS v2_inventory_snapshots")
    op.execute("DROP TABLE IF EXISTS v2_return_events")
    op.execute("DROP TABLE IF EXISTS v2_sales_events")
    op.execute("DROP TABLE IF EXISTS stock_authorities")
    op.execute("DROP TABLE IF EXISTS event_identity_registry")
