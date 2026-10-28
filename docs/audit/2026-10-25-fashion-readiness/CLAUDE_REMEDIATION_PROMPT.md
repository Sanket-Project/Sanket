# Claude implementation handoff: resolve Sanket readiness audit

Work in `C:\Users\admin\Desktop\Prisma`. Implement and verify the fixes from the 25 October 2026 Swecha Fashions readiness audit. This is an implementation request, not a request for another audit or a plan alone.

## Read and establish the baseline

1. Read the repository's `AGENTS.md` before any repository action. Follow its actual Superpowers skills when available: systematic debugging, brainstorming/design approval for non-trivial changes, writing plans, RED/GREEN/REFACTOR, execution, code review and verification. Do not claim to invoke a skill you do not have. Respect any required design-approval gate; once the design is approved, carry the work through implementation and verification.
2. Read `docs/audit/2026-10-25-fashion-readiness/REPORT.md`, `verification-summary.json`, `review-notes.md`, and the relevant saved evidence. The audited commit was `3dba120ac51074ba6ba26ec09817126663d40b43`; inspect current code and preserve existing user changes. Reproduce each finding rather than assuming the checkout is unchanged.
3. Use the original audit artifacts as read-only baseline evidence. Save remediation evidence separately under `docs/audit/`. The existing audit runners deliberately create records and duplicate sales; they are not idempotent reset scripts and must not be rerun against a valuable database.
4. Use an isolated test database and clearly labelled synthetic fashion fixtures. App connections must remain `sanket_app` or an equivalent NOSUPERUSER/NOBYPASSRLS role, with tenant RLS enforced. Elevated migration access must use `MIGRATION_DATABASE_URL`. Do not weaken auth, tenancy or subscription checks to get tests green. Do not send messages, place orders, charge payments, deploy or publish anything.

## Fix every confirmed finding

### F01: non-idempotent sales import - highest priority

Re-uploading the same CSV with the same order IDs inserted all 459 valid rows again, doubled units from 17,482 to 34,964 and inflated forecast error. Trace `backend/app/services/integrations/file_import.py`, especially its sales branch and per-upload random ID.

Design stable, tenant-scoped source/order/line identity and safe replay handling, including concurrent uploads and partial retries. Where source identities are absent, explicitly define conservative file/row identity semantics. Do not collapse genuinely different transactions merely because SKU, time and quantity match. Clarify how corrected exports are handled. Prove unchanged row counts, units and revenue on replay; distinct legitimate orders must remain distinct. Gate or explicitly reject operational forecasting on confirmed critical duplicate corruption instead of silently forecasting inflated history. Handle existing duplicates safely; do not mass-delete customer data.

### F12: duplicate repair fails with `min(uuid)` - highest priority

`POST /data-quality/fix` with `action=dedupe_sales, confirm=false` returned 500: PostgreSQL 16 has no `min(uuid)` aggregate. Trace `_dedupe_sales` in `backend/app/services/data_quality_audit.py` near line 743. Use deterministic supported survivor selection and conservative duplicate identity. Test preview without mutation, actual repair on disposable fixtures, tenant isolation, transaction rollback and preservation of legitimate matching transactions. Do not claim the earliest record is kept unless ordering actually guarantees it.

### F02: weekly calendar mismatch and unusable accuracy scoring

History uses Monday buckets, while zero-shot inference uses pandas `W` and generates Sundays. The first response date after Monday 24 August 2026 was Sunday 30 August instead of the next Monday bucket. Uploaded actuals then failed to match `/forecast/accuracy`.

Trace `backend/ml/sanket_ml/data/loader.py`, `inference/zero_shot.py`, forecast persistence/export and `backend/app/routers/forecast_accuracy.py`. Apply one explicit weekly/calendar/timezone convention end to end. Verify full weekly intervals, including transactions later in the last week. Test that actuals match the intended forecast period and that production accuracy excludes predictions generated after the period being evaluated. Keep historical backtesting explicit and free from future-data leakage; do not make a misleading score by joining a forecast to its training week.

### F03: INR amounts converted as USD

The INR sales screen displayed 1,086,566,446 for an API total of 13,091,162: an erroneous 83x multiplier. `SalesAnalytics.tsx` omits source currency, while `useFormattedCurrency.ts` defaults to USD and the currency store defaults to 83.

Carry source currency consistently through ingestion, aggregation, API responses, charts, tables and exports. Define safe mixed-currency behavior and exchange-rate provenance. Do not treat an arbitrary constant as a live rate. Verify INR-to-INR identity and intended USD/INR conversions, and reconcile screens with raw sales and exports.

### F04: unsupported model/uplift claims and four-SKU truncation

`frontend/src/pages/Forecasts.tsx` showed TFT/DeepAR/Prophet+ and a hardcoded 12% seasonal uplift while the API reported Chronos zero-shot and no external signals. `.slice(0, 4)` omitted two of six SKU charts and made the displayed count wrong.

Use actual response metadata and measured comparisons. Show the actual model/source, horizon, forecasted count, omitted count and reasons. Paginate or otherwise expose every SKU. Label indicative estimates and unavailable data honestly. Remove unsupported uplift/model/driver claims from the forecast page and related overview/marketing copy. Test real and indicative paths, no-history responses, source failures and more than four SKUs.

### F05: trend partitions missing and zero evidence called 100% agreement

Signal ingestion failed because October 2026 had no `trend_signals` partition; baseline SQL only created May-August partitions. Trend Analysis displayed zero samples as stable demand with high 100% agreement via its zero-volatility default.

Add safe migration/rolling partition maintenance for current and future trend periods, with appropriate permissions and retention. Test crossing a month boundary and a fresh installation. Keep missing, stale, failed and genuinely neutral signals distinct in APIs and UI. No samples must mean insufficient/unavailable evidence, never perfect agreement. Keep model-only forecasts available when appropriate, but accurately disclose missing signal adjustment. Do not add fabricated fallback signals.

### F06: Swecha size support

Creating a 5XL SKU returned 422; the fashion enum in `backend/app/services/industry_context.py` also excludes 4XL. Support Swecha's size variants, including sensible label normalization, while retaining validation and variant identity. Test API creation, import, editing and size curves. Do not flatten sizes into one SKU to bypass validation.

### F07: explicit zero-demand rows rejected

Data Quality tells users to include zero-sales weeks, but the importer rejected 73 zero-quantity fixture rows. Define and implement a valid aggregate-history import contract that preserves observed zero demand and distinguishes it from missing data and stockout availability. Keep invalid negative transaction checks and returns semantics coherent. Test leading, interior and trailing zero weeks, gaps, retries and downstream forecast context.

### F08: unsold products silently omitted

A valid unsold SKU was omitted; the current zero-shot path requires eight observations. Zero-shot training is not zero-history forecasting. Return explicit per-SKU eligibility/omission reasons and correct the promise that never-sold SKUs automatically get usable forecasts. If an analogue-based new-product method is implemented, validate it separately, disclose its basis and uncertainty, and never invent demand or silently substitute unrelated SKUs. Honest insufficient-history behavior is required even if a validated analogue model is outside the approved scope.

### F09: inventory health and location scope

Without an open decision, Inventory used an arbitrary 20-unit threshold, showing healthy/no action while cover was pending and shortage alerts existed. After decision refresh, context appeared. The clean screen reused the same SKU-level 26-day cover across locations with different stock.

Derive risk from current stock, appropriate demand, lead time and freshness independently of whether a recommendation happens to exist. Missing context must remain unknown, not safe. Separate SKU-wide and location-specific coverage; do not label pooled demand/cover as store-specific. Show store cover or transfer suggestions only when supported by store demand and supply inputs. Test different stock/demand across two locations, stale/missing forecasts, no decisions and refresh behavior.

### F10: estimated ROI called realized savings

Approving one synthetic recommendation immediately produced `total_value_realized=144258.44` without a supplier order, receipt or observed outcome. The UI said the figures were not modelled/projected.

Separate forecast-based opportunity, approved/committed estimates and observed realized outcomes. Approval alone must not prove revenue saved, a stockout avoided or money realized. Keep quantities, financial units and totals economically coherent, with no double-counting of unlike measures. Provide evidence/provenance for each value and test the full lifecycle. Correct API and UI wording consistently.

### F11: false WhatsApp readiness

`PlanningBriefDashboard.tsx` hardcodes `Digest enabled` while configuration was disabled, provider console and credentials absent. Derive status from actual configuration, distinguish preview from delivery, and test disabled/unconfigured/ready/error states. Do not send any messages during remediation.

## Forecast quality and unresolved validation

The clean diagnostic had 8.54% WAPE versus 12.36% for last value across only six synthetic SKUs and 48 held-out points. It was manually aligned by horizon because date matching was broken. The intermittent gown SKU predicted zero median units against 19 actual units, with 100% WAPE. These are investigation inputs, not accuracy targets to overfit.

After fixing ingestion and dates, build a reproducible, date-aligned rolling-origin evaluation with frozen cutoffs and leakage checks. Compare Chronos and existing supported approaches against last value, trailing mean and seasonal baselines on identical folds. Investigate intermittent-demand routing and short-history behavior. Any selection/tuning must use training/validation data, never the reported test holdout. Report portfolio and per-SKU/cohort WAPE, bias, interval coverage, omitted SKU coverage, and stability across cutoffs. Do not guarantee every model wins every SKU or manufacture an accuracy percentage. If the model remains worse than an appropriate validated baseline, use a validated routing/fallback policy or clearly expose the limitation.

Real Swecha accuracy, genuine business savings, live connectors and WhatsApp delivery cannot be proven without their data, access and observed outcomes. Record missing prerequisites rather than inventing results or marking them complete.

## Resolve the red suite and verify the whole workflow

The full backend run produced 371 passed, 1 failed, 164 warnings. `tests/test_external_signals.py::test_regional_demand_connector_fetch` expected more than five samples but got zero. It passed alone. Investigate order dependence, caching, shared state, async lifecycle and mock isolation as hypotheses; establish the actual cause. Do not delete, skip, weaken or retry the test until it appears green. Explain the fix and show a clean full-suite result.

Run these checks and report exact commands, counts, exit codes and material warnings:

```text
frontend: npm run typecheck
frontend: npm run lint
frontend: npm test
frontend: npm run build
backend: uv run pytest
backend/ml: .venv/Scripts/python.exe -m pytest -q
```

Update regression tests through RED/GREEN/REFACTOR. Add/run meaningful Playwright coverage for import -> forecast -> actuals/accuracy -> inventory -> decisions/scenarios -> export. Use configurable local API/WebSocket URLs and isolated seeded fixtures; do not mistake the unrelated service on port 8000 for Sanket. The prior audit used backend 8010, ML 8001, frontend 5173, database 55432 and Redis 56379. Detect port/process ownership before reusing these services. Preserve the audit baseline and run new comparisons in a fresh remediation workspace.

For completed fixes, review spec compliance and code quality, run migrations on a fresh and representative existing schema, and exercise the UI, not only mocked requests. Verify RLS and authorization neighbors after any import/schema/API changes. Check the final diff and preserve unrelated work. Do not reset shared processes or databases blindly.

## Deliverables and completion criteria

Deliver implemented fixes, regression tests, necessary migrations, a reproducible evaluation and demo runbook, and a concise remediation report under `docs/audit/`.

Map F01-F12 plus the suite failure and forecasting evaluation to changed files, root cause, reproduction, passing acceptance evidence and any remaining limitation. Include fresh screenshots and before/after forecast metrics. Distinguish fixed, verified, partially addressed and blocked-by-external-prerequisite items. A missing credential or real-client dataset is not a code fix and must not be hidden.

Finish with a candid demo/pilot/production readiness verdict. Do not claim perfect forecasting, universal connector support, proven client ROI or production readiness solely because tests pass. If an approved implementation can be completed, continue through verification instead of stopping after a plan. State any required human decision precisely and only when genuinely required by the repository workflow or missing external input.
