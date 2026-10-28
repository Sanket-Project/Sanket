-- Purge mock/demo rows from the local dev database (sanket_recovered_20261026).
-- Backup taken first: scratchpad/sanket_recovered_20261026-before-mock-purge.dump
-- Runs in one transaction; ON_ERROR_STOP rolls everything back on any error.
BEGIN;
SET LOCAL app.bypass_rls = 'true';

-- swecha-demo: synthetic Swecha workspace (180 products, 2,321 SKUs, 6,693 stock rows)
DELETE FROM tenants WHERE slug = 'swecha-demo';

-- sanket-dev: all 22 products are SQL demo seeds; keep the tenant + login users
DELETE FROM forecast_runs    WHERE tenant_id = (SELECT id FROM tenants WHERE slug = 'sanket-dev');
DELETE FROM historical_sales WHERE tenant_id = (SELECT id FROM tenants WHERE slug = 'sanket-dev');
DELETE FROM inventory_levels WHERE tenant_id = (SELECT id FROM tenants WHERE slug = 'sanket-dev');
DELETE FROM skus             WHERE tenant_id = (SELECT id FROM tenants WHERE slug = 'sanket-dev');
DELETE FROM products         WHERE tenant_id = (SELECT id FROM tenants WHERE slug = 'sanket-dev');

-- Anything else still sourced from seeds or fabricated signals
DELETE FROM inventory_levels WHERE source IN ('seed', 'synthetic_test');
DELETE FROM trend_signals WHERE source = 'logistics' AND payload ? 'simulated_congestion_percent';
DELETE FROM trend_signals
 WHERE payload->>'synthetic' = 'true' OR payload->>'is_synthetic' = 'true' OR source::text = 'synthetic';

SELECT t.slug,
  (SELECT count(*) FROM products p         WHERE p.tenant_id = t.id) AS products,
  (SELECT count(*) FROM skus s             WHERE s.tenant_id = t.id) AS skus,
  (SELECT count(*) FROM historical_sales h WHERE h.tenant_id = t.id) AS sales,
  (SELECT count(*) FROM inventory_levels i WHERE i.tenant_id = t.id) AS inventory,
  (SELECT count(*) FROM forecast_runs f    WHERE f.tenant_id = t.id) AS runs,
  (SELECT count(*) FROM users u            WHERE u.tenant_id = t.id) AS users
FROM tenants t ORDER BY 1;

COMMIT;
