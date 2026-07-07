-- SANKET Platform — Seed Data
-- Industry definitions and a dev tenant with sample users.
-- Run AFTER 003_rls_policies.sql.
-- In production, replace the dev tenant block with real onboarding.

-- ─────────────────────────────────────────
-- INDUSTRIES
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
) VALUES
(
    'fashion',
    'Apparel & Fashion',
    26,
    ARRAY['size','color','channel','region'],
    ARRAY['trend_search','social_sentiment','weather','competitor_price']::signal_type[],
    '{
        "size":        {"type": "string", "enum": ["XS","S","M","L","XL","XXL","XXXL"]},
        "color":       {"type": "string"},
        "material":    {"type": "string"},
        "season":      {"type": "string", "enum": ["SS","FW","AW","Cruise","Resort"]},
        "gender":      {"type": "string", "enum": ["mens","womens","unisex","kids"]},
        "care_label":  {"type": "string"},
        "country_of_origin": {"type": "string"}
    }'::jsonb,
    ARRAY['TimesFM','TFT','N-HiTS','LightGBM','Croston'],
    ARRAY['OR-Tools','RLlib-replenishment'],
    'standard'
),
(
    'electronics',
    'Consumer Electronics',
    12,
    ARRAY['model_year','channel','region','warranty_tier'],
    ARRAY['trend_search','competitor_price','logistics_disruption','macro_economic']::signal_type[],
    '{
        "model_year":     {"type": "integer"},
        "specs":          {"type": "object"},
        "warranty_months":{"type": "integer"},
        "component_ids":  {"type": "array", "items": {"type": "string"}},
        "energy_class":   {"type": "string"},
        "connectivity":   {"type": "array", "items": {"type": "string"}},
        "color_finish":   {"type": "string"}
    }'::jsonb,
    ARRAY['TimesFM','DeepAR','TFT','LightGBM','Chronos'],
    ARRAY['OR-Tools','RLlib-replenishment','causal-DoWhy'],
    'standard'
),
(
    'pharma',
    'Pharmaceuticals',
    52,
    ARRAY['ndc','channel','region','cold_chain'],
    ARRAY['regulatory','macro_economic','logistics_disruption','supplier_lead']::signal_type[],
    '{
        "ndc_code":           {"type": "string"},
        "dosage_form":        {"type": "string"},
        "strength":           {"type": "string"},
        "route_of_admin":     {"type": "string"},
        "controlled_substance":{"type": "boolean"},
        "therapeutic_class":  {"type": "string"},
        "requires_rx":        {"type": "boolean"},
        "storage_class":      {"type": "string", "enum": ["ambient","refrigerated","frozen","controlled_room"]}
    }'::jsonb,
    ARRAY['TFT','Croston','N-HiTS','LightGBM','Chronos'],
    ARRAY['OR-Tools','safety-stock-optimizer'],
    'gxp'
),
(
    'agrocenter',
    'Agrocenter & Farm Inputs',
    26,
    ARRAY['crop_type','region','channel','season'],
    ARRAY['weather','macro_economic','regulatory','supplier_lead']::signal_type[],
    '{
        "product_type":            {"type": "string", "enum": ["pesticide","feed","fertilizer","seed","equipment"]},
        "active_ingredient":       {"type": "string"},
        "application_method":      {"type": "string", "enum": ["foliar","soil","broadcast","drip","manual"]},
        "crop_type":               {"type": "string"},
        "storage_class":           {"type": "string", "enum": ["ambient","cool_dry","flammable","refrigerated"]},
        "regulatory_registration": {"type": "string"},
        "pack_size_kg":            {"type": "integer"}
    }'::jsonb,
    ARRAY['TimesFM','TFT','N-HiTS','LightGBM','Chronos'],
    ARRAY['OR-Tools','safety-stock-optimizer','seasonal-replenishment'],
    'standard'
),
(
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
-- DEV TENANT  (remove / replace for production)
-- ─────────────────────────────────────────

DO $$
DECLARE
    v_tenant_id UUID;
    v_owner_id  UUID;
    v_admin_id  UUID;
BEGIN
    -- Bypass RLS for seed operations
    SET LOCAL app.current_tenant_id = '';

    INSERT INTO tenants (
        slug, display_name, tier, status,
        industries, active_industry,
        max_skus, max_users, data_retention_days
    ) VALUES (
        'sanket-dev',
        'SANKET Dev Tenant',
        'enterprise',
        'active',
        ARRAY['fashion','electronics','pharma','agrocenter','hardware']::industry_code[],
        'fashion',
        999999,
        50,
        1825
    )
    ON CONFLICT (slug) DO UPDATE SET updated_at = now()
    RETURNING id INTO v_tenant_id;

    -- Owner account — password: Dev@Sanket2024!
    INSERT INTO users (
        tenant_id, email, password_hash, full_name, role, active_industry
    ) VALUES (
        v_tenant_id,
        'owner@sanket-dev.com',
        '$argon2id$v=19$m=65536,t=3,p=4$7n2vNea8F4KwlvIeY4wRYg$V3rq91v0e5q8kwuyIA0N1uG+e4rDECKJcTlql2ZQe1Y',
        'Platform Owner',
        'owner',
        'fashion'
    )
    ON CONFLICT (tenant_id, email) DO UPDATE SET password_hash = EXCLUDED.password_hash, updated_at = now()
    RETURNING id INTO v_owner_id;

    -- Admin account — password: Dev@Sanket2024!
    INSERT INTO users (
        tenant_id, email, password_hash, full_name, role, active_industry
    ) VALUES (
        v_tenant_id,
        'admin@sanket-dev.com',
        '$argon2id$v=19$m=65536,t=3,p=4$7n2vNea8F4KwlvIeY4wRYg$V3rq91v0e5q8kwuyIA0N1uG+e4rDECKJcTlql2ZQe1Y',
        'Platform Admin',
        'admin',
        'fashion'
    )
    ON CONFLICT (tenant_id, email) DO UPDATE SET password_hash = EXCLUDED.password_hash, updated_at = now()
    RETURNING id INTO v_admin_id;

    -- Per-industry profiles with default settings
    INSERT INTO industry_profiles (tenant_id, industry, model_overrides, feature_flags)
    VALUES
        (v_tenant_id, 'fashion',     '{}', '{"markdown_optimizer": true, "assortment_planning": true}'),
        (v_tenant_id, 'electronics', '{}', '{"component_risk": true, "competitor_tracking": true}'),
        (v_tenant_id, 'pharma',      '{}', '{"gxp_mode": true, "shortage_alerts": true, "batch_tracking": true}'),
        (v_tenant_id, 'agrocenter',  '{}', '{"seasonal_replenishment": true, "weather_signals": true, "input_coverage": true}'),
        (v_tenant_id, 'hardware',    '{}', '{"supply_risk": true, "competitor_tracking": true, "safety_stock_optimizer": true}')
    ON CONFLICT (tenant_id, industry) DO NOTHING;

    RAISE NOTICE 'Dev tenant seeded: tenant_id=%, owner_id=%', v_tenant_id, v_owner_id;
END;
$$;
