# Swecha client demo data plan

Approved by user: replace existing Swecha business data after backup; expose separate aggregate reports without fabricated SKU sales.

1. Back up and validate the local database; inventory existing tenant rows. Verify archive listing and preserve accounts/settings and other tenants.
2. Add failing tests for a tenant-scoped client-report endpoint and report UI: periods, amounts, unavailable states, and isolation. Verify RED before implementation.
3. Implement the smallest read-only report endpoint using existing tenant settings JSON and a report component on Sales Analytics. Verify targeted tests, typecheck, lint.
4. Parse the four supplied reports, reconcile totals, and replace only Swecha business rows in a transaction using the RLS application role. Retain source hashes and metadata, SKU/store stock values, and report aggregates. Verify counts, totals, rollback on failure, retained rows, other tenants.
5. Start the normal local stack, check authenticated endpoints and UI, run required frontend/backend suites, review diff, and document real limitations and demo URL.

Reports do not feed forecasts: October store/day sales lack SKUs; January–October gross margin lacks sale dates; supplier purchases lack SKU invoice lines. Inventory source has no explicit snapshot date. Do not infer missing history or stock coverage. SKU prices may vary by location; retain source values per position and disclose catalogue representative prices.
