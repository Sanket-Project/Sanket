# Approved workspace redesign — implementation evidence

Design approved 2026-10-27. Execution plan: ../../superpowers/plans/2026-10-27-client-workspace-ui.md.

## Workflow

Manual writing-plans → subagent-driven development → strict TDD. Separate file ownership for company trends backend, trends frontend, inventory, and dashboard integration. Existing uncommitted forecast/import work is preserved. Live swecha-demo business records remain empty; populated behavior is tested using isolated test fixtures.

## Dashboard TDD

- RED: three new confidence tests failed because the labelled confidence field did not exist (9 existing tests passed).
- GREEN: aligned summary field with numeric score, readable band and View reasons; valid zero remains visible; missing confidence explains its reason. Removed the floating capsule.
- RED: empty-card regression failed on missing concise heading.
- GREEN: concise heading/copy, no sample catalogue image for an empty planning card. Focused suite: 13 passed. Logs: tmp/dashboard-red.log and tmp/dashboard-green.log.

## Final verification

- ML regression suite: 73 passed, 2 warnings (15.45 seconds). Log: tmp/client-ui-ml-tests.log.
- Backend: `cd backend; uv run pytest` — **688 passed**, 4 warnings, 292.92 seconds. Log: tmp/client-ui-backend-tests.log. Warnings include dependency deprecations and a pooled-connection cleanup warning during the test suite; no assertion failures.
- Frontend: `npm run typecheck` and `npm run lint` — both exit 0. `npm test` — **262 passed in 50 files**, 66.05 seconds. Logs: tmp/client-ui-typecheck-final.log, tmp/client-ui-lint-final.log, tmp/client-ui-frontend-tests-final.log.
- Reviewed diffs and ran `git diff --check` for the changed application files: no whitespace errors. Independent reviews covered dashboard confidence/API integration and inventory actions/pagination. Findings were fixed and retested.
- Local API: existing credentials still authenticate; overview, company trends, district filtering and catalogue options all returned 200 in 49.2–88.2 ms. All returned empty company business data. Evidence: [API results](api-verification.json). No live business records were created.

## Delivered behavior

- State → District selection includes Hyderabad and the official 33 Telangana districts. Product/SKU options come from bounded tenant catalogue queries. Dropdown search, keyboard selection, focus, list scrolling and viewport placement are tested.
- Trend Analysis separates uploaded sales comparisons from catalogue-matched external interest. Dates use actual elapsed time, and period anchors are distinct from the last sale in a regional selection. Missing data gets an import prompt or missing-evidence explanation.
- Catalogue-derived external collection runs through arq where configured (explicit local background fallback otherwise), with a tenant/industry database lock, fifteen-minute reuse and at most eight deduplicated product/category terms per sweep. Private observations remain tenant scoped; no external search occurs during a GET.
- Inventory uses one SKU row with store details and location-matched saved recommendations. It paginates across all stock, resolves imports beyond the first 200 catalogue entries, and bounds forecast/transfer coverage reads to the SKU page. Tenant changes clear cached selections and parsed import state.
- Dashboard confidence appears once in the planning summary with a band and reasons link; absent evidence is Not scored. Empty planning has no sample product image.

## Browser verification

Used the in-app browser against the real, empty swecha-demo workspace at desktop 1440 × 900 and narrow 390 × 844 breakpoints. Temporary viewport overrides were reset and light theme restored.

1. Regional selection: searched Telangana, inspected all 33 district options, selected Hyderabad using keyboard. The final menu remains within the viewport; narrow-page document width equals viewport width (390 px). [Desktop evidence](after/01-regional-district-menu.png), [mobile evidence](after/05-regional-mobile.png).
2. Dashboard: the confidence field is aligned in the summary and explains why no score exists. [Evidence](after/02-dashboard-desktop.png).
3. Inventory: concise onboarding routes to products, sales imports and stock import, without large zero-value KPI cards. [Desktop evidence](after/03-inventory-desktop.png), [mobile evidence](after/04-inventory-mobile.png).

Browser QA caught and corrected an ancestor-scroll jump in dropdown keyboard navigation and unsupported Tailwind primary-color utilities. Added regressions that scroll only the option list and compile the controls against the actual Tailwind palette. Active regional-tab computed colors verified as light: background rgb(3,54,61), foreground rgb(255,255,255); dark: background rgb(189,217,215), foreground rgb(3,54,61).

Populated stock expansion, catalogue filtering, sales comparisons and confidence scores were verified with isolated automated test fixtures. They were not populated in the user's cleared live workspace for screenshots.

## Scope notes

Inventory attention filters are explicitly scoped to the current page of bounded, freshly computed coverage. Global SKU/position totals, server search, location selection and pagination remain available. A complete catalogue-wide attention index would require persisted coverage snapshots; this implementation must not disguise a truncated page as all stock.

Regional filters do not infer district evidence from a city/state observation. Location sales filtering requires explicit state/district metadata. No district score is synthesized.

The Telangana selector follows the [official 33-district list](https://www.telangana.gov.in/about/districts/) (verified 2026-10-27).

External read scope is explicit: the latest 1,000 search observations from thirty days, up to fifty catalogue-matched results. Collection prioritizes a bounded set of product/category terms rather than querying every SKU.
