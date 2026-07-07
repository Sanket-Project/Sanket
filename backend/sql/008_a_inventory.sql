-- SANKET Platform — Inventory levels (real warehouse stock)
-- Requires 002_schema.sql + 003_rls_policies.sql to have been applied first.
--
-- This is the real-stock source of truth. Until now the insight layer
-- (shortage alerts, coverage-days, replenishment, financial risk) had no
-- inventory feed and fell back to a fabricated `safety_stock * 2`. With this
-- table populated, those insights reflect the stock actually in the warehouse.

CREATE TABLE IF NOT EXISTS inventory_levels (
    id              UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID            NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
    sku_id          UUID            NOT NULL REFERENCES skus (id) ON DELETE CASCADE,
    industry        industry_code   NOT NULL,
    location        TEXT            NOT NULL DEFAULT 'default',
    on_hand_units   NUMERIC(18,2)   NOT NULL DEFAULT 0 CHECK (on_hand_units  >= 0),
    inbound_units   NUMERIC(18,2)   NOT NULL DEFAULT 0 CHECK (inbound_units  >= 0),
    reserved_units  NUMERIC(18,2)   NOT NULL DEFAULT 0 CHECK (reserved_units >= 0),
    as_of           TIMESTAMPTZ     NOT NULL DEFAULT now(),
    source          TEXT            NOT NULL DEFAULT 'manual',
    attributes      JSONB           NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT now(),
    -- One current position per SKU per location; ingestion upserts on this key.
    CONSTRAINT uq_inventory_tenant_sku_loc UNIQUE (tenant_id, sku_id, location)
);

CREATE INDEX IF NOT EXISTS idx_inventory_tenant_sku ON inventory_levels (tenant_id, sku_id);
CREATE INDEX IF NOT EXISTS idx_inventory_tenant_industry ON inventory_levels (tenant_id, industry);

CREATE TRIGGER trg_inventory_levels_updated_at
    BEFORE UPDATE ON inventory_levels
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ── Row-level security ──────────────────────────────────────────────────────
ALTER TABLE inventory_levels ENABLE ROW LEVEL SECURITY;

CREATE POLICY inventory_levels_isolation ON inventory_levels
    USING (bypass_rls() OR tenant_id = current_tenant_id());

GRANT SELECT, INSERT, UPDATE, DELETE ON inventory_levels TO sanket_app;

-- ── Seed initial stock for existing SKUs ────────────────────────────────────
-- Deterministic spread (≈0.4×–3.0× of reorder_point+safety_stock) so demo data
-- contains a realistic mix of healthy, low, and at-risk coverage levels rather
-- than a flat uniform number.
INSERT INTO inventory_levels (tenant_id, sku_id, industry, location, on_hand_units, inbound_units, source)
SELECT
    s.tenant_id,
    s.id,
    s.industry,
    'default',
    GREATEST(
        0,
        ROUND(
            (COALESCE(s.reorder_point, 0) + COALESCE(s.safety_stock, 0))
            * (0.4 + (abs(hashtext(s.id::text)) % 260) / 100.0)
        )
    ),
    0,
    'seed'
FROM skus s
ON CONFLICT (tenant_id, sku_id, location) DO NOTHING;
