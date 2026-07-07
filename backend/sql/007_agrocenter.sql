-- SANKET Phase 8: Agrocenter industry
-- Adds the agrocenter vertical (pesticides, feed, fertilizers).
-- Apply against a running database: see instructions below.
--
-- Docker:  docker compose exec postgres psql -U sanket_app -d sanket -f /docker-entrypoint-initdb.d/007_agrocenter.sql
-- Local:   psql postgresql://sanket_app:changeme@localhost:5432/sanket -f backend/sql/007_agrocenter.sql

-- ─────────────────────────────────────────
-- 1. Extend the ENUM
--    ALTER TYPE ... ADD VALUE cannot run inside a transaction block.
--    Run this file outside of BEGIN/COMMIT (psql does this by default).
-- ─────────────────────────────────────────
ALTER TYPE industry_code ADD VALUE IF NOT EXISTS 'agrocenter';

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
-- 3. Update dev tenant + add industry profile
-- ─────────────────────────────────────────
DO $$
DECLARE
    v_tenant_id UUID;
BEGIN
    SET LOCAL app.current_tenant_id = '';

    SELECT id INTO v_tenant_id FROM tenants WHERE slug = 'sanket-dev';

    IF v_tenant_id IS NOT NULL THEN
        -- Add agrocenter to the tenant's industry list (only if not already present)
        UPDATE tenants
        SET industries = array_append(industries, 'agrocenter'::industry_code),
            updated_at = now()
        WHERE id = v_tenant_id
          AND NOT ('agrocenter'::industry_code = ANY(industries));

        -- Add per-tenant industry profile
        INSERT INTO industry_profiles (tenant_id, industry, model_overrides, feature_flags)
        VALUES (v_tenant_id, 'agrocenter', '{}', '{"seasonal_replenishment": true, "weather_signals": true, "input_coverage": true}')
        ON CONFLICT (tenant_id, industry) DO NOTHING;

        RAISE NOTICE 'Agrocenter added to dev tenant %', v_tenant_id;
    ELSE
        RAISE NOTICE 'Dev tenant not found — skipping tenant update';
    END IF;
END;
$$;
