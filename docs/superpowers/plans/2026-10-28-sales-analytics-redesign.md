# Sales analytics redesign

Approved direction: a plain-language sales story, clear trend, conditional ranked
branch comparison, best-selling products, and progressively disclosed supporting
reports. Preserve the teal design system, source periods, missing-data semantics,
currency separation, and tenant RLS. Existing workspace edits must be preserved.

Execute sequentially using RED → GREEN → REFACTOR. Each step is a small task;
review its diff and tests before proceeding.

1. Add tests for ranked branch comparisons, absent branch data, negative sales,
   and independent report periods. Verify failures before adding the shared view.
2. Redesign imported reports around a sales hero and branch comparison; retain
   profit, purchases, and source details. Verify component tests.
3. Add API tests for location-based branch aggregation, missing locations,
   currencies, and tenant isolation. Verify failure, then implement a read-only
   tenant/industry-scoped endpoint using existing sale locations and RLS.
4. Add transaction-page tests for plain-language summaries, period selection,
   error states, branch visibility, and exact lookback. Verify failures, then
   redesign the page with consistent controls and accessible chart/table views.
5. Run frontend typecheck, lint, tests and backend pytest. Review the diff and
   inspect desktop/mobile renderings. Record actual results and limitations.

Branch rules: named source stores/locations identify branches. Never infer a
branch from a region or SKU. Blank locations remain unassigned and disclosed
when named branches exist; no branch panel when none exist. Mixed currencies
are never summed or ranked against one another by money.

Imported aggregate reports retain their original reporting periods; do not
invent daily charts, growth, or SKU sales from aggregate totals.

Completed: all five steps. Verification and synthetic desktop/mobile screenshot
evidence are in `docs/audit/2026-10-28-sales-analytics/README.md`. Full frontend:
343 passed. Full backend: 1,141 passed. Final focused backend: 13 passed.
Browser design checks: 8 passed. Typecheck, lint, Ruff and scoped diff checks pass.
