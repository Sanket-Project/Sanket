-- SANKET Platform — Full demo catalog + ground-truth transactional history
-- Fills the gap identified during QA: only the Hardware vertical had demo
-- products/SKUs (008_b_hardware.sql), and NO industry had historical_sales,
-- so Sales Analytics, Forecast Accuracy (MAPE/WAPE vs ground truth), and the
-- Pharma compliance snapshot all had nothing real to compute against.
--
-- This script is idempotent per-tenant: each catalog block only inserts if
-- that industry has no products yet for the tenant, and the historical_sales
-- block only inserts if the tenant has none yet — safe to re-run.
--
-- Apply against the running dev stack (no rebuild needed — backend/sql is
-- live bind-mounted into the postgres container):
--
--   docker compose exec postgres psql -U sanket_app -d sanket \
--     -f /docker-entrypoint-initdb.d/010_full_demo_data.sql
--
-- Local:  psql postgresql://sanket_app:changeme@localhost:5432/sanket \
--           -f backend/sql/010_full_demo_data.sql

DO $$
DECLARE
    v_tenant_id UUID;
BEGIN
    SELECT id INTO v_tenant_id FROM tenants WHERE slug = 'sanket-dev';

    IF v_tenant_id IS NULL THEN
        RAISE NOTICE 'Dev tenant not found — skipping demo data seed';
        RETURN;
    END IF;

    -- Scope subsequent inserts to the tenant so RLS policies pass.
    PERFORM set_config('app.current_tenant_id', v_tenant_id::text, true);

    -- ═══════════════════════════════════════════════════════════════
    -- FASHION — products + SKUs
    -- ═══════════════════════════════════════════════════════════════
    IF NOT EXISTS (
        SELECT 1 FROM products WHERE tenant_id = v_tenant_id AND industry = 'fashion'::industry_code
    ) THEN
        INSERT INTO products (id, tenant_id, industry, external_id, name, brand, category, status, attributes)
        SELECT gen_random_uuid(), v_tenant_id, 'fashion'::industry_code, p.external_id, p.name, 'SANKET Demo', p.category, 'active', '{}'::jsonb
        FROM (VALUES
            ('FA-TSHIRT', 'Classic Cotton T-Shirt', 'Tops'),
            ('FA-JEANS',  'Slim Fit Jeans',          'Bottoms'),
            ('FA-JACKET', 'Windbreaker Jacket',      'Outerwear'),
            ('FA-SNEAKER','Court Sneakers',          'Footwear')
        ) AS p(external_id, name, category)
        ON CONFLICT (tenant_id, external_id) WHERE external_id IS NOT NULL DO NOTHING;

        INSERT INTO skus (id, tenant_id, product_id, industry, sku_code, description, unit_cost, unit_price, lead_time_days, moq, safety_stock, reorder_point, attributes, is_active)
        SELECT gen_random_uuid(), v_tenant_id, pr.id, 'fashion'::industry_code, v.sku_code, v.description,
               v.unit_cost, v.unit_price, v.lead_time, 1, v.safety, v.reorder, v.attrs::jsonb, true
        FROM (VALUES
            ('FA-TSHIRT', 'FA-TSHIRT-01', 'Classic Cotton T-Shirt / M / White', 4,  19, 14, 150, 260, '{"size":"M","color":"White","material":"cotton","season":"SS","gender":"unisex","care_label":"machine wash cold","country_of_origin":"India"}'),
            ('FA-TSHIRT', 'FA-TSHIRT-02', 'Classic Cotton T-Shirt / L / Black', 4,  19, 14, 140, 240, '{"size":"L","color":"Black","material":"cotton","season":"SS","gender":"unisex","care_label":"machine wash cold","country_of_origin":"India"}'),
            ('FA-JEANS',  'FA-JEANS-01',  'Slim Fit Jeans / 32 / Indigo',        14, 49, 21, 90,  150, '{"size":"32","color":"Indigo","material":"denim","season":"FW","gender":"mens","care_label":"wash inside out","country_of_origin":"Bangladesh"}'),
            ('FA-JEANS',  'FA-JEANS-02',  'Slim Fit Jeans / 34 / Black',         14, 49, 21, 85,  140, '{"size":"34","color":"Black","material":"denim","season":"FW","gender":"mens","care_label":"wash inside out","country_of_origin":"Bangladesh"}'),
            ('FA-JACKET', 'FA-JACKET-01', 'Windbreaker Jacket / M / Navy',       22, 79, 28, 60,  100, '{"size":"M","color":"Navy","material":"nylon","season":"AW","gender":"unisex","care_label":"do not tumble dry","country_of_origin":"Vietnam"}'),
            ('FA-JACKET', 'FA-JACKET-02', 'Windbreaker Jacket / L / Olive',      22, 79, 28, 55,  95,  '{"size":"L","color":"Olive","material":"nylon","season":"AW","gender":"unisex","care_label":"do not tumble dry","country_of_origin":"Vietnam"}'),
            ('FA-SNEAKER','FA-SNEAKER-01','Court Sneakers / US9 / White',        26, 89, 35, 70,  120, '{"size":"US9","color":"White","material":"leather","season":"Cruise","gender":"mens","care_label":"wipe clean","country_of_origin":"China"}'),
            ('FA-SNEAKER','FA-SNEAKER-02','Court Sneakers / US10 / Black',       26, 89, 35, 65,  110, '{"size":"US10","color":"Black","material":"leather","season":"Cruise","gender":"mens","care_label":"wipe clean","country_of_origin":"China"}')
        ) AS v(external_id, sku_code, description, unit_cost, unit_price, lead_time, safety, reorder, attrs)
        JOIN products pr ON pr.tenant_id = v_tenant_id AND pr.external_id = v.external_id AND pr.industry = 'fashion'::industry_code
        ON CONFLICT (tenant_id, sku_code) DO NOTHING;
    END IF;

    -- ═══════════════════════════════════════════════════════════════
    -- ELECTRONICS — products + SKUs
    -- ═══════════════════════════════════════════════════════════════
    IF NOT EXISTS (
        SELECT 1 FROM products WHERE tenant_id = v_tenant_id AND industry = 'electronics'::industry_code
    ) THEN
        INSERT INTO products (id, tenant_id, industry, external_id, name, brand, category, status, attributes)
        SELECT gen_random_uuid(), v_tenant_id, 'electronics'::industry_code, p.external_id, p.name, 'SANKET Demo', p.category, 'active', '{}'::jsonb
        FROM (VALUES
            ('EL-HEADPHONE', 'Wireless ANC Headphones',  'Audio'),
            ('EL-SMARTWATCH','Fitness Smartwatch',        'Wearables'),
            ('EL-SPEAKER',   'Portable Bluetooth Speaker','Audio'),
            ('EL-LAPTOP',    '14-inch Ultrabook',         'Computing')
        ) AS p(external_id, name, category)
        ON CONFLICT (tenant_id, external_id) WHERE external_id IS NOT NULL DO NOTHING;

        INSERT INTO skus (id, tenant_id, product_id, industry, sku_code, description, unit_cost, unit_price, lead_time_days, moq, safety_stock, reorder_point, attributes, is_active)
        SELECT gen_random_uuid(), v_tenant_id, pr.id, 'electronics'::industry_code, v.sku_code, v.description,
               v.unit_cost, v.unit_price, v.lead_time, 1, v.safety, v.reorder, v.attrs::jsonb, true
        FROM (VALUES
            ('EL-HEADPHONE', 'EL-HEADPHONE-01', 'Wireless ANC Headphones / Black',  58,  149, 45, 80, 140, '{"model_year":2025,"warranty_months":24,"energy_class":"n/a","connectivity":["bluetooth5.3"],"color_finish":"matte black"}'),
            ('EL-HEADPHONE', 'EL-HEADPHONE-02', 'Wireless ANC Headphones / Silver', 58,  149, 45, 70, 120, '{"model_year":2025,"warranty_months":24,"energy_class":"n/a","connectivity":["bluetooth5.3"],"color_finish":"silver"}'),
            ('EL-SMARTWATCH','EL-SMARTWATCH-01','Fitness Smartwatch / 42mm',        62,  179, 38, 60, 100, '{"model_year":2025,"warranty_months":12,"energy_class":"n/a","connectivity":["bluetooth","gps"],"color_finish":"graphite"}'),
            ('EL-SMARTWATCH','EL-SMARTWATCH-02','Fitness Smartwatch / 46mm',        68,  199, 38, 55, 90,  '{"model_year":2025,"warranty_months":12,"energy_class":"n/a","connectivity":["bluetooth","gps"],"color_finish":"titanium"}'),
            ('EL-SPEAKER',   'EL-SPEAKER-01',   'Portable Bluetooth Speaker / Blue',24,  69,  30, 100,180, '{"model_year":2024,"warranty_months":12,"energy_class":"n/a","connectivity":["bluetooth5.0"],"color_finish":"blue"}'),
            ('EL-SPEAKER',   'EL-SPEAKER-02',   'Portable Bluetooth Speaker / Red', 24,  69,  30, 95, 170, '{"model_year":2024,"warranty_months":12,"energy_class":"n/a","connectivity":["bluetooth5.0"],"color_finish":"red"}'),
            ('EL-LAPTOP',    'EL-LAPTOP-01',    '14-inch Ultrabook / 8GB/256GB',    420, 899, 52, 25, 45,  '{"model_year":2025,"warranty_months":36,"energy_class":"A","connectivity":["wifi6","usb-c"],"color_finish":"space gray"}'),
            ('EL-LAPTOP',    'EL-LAPTOP-02',    '14-inch Ultrabook / 16GB/512GB',   540, 1099,52, 20, 35,  '{"model_year":2025,"warranty_months":36,"energy_class":"A","connectivity":["wifi6","usb-c"],"color_finish":"silver"}')
        ) AS v(external_id, sku_code, description, unit_cost, unit_price, lead_time, safety, reorder, attrs)
        JOIN products pr ON pr.tenant_id = v_tenant_id AND pr.external_id = v.external_id AND pr.industry = 'electronics'::industry_code
        ON CONFLICT (tenant_id, sku_code) DO NOTHING;
    END IF;

    -- ═══════════════════════════════════════════════════════════════
    -- PHARMA — products + SKUs
    -- ═══════════════════════════════════════════════════════════════
    IF NOT EXISTS (
        SELECT 1 FROM products WHERE tenant_id = v_tenant_id AND industry = 'pharma'::industry_code
    ) THEN
        INSERT INTO products (id, tenant_id, industry, external_id, name, brand, category, status, attributes)
        SELECT gen_random_uuid(), v_tenant_id, 'pharma'::industry_code, p.external_id, p.name, 'SANKET Demo Pharma', p.category, 'active', '{}'::jsonb
        FROM (VALUES
            ('PH-AMOX',    'Amoxicillin 500mg Capsules',      'Antibiotics'),
            ('PH-IBU',     'Ibuprofen 200mg Tablets',         'Analgesics'),
            ('PH-INSULIN', 'Insulin Glargine Injection',      'Diabetes Care'),
            ('PH-VITC',    'Vitamin C 1000mg Tablets',        'Supplements')
        ) AS p(external_id, name, category)
        ON CONFLICT (tenant_id, external_id) WHERE external_id IS NOT NULL DO NOTHING;

        INSERT INTO skus (id, tenant_id, product_id, industry, sku_code, description, unit_cost, unit_price, lead_time_days, moq, safety_stock, reorder_point, attributes, is_active)
        SELECT gen_random_uuid(), v_tenant_id, pr.id, 'pharma'::industry_code, v.sku_code, v.description,
               v.unit_cost, v.unit_price, v.lead_time, 1, v.safety, v.reorder, v.attrs::jsonb, true
        FROM (VALUES
            ('PH-AMOX',    'PH-AMOX-01',    'Amoxicillin 500mg / Bottle of 30',   3.2, 9.5,  20, 300, 500, '{"ndc_code":"00000-1001-30","dosage_form":"capsule","strength":"500mg","route_of_admin":"oral","controlled_substance":false,"therapeutic_class":"antibiotic","requires_rx":true,"storage_class":"ambient"}'),
            ('PH-AMOX',    'PH-AMOX-02',    'Amoxicillin 500mg / Bottle of 100',  9.8, 26.0, 20, 150, 260, '{"ndc_code":"00000-1001-100","dosage_form":"capsule","strength":"500mg","route_of_admin":"oral","controlled_substance":false,"therapeutic_class":"antibiotic","requires_rx":true,"storage_class":"ambient"}'),
            ('PH-IBU',     'PH-IBU-01',     'Ibuprofen 200mg / Bottle of 50',     1.4, 5.5,  14, 400, 650, '{"ndc_code":"00000-2002-50","dosage_form":"tablet","strength":"200mg","route_of_admin":"oral","controlled_substance":false,"therapeutic_class":"nsaid","requires_rx":false,"storage_class":"ambient"}'),
            ('PH-IBU',     'PH-IBU-02',     'Ibuprofen 200mg / Bottle of 200',    4.6, 15.0, 14, 220, 380, '{"ndc_code":"00000-2002-200","dosage_form":"tablet","strength":"200mg","route_of_admin":"oral","controlled_substance":false,"therapeutic_class":"nsaid","requires_rx":false,"storage_class":"ambient"}'),
            ('PH-INSULIN', 'PH-INSULIN-01', 'Insulin Glargine / 10mL Vial',       18.0,52.0, 30, 100, 180, '{"ndc_code":"00000-3003-10","dosage_form":"injection","strength":"100units/mL","route_of_admin":"subcutaneous","controlled_substance":false,"therapeutic_class":"antidiabetic","requires_rx":true,"storage_class":"refrigerated"}'),
            ('PH-INSULIN', 'PH-INSULIN-02', 'Insulin Glargine / 3mL Pen (5-pack)',26.0,72.0, 30, 80,  140, '{"ndc_code":"00000-3003-3","dosage_form":"injection","strength":"100units/mL","route_of_admin":"subcutaneous","controlled_substance":false,"therapeutic_class":"antidiabetic","requires_rx":true,"storage_class":"refrigerated"}'),
            ('PH-VITC',    'PH-VITC-01',    'Vitamin C 1000mg / Bottle of 60',    1.1, 6.0,  10, 350, 600, '{"ndc_code":"00000-4004-60","dosage_form":"tablet","strength":"1000mg","route_of_admin":"oral","controlled_substance":false,"therapeutic_class":"supplement","requires_rx":false,"storage_class":"ambient"}'),
            ('PH-VITC',    'PH-VITC-02',    'Vitamin C 1000mg / Bottle of 120',   2.0, 10.5, 10, 260, 440, '{"ndc_code":"00000-4004-120","dosage_form":"tablet","strength":"1000mg","route_of_admin":"oral","controlled_substance":false,"therapeutic_class":"supplement","requires_rx":false,"storage_class":"ambient"}')
        ) AS v(external_id, sku_code, description, unit_cost, unit_price, lead_time, safety, reorder, attrs)
        JOIN products pr ON pr.tenant_id = v_tenant_id AND pr.external_id = v.external_id AND pr.industry = 'pharma'::industry_code
        ON CONFLICT (tenant_id, sku_code) DO NOTHING;
    END IF;

    -- ═══════════════════════════════════════════════════════════════
    -- AGROCENTER — products + SKUs
    -- ═══════════════════════════════════════════════════════════════
    IF NOT EXISTS (
        SELECT 1 FROM products WHERE tenant_id = v_tenant_id AND industry = 'agrocenter'::industry_code
    ) THEN
        INSERT INTO products (id, tenant_id, industry, external_id, name, brand, category, status, attributes)
        SELECT gen_random_uuid(), v_tenant_id, 'agrocenter'::industry_code, p.external_id, p.name, 'SANKET Demo Agro', p.category, 'active', '{}'::jsonb
        FROM (VALUES
            ('AG-FERT', 'NPK 20-20-20 Fertilizer',   'Fertilizer'),
            ('AG-PEST', 'Broad-Spectrum Pesticide',  'Pesticide'),
            ('AG-SEED', 'Hybrid Corn Seed',          'Seed'),
            ('AG-FEED', 'Poultry Feed Pellets',      'Feed')
        ) AS p(external_id, name, category)
        ON CONFLICT (tenant_id, external_id) WHERE external_id IS NOT NULL DO NOTHING;

        INSERT INTO skus (id, tenant_id, product_id, industry, sku_code, description, unit_cost, unit_price, lead_time_days, moq, safety_stock, reorder_point, attributes, is_active)
        SELECT gen_random_uuid(), v_tenant_id, pr.id, 'agrocenter'::industry_code, v.sku_code, v.description,
               v.unit_cost, v.unit_price, v.lead_time, 1, v.safety, v.reorder, v.attrs::jsonb, true
        FROM (VALUES
            ('AG-FERT', 'AG-FERT-01', 'NPK 20-20-20 / 25kg bag',        14, 32, 21, 200, 340, '{"product_type":"fertilizer","active_ingredient":"NPK","application_method":"broadcast","crop_type":"general","storage_class":"cool_dry","regulatory_registration":"REG-AG-001","pack_size_kg":25}'),
            ('AG-FERT', 'AG-FERT-02', 'NPK 20-20-20 / 50kg bag',        26, 58, 21, 120, 210, '{"product_type":"fertilizer","active_ingredient":"NPK","application_method":"broadcast","crop_type":"general","storage_class":"cool_dry","regulatory_registration":"REG-AG-001","pack_size_kg":50}'),
            ('AG-PEST', 'AG-PEST-01', 'Broad-Spectrum Pesticide / 1L',  8,  22, 18, 180, 300, '{"product_type":"pesticide","active_ingredient":"glyphosate","application_method":"foliar","crop_type":"row_crops","storage_class":"flammable","regulatory_registration":"REG-AG-014","pack_size_kg":1}'),
            ('AG-PEST', 'AG-PEST-02', 'Broad-Spectrum Pesticide / 5L',  32, 79, 18, 90,  150, '{"product_type":"pesticide","active_ingredient":"glyphosate","application_method":"foliar","crop_type":"row_crops","storage_class":"flammable","regulatory_registration":"REG-AG-014","pack_size_kg":5}'),
            ('AG-SEED', 'AG-SEED-01', 'Hybrid Corn Seed / 25kg bag',    40, 95, 45, 60,  110, '{"product_type":"seed","active_ingredient":"n/a","application_method":"drip","crop_type":"corn","storage_class":"ambient","regulatory_registration":"REG-AG-027","pack_size_kg":25}'),
            ('AG-SEED', 'AG-SEED-02', 'Hybrid Corn Seed / 50kg bag',    76, 175,45, 40,  80,  '{"product_type":"seed","active_ingredient":"n/a","application_method":"drip","crop_type":"corn","storage_class":"ambient","regulatory_registration":"REG-AG-027","pack_size_kg":50}'),
            ('AG-FEED', 'AG-FEED-01', 'Poultry Feed Pellets / 25kg bag',11, 24, 12, 220, 380, '{"product_type":"feed","active_ingredient":"n/a","application_method":"manual","crop_type":"n/a","storage_class":"cool_dry","regulatory_registration":"REG-AG-041","pack_size_kg":25}'),
            ('AG-FEED', 'AG-FEED-02', 'Poultry Feed Pellets / 50kg bag',20, 44, 12, 130, 230, '{"product_type":"feed","active_ingredient":"n/a","application_method":"manual","crop_type":"n/a","storage_class":"cool_dry","regulatory_registration":"REG-AG-041","pack_size_kg":50}')
        ) AS v(external_id, sku_code, description, unit_cost, unit_price, lead_time, safety, reorder, attrs)
        JOIN products pr ON pr.tenant_id = v_tenant_id AND pr.external_id = v.external_id AND pr.industry = 'agrocenter'::industry_code
        ON CONFLICT (tenant_id, sku_code) DO NOTHING;
    END IF;

    -- ═══════════════════════════════════════════════════════════════
    -- INVENTORY LEVELS — cover any SKU (any industry) that has none yet
    -- ═══════════════════════════════════════════════════════════════
    INSERT INTO inventory_levels (tenant_id, sku_id, industry, location, on_hand_units, inbound_units, source)
    SELECT
        s.tenant_id, s.id, s.industry, 'default',
        GREATEST(
            0,
            ROUND(
                (COALESCE(s.reorder_point, 0) + COALESCE(s.safety_stock, 0))
                * (0.4 + (abs(hashtext(s.id::text)) % 260) / 100.0)
            )
        ),
        ROUND((abs(hashtext(s.id::text || 'in')) % 40)),
        'seed'
    FROM skus s
    WHERE s.tenant_id = v_tenant_id
    ON CONFLICT (tenant_id, sku_id, location) DO NOTHING;

    -- ═══════════════════════════════════════════════════════════════
    -- PHARMA BATCHES — GxP status mix (released/quarantine/rejected/
    -- recalled/expired) with realistic expiry spread, so the Pharma
    -- compliance snapshot and expiry timeline show real data.
    -- ═══════════════════════════════════════════════════════════════
    IF NOT EXISTS (SELECT 1 FROM pharma_batches WHERE tenant_id = v_tenant_id) THEN
        -- Healthy released batches, expiry ~150-210 days out.
        INSERT INTO pharma_batches (
            id, tenant_id, sku_id, lot_number, ndc_code, manufactured_at, expiry_date,
            quantity_produced, quantity_remaining, gxp_status, cold_chain_required,
            storage_temp_min_c, storage_temp_max_c, qa_released_by, qa_released_at, metadata
        )
        SELECT
            gen_random_uuid(), s.tenant_id, s.id,
            'LOT-' || upper(replace(s.sku_code, '-', '')) || '-' || to_char(CURRENT_DATE, 'YYMM') || '-A',
            s.attributes->>'ndc_code',
            CURRENT_DATE - INTERVAL '30 days',
            CURRENT_DATE + (150 + (abs(hashtext(s.id::text || 'a')) % 60)) * INTERVAL '1 day',
            1000, ROUND(1000 * (0.5 + (abs(hashtext(s.id::text || 'qa')) % 40) / 100.0)),
            'released'::gxp_batch_status,
            (s.attributes->>'storage_class') = 'refrigerated',
            CASE WHEN (s.attributes->>'storage_class') = 'refrigerated' THEN 2 ELSE NULL END,
            CASE WHEN (s.attributes->>'storage_class') = 'refrigerated' THEN 8 ELSE NULL END,
            NULL, now() - INTERVAL '20 days', '{}'::jsonb
        FROM skus s
        WHERE s.tenant_id = v_tenant_id AND s.industry = 'pharma'::industry_code;

        -- Critical-expiry released batches (<30 days), so the expiry
        -- timeline / insight callout has something urgent to surface.
        INSERT INTO pharma_batches (
            id, tenant_id, sku_id, lot_number, ndc_code, manufactured_at, expiry_date,
            quantity_produced, quantity_remaining, gxp_status, cold_chain_required,
            storage_temp_min_c, storage_temp_max_c, qa_released_by, qa_released_at, metadata
        )
        SELECT
            gen_random_uuid(), s.tenant_id, s.id,
            'LOT-' || upper(replace(s.sku_code, '-', '')) || '-' || to_char(CURRENT_DATE, 'YYMM') || '-B',
            s.attributes->>'ndc_code',
            CURRENT_DATE - INTERVAL '340 days',
            CURRENT_DATE + (5 + (abs(hashtext(s.id::text || 'b')) % 25)) * INTERVAL '1 day',
            500, ROUND(500 * (0.2 + (abs(hashtext(s.id::text || 'qb')) % 30) / 100.0)),
            'released'::gxp_batch_status,
            (s.attributes->>'storage_class') = 'refrigerated',
            CASE WHEN (s.attributes->>'storage_class') = 'refrigerated' THEN 2 ELSE NULL END,
            CASE WHEN (s.attributes->>'storage_class') = 'refrigerated' THEN 8 ELSE NULL END,
            NULL, now() - INTERVAL '300 days', '{}'::jsonb
        FROM skus s
        WHERE s.tenant_id = v_tenant_id AND s.industry = 'pharma'::industry_code
        AND (abs(hashtext(s.id::text)) % 2 = 0);  -- roughly half the SKUs

        -- In-quarantine batches awaiting QA release.
        INSERT INTO pharma_batches (
            id, tenant_id, sku_id, lot_number, ndc_code, manufactured_at, expiry_date,
            quantity_produced, quantity_remaining, gxp_status, cold_chain_required,
            storage_temp_min_c, storage_temp_max_c, metadata
        )
        SELECT
            gen_random_uuid(), s.tenant_id, s.id,
            'LOT-' || upper(replace(s.sku_code, '-', '')) || '-' || to_char(CURRENT_DATE, 'YYMM') || '-Q',
            s.attributes->>'ndc_code',
            CURRENT_DATE - INTERVAL '5 days',
            CURRENT_DATE + INTERVAL '365 days',
            800, 800,
            'quarantine'::gxp_batch_status,
            (s.attributes->>'storage_class') = 'refrigerated',
            CASE WHEN (s.attributes->>'storage_class') = 'refrigerated' THEN 2 ELSE NULL END,
            CASE WHEN (s.attributes->>'storage_class') = 'refrigerated' THEN 8 ELSE NULL END,
            '{}'::jsonb
        FROM skus s
        WHERE s.tenant_id = v_tenant_id AND s.industry = 'pharma'::industry_code;

        -- A couple of non-conforming batches (rejected/recalled/expired)
        -- so the compliance snapshot's third bucket isn't always zero.
        INSERT INTO pharma_batches (
            id, tenant_id, sku_id, lot_number, ndc_code, manufactured_at, expiry_date,
            quantity_produced, quantity_remaining, gxp_status, cold_chain_required, recall_reason, recalled_at, metadata
        )
        SELECT
            gen_random_uuid(), s.tenant_id, s.id,
            'LOT-' || upper(replace(s.sku_code, '-', '')) || '-' || to_char(CURRENT_DATE, 'YYMM') || '-R',
            s.attributes->>'ndc_code',
            CURRENT_DATE - INTERVAL '200 days',
            CURRENT_DATE + INTERVAL '100 days',
            300, 300,
            (ARRAY['rejected','recalled','expired']::gxp_batch_status[])[1 + (abs(hashtext(s.id::text || 'r')) % 3)],
            false,
            CASE WHEN (abs(hashtext(s.id::text || 'r')) % 3) = 1 THEN 'Potency out of spec on stability testing' ELSE NULL END,
            CASE WHEN (abs(hashtext(s.id::text || 'r')) % 3) = 1 THEN now() - INTERVAL '10 days' ELSE NULL END,
            '{}'::jsonb
        FROM skus s
        WHERE s.tenant_id = v_tenant_id AND s.industry = 'pharma'::industry_code
        AND (abs(hashtext(s.id::text)) % 3 = 0);  -- roughly a third of SKUs
    END IF;

    -- ═══════════════════════════════════════════════════════════════
    -- HISTORICAL SALES — 120 days of daily ground-truth sales for every
    -- SKU in the tenant (all industries), ending today. This is what
    -- lets Sales Analytics show consistent day/week/month/year figures
    -- and lets the Forecast Accuracy page compute real MAPE/WAPE.
    -- ═══════════════════════════════════════════════════════════════
    IF NOT EXISTS (SELECT 1 FROM historical_sales WHERE tenant_id = v_tenant_id) THEN
        INSERT INTO historical_sales (
            id, tenant_id, sku_id, industry, sale_time, channel, region,
            units_sold, gross_revenue, net_revenue, returns, promo_flag, markdown_pct, in_stock
        )
        SELECT
            gen_random_uuid(),
            s.tenant_id,
            s.id,
            s.industry,
            (CURRENT_DATE - n) + TIME '14:00',
            (ARRAY['online','retail','wholesale'])[1 + (n % 3)],
            (ARRAY['US','EU','APAC'])[1 + ((abs(hashtext(s.id::text)) + n) % 3)],
            units,
            ROUND(units * COALESCE(s.unit_price, 10), 2),
            ROUND(units * COALESCE(s.unit_price, 10) * (CASE WHEN promo THEN 0.85 ELSE 0.97 END), 2),
            CASE WHEN (n % 23 = 0) THEN GREATEST(0, ROUND(units * 0.05)) ELSE 0 END,
            promo,
            CASE WHEN promo THEN 15 ELSE 0 END,
            true
        FROM skus s
        CROSS JOIN LATERAL generate_series(0, 119) AS n
        CROSS JOIN LATERAL (
            SELECT
                (5 + (abs(hashtext(s.sku_code)) % 20))::numeric AS base,
                (CASE WHEN extract(dow FROM (CURRENT_DATE - n)) IN (0, 6) THEN 1.3 ELSE 1.0 END)::numeric AS weekly_factor,
                (1 + 0.15 * (119 - n) / 119.0)::numeric AS trend_factor,
                (0.85 + (abs(hashtext(s.sku_code || n::text)) % 30) / 100.0)::numeric AS noise,
                (n % 17 = 0) AS promo
        ) f
        CROSS JOIN LATERAL (
            SELECT GREATEST(
                0,
                ROUND(f.base * f.weekly_factor * f.trend_factor * f.noise * (CASE WHEN f.promo THEN 1.6 ELSE 1.0 END))
            )::integer AS units
        ) u
        WHERE s.tenant_id = v_tenant_id;
    END IF;

    RAISE NOTICE 'Full demo catalog + 120-day sales history seeded for tenant %', v_tenant_id;
END;
$$;
