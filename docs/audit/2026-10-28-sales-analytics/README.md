# Sales analytics redesign verification

Approved on 28 October 2026. Both transaction analytics and imported aggregate
reports now lead with a plain-language sales summary. Explicit sale locations
or imported store names produce a ranked branch comparison; absent names omit
the panel. No branches are inferred from regions or products.

## Data integrity review

- Branch API uses the existing tenant-scoped database session, explicit tenant
  and industry predicates, and a tenant-scoped SKU join. No schema or RLS changes.
- Branch grouping trims source location names. Unassigned records are disclosed
  when a comparison is available. The date window matches the chart grouping.
- Different currencies remain separate; mixed-currency bars compare item counts.
- Missing or partially available branch revenue is unavailable, rather than zero
  or a misleading partial total. Explicit zero amounts retain their currency.
- Returns are named clearly. Negative net branch sales never receive a positive
  sales-share label. Aggregate report periods remain independent.
- Chart comparisons use completed periods and exclude the current partial period.
- New sale events refetch authoritative totals and breakdowns, without adding
  currency-free event amounts to recorded revenue.
- Chart gaps stay distinct from observed zero sales. Chart values are also
  available in an expandable HTML table. Request failures have retry actions.

## Verification

- RED: imported-report tests failed for the old title, absent ranked branch
  comparison, and negative-return explanation before implementation.
- RED: branch API tests returned 404 before implementation; missing-revenue and
  partial-revenue cases subsequently failed before their fixes.
- RED: transaction tests failed for history controls, conditional branches,
  honest request errors, missing history, and completed-period explanation.
- `npm run typecheck`: passed.
- `npm run lint`: passed.
- `npm test`: 67 files, 343 tests passed.
- `uv run pytest`: 1,141 passed, 3 deprecation warnings in 402.42 seconds.
  The final partial-branch-revenue hardening was then verified with the focused
  13-test sales, currency and history suite below.
- `uv run pytest tests/test_sales_branches.py tests/test_sales_currency.py tests/test_sales_timeseries_gaps.py -q --tb=short`: 13 passed.
- `uv run ruff check app/routers/sales_analytics.py tests/test_sales_branches.py`: passed.
- `npx playwright test e2e/sales-analytics-design.spec.ts --workers=2`: 8 passed.
- Scoped `git diff --check`: passed.

Browser checks render real page components and the production stylesheet using
explicitly synthetic, intercepted API responses. They cover 1440px desktop and
375px mobile in both light and dark modes, page overflow, runtime errors, chart
grouping controls and the accessible history table. They do not authenticate
against or modify a customer workspace. Backend tests use disposable PostgreSQL.

Manually reviewed desktop light and mobile dark screenshots, the API query,
currency handling, error/empty states, and changed source diff. Screenshots in
this folder are labeled synthetic review data and are not customer sales.
