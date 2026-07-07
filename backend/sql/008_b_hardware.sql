-- SANKET Phase 8: Hardware & Industrial Supply industry
-- Adds the hardware vertical (tools, fasteners, electrical, plumbing,
-- building materials, safety) plus a demo catalog so dashboards populate.
-- Apply against a running database:
--
-- Docker:  docker compose exec postgres psql -U sanket_app -d sanket -f /docker-entrypoint-initdb.d/008_hardware.sql
-- Local:   psql postgresql://sanket_app:changeme@localhost:5432/sanket -f backend/sql/008_hardware.sql

-- ─────────────────────────────────────────
-- 1. Extend the ENUM
--    ALTER TYPE ... ADD VALUE cannot run inside a transaction block.
--    Run this file outside of BEGIN/COMMIT (psql does this by default).
-- ─────────────────────────────────────────
ALTER TYPE industry_code ADD VALUE IF NOT EXISTS 'hardware';

-- ─────────────────────────────────────────
-- 2. Industry definition row
-- ─────────────────────────────────────────
INSERT INTO industries (
    code,
    display_name,
    default_horizon_weeks,
    granularity_dimensions,
    required_signal_types,
    sku_attribute_schema,
    forecast_models,
    optimization_models,
    audit_level
) VALUES (
    'hardware',
    'Hardware & Industrial Supply',
    16,
    ARRAY['category','region','channel','brand'],
    ARRAY['competitor_price','macro_economic','supplier_lead','logistics_disruption']::signal_type[],
    '{
        "product_type":   {"type": "string", "enum": ["tool","fastener","building_material","electrical","plumbing","paint","safety"]},
        "material":       {"type": "string"},
        "finish":         {"type": "string"},
        "dimensions":     {"type": "string"},
        "grade":          {"type": "string"},
        "voltage":        {"type": "string"},
        "power_rating_w": {"type": "integer"},
        "certification":  {"type": "string"},
        "pack_size":      {"type": "integer"}
    }'::jsonb,
    ARRAY['TimesFM','TFT','N-HiTS','LightGBM','Chronos'],
    ARRAY['OR-Tools','safety-stock-optimizer','RLlib-replenishment'],
    'standard'
)
ON CONFLICT (code) DO UPDATE SET
    display_name            = EXCLUDED.display_name,
    default_horizon_weeks   = EXCLUDED.default_horizon_weeks,
    granularity_dimensions  = EXCLUDED.granularity_dimensions,
    required_signal_types   = EXCLUDED.required_signal_types,
    sku_attribute_schema    = EXCLUDED.sku_attribute_schema,
    forecast_models         = EXCLUDED.forecast_models,
    optimization_models     = EXCLUDED.optimization_models,
    audit_level             = EXCLUDED.audit_level,
    updated_at              = now();

-- ─────────────────────────────────────────
-- 3. Update dev tenant + add industry profile + seed a demo catalog
-- ─────────────────────────────────────────
DO $$
DECLARE
    v_tenant_id UUID;
BEGIN
    SELECT id INTO v_tenant_id FROM tenants WHERE slug = 'sanket-dev';

    IF v_tenant_id IS NULL THEN
        RAISE NOTICE 'Dev tenant not found — skipping tenant update + catalog seed';
        RETURN;
    END IF;

    -- Bypass RLS for the tenant-list update, then scope to the tenant for catalog inserts.
    PERFORM set_config('app.current_tenant_id', '', true);

    -- Add hardware to the tenant's industry list (only if not already present)
    UPDATE tenants
    SET industries = array_append(industries, 'hardware'::industry_code),
        updated_at = now()
    WHERE id = v_tenant_id
      AND NOT ('hardware'::industry_code = ANY(industries));

    -- Per-tenant industry profile
    INSERT INTO industry_profiles (tenant_id, industry, model_overrides, feature_flags)
    VALUES (v_tenant_id, 'hardware', '{}',
            '{"supply_risk": true, "competitor_tracking": true, "safety_stock_optimizer": true}')
    ON CONFLICT (tenant_id, industry) DO NOTHING;

    -- Scope subsequent inserts to the tenant so RLS policies pass.
    PERFORM set_config('app.current_tenant_id', v_tenant_id::text, true);

    -- Demo products (idempotent on external_id)
    INSERT INTO products (
        id, tenant_id, industry, external_id, name, brand, category, status, attributes
    )
    SELECT gen_random_uuid(), v_tenant_id, 'hardware'::industry_code,
           p.external_id, p.name, 'SANKET Demo', p.category, 'active', '{}'::jsonb
    FROM (VALUES
        ('HW-DRILL',  'Cordless Hammer Drill 18V', 'Power Tools'),
        ('HW-FAST',   'Hex Bolt Assortment',       'Fasteners'),
        ('HW-WIRE',   'THHN Building Wire',         'Electrical'),
        ('HW-PIPE',   'PVC Pressure Pipe',          'Plumbing'),
        ('HW-CEMENT', 'Rapid-Set Cement 25kg',      'Building Materials'),
        ('HW-PPE',    'Industrial Safety Helmet',   'Safety')
    ) AS p(external_id, name, category)
    ON CONFLICT (tenant_id, external_id) WHERE external_id IS NOT NULL DO NOTHING;

    -- Demo SKUs (idempotent on sku_code), attributes match the hardware schema
    INSERT INTO skus (
        id, tenant_id, product_id, industry, sku_code, description,
        unit_cost, unit_price, lead_time_days, moq, safety_stock, reorder_point,
        attributes, is_active
    )
    SELECT gen_random_uuid(), v_tenant_id, pr.id, 'hardware'::industry_code,
           v.sku_code, v.description,
           v.unit_cost, v.unit_price, v.lead_time, 1, v.safety, v.reorder,
           v.attrs::jsonb, true
    FROM (VALUES
        ('HW-DRILL',  'HW-DRILL-01',  'Cordless Hammer Drill 18V / Bare Tool',     78,  149, 35, 40,  70, '{"product_type":"tool","material":"composite","finish":"matte","power_rating_w":450,"voltage":"18V","certification":"CE","pack_size":1}'),
        ('HW-DRILL',  'HW-DRILL-02',  'Cordless Hammer Drill 18V / 2-Battery Kit', 110, 219, 42, 30,  55, '{"product_type":"tool","material":"composite","finish":"matte","power_rating_w":450,"voltage":"18V","certification":"CE","pack_size":1}'),
        ('HW-FAST',   'HW-FAST-01',   'Hex Bolt Assortment / M8 Grade 8.8',        12,  29,  21, 200, 320, '{"product_type":"fastener","material":"carbon_steel","finish":"zinc","dimensions":"M8 x 50mm","grade":"8.8","pack_size":100}'),
        ('HW-FAST',   'HW-FAST-02',   'Hex Bolt Assortment / M10 Stainless A2',    18,  41,  28, 150, 240, '{"product_type":"fastener","material":"stainless_a2","finish":"polished","dimensions":"M10 x 60mm","grade":"A2-70","pack_size":50}'),
        ('HW-WIRE',   'HW-WIRE-01',   'THHN Building Wire / 12 AWG 100m',          45,  92,  30, 60,  110, '{"product_type":"electrical","material":"copper","voltage":"600V","certification":"UL","dimensions":"12 AWG","pack_size":1}'),
        ('HW-WIRE',   'HW-WIRE-02',   'THHN Building Wire / 10 AWG 100m',          62,  124, 38, 45,  85,  '{"product_type":"electrical","material":"copper","voltage":"600V","certification":"UL","dimensions":"10 AWG","pack_size":1}'),
        ('HW-PIPE',   'HW-PIPE-01',   'PVC Pressure Pipe / 25mm Class 9',          8,   21,  18, 120, 200, '{"product_type":"plumbing","material":"pvc","dimensions":"25mm","grade":"Class 9","certification":"ISI","pack_size":1}'),
        ('HW-PIPE',   'HW-PIPE-02',   'PVC Pressure Pipe / 50mm Class 12',         15,  36,  24, 80,  140, '{"product_type":"plumbing","material":"pvc","dimensions":"50mm","grade":"Class 12","certification":"ISI","pack_size":1}'),
        ('HW-CEMENT', 'HW-CEMENT-01', 'Rapid-Set Cement 25kg / Standard',          9,   19,  16, 150, 260, '{"product_type":"building_material","material":"portland_cement","grade":"43","pack_size":1}'),
        ('HW-CEMENT', 'HW-CEMENT-02', 'Rapid-Set Cement 25kg / High-Early',        12,  26,  20, 100, 180, '{"product_type":"building_material","material":"portland_cement","grade":"53","pack_size":1}'),
        ('HW-PPE',    'HW-PPE-01',    'Industrial Safety Helmet / Vented White',   6,   16,  14, 180, 300, '{"product_type":"safety","material":"hdpe","finish":"gloss","certification":"EN397","pack_size":1}'),
        ('HW-PPE',    'HW-PPE-02',    'Industrial Safety Helmet / Hi-Vis Orange',  7,   18,  17, 140, 240, '{"product_type":"safety","material":"hdpe","finish":"hi_vis","certification":"EN397","pack_size":1}')
    ) AS v(external_id, sku_code, description, unit_cost, unit_price, lead_time, safety, reorder, attrs)
    JOIN products pr
      ON pr.tenant_id = v_tenant_id
     AND pr.external_id = v.external_id
     AND pr.industry = 'hardware'::industry_code
    ON CONFLICT (tenant_id, sku_code) DO NOTHING;

    -- Seed warehouse stock so coverage / shortage / cost insights run on real positions.
    INSERT INTO inventory_levels (
        tenant_id, sku_id, industry, location, on_hand_units, inbound_units, source
    )
    SELECT s.tenant_id, s.id, s.industry, 'default',
           GREATEST(
               0,
               ROUND(
                   (COALESCE(s.reorder_point, 0) + COALESCE(s.safety_stock, 0))
                   * (0.4 + (abs(hashtext(s.id::text)) % 260) / 100.0)
               )
           ),
           0, 'seed'
    FROM skus s
    WHERE s.tenant_id = v_tenant_id
      AND s.industry = 'hardware'::industry_code
    ON CONFLICT (tenant_id, sku_id, location) DO NOTHING;

    RAISE NOTICE 'Hardware added + demo catalog seeded for dev tenant %', v_tenant_id;
END;
$$;
