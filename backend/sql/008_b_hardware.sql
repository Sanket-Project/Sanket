-- SANKET Phase 8: Hardware & Industrial Supply industry
-- Adds the hardware vertical (tools, fasteners, electrical, plumbing,
-- building materials, safety). No catalog is seeded: products come from real imports.
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
-- 3. Update dev tenant + add industry profile
-- ─────────────────────────────────────────
DO $$
DECLARE
    v_tenant_id UUID;
BEGIN
    SELECT id INTO v_tenant_id FROM tenants WHERE slug = 'sanket-dev';

    IF v_tenant_id IS NULL THEN
        RAISE NOTICE 'Dev tenant not found — skipping tenant update';
        RETURN;
    END IF;

    -- Bypass RLS for the tenant-list update.
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

    RAISE NOTICE 'Hardware added for dev tenant %', v_tenant_id;
END;
$$;
