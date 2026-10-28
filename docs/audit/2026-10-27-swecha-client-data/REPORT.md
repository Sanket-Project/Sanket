# Swecha client demo — 27 October 2026

Open [Forecasts](http://127.0.0.1:5173/workspace/forecasts), [Inventory](http://127.0.0.1:5173/workspace/inventory), and [Sales Analytics](http://127.0.0.1:5173/workspace/sales-analytics) using the existing Swecha workspace login. The normal local stack is running. Final launcher process at startup: 19308. Logs: `tmp/swecha-final-stack.log`, `tmp/swecha-final-stack.err`, `tmp/dev-stack/`. Verify process ownership before stopping services.

## Imported data

| Report | Scope | Reconciled result |
| --- | --- | --- |
| Stock | Six locations | 13,783 SKUs, 12,148 product groups, 16,519 SKU/location positions, 38,419 units; source closing value INR 18,878,893.78 |
| Sales | 121 store/day records, 1–25 October 2026 | 2,643 net units; INR 2,581,934 net sales |
| Gross profit | 15,524 SKU/store period records, 1 January–25 October 2026 | INR 9,754,931.20 gross profit; 37.80% margin on sales excluding tax |
| Purchases | 266 supplier invoice and return records, 3 January–23 October 2026 | 28,311 net units; INR 18,882,379.57 including signed returns |

The report UI keeps the periods separate and includes store breakdowns, top 20 SKUs by reported gross profit, supplier totals, filenames and data limitations. It uses the existing workspace settings JSON; no schema change was needed. Original files in Downloads were not modified. Document contents were treated as data, not instructions.

Stock and purchase details reconcile exactly to supplied grand totals. Sales detail reconciles to the supplied store subtotals. Gross-profit detail reconciles within sub-cent source rounding. Source hashes and controls are in `source-reconciliation.json`.

## Replacement and preservation

User approved replacing the existing Swecha data after backup. Backup: `backups/swecha-before-client-import-2026-10-27.dump`, 2,852,393 bytes; archive listing validated. Keep this private local backup out of commits and shared demo materials. Its SHA256 is in `backup.json`.

A complete delete-and-load rollback rehearsal passed before the real transaction. Clearing and loading ran in one transaction under the tenant-scoped application role with RLS enforced. Temporary maintenance permissions were restored. Other tenants were unchanged during replacement. Existing login credentials, roles and original workspace settings were independently compared with the backup and preserved. Only the client report summaries were added to settings. Existing workspace display name and test-workspace settings were retained.

Evidence: `dry-run.json`, `apply.json`, `final-data-verification.json`. In `apply.json`, `after` means after clearing and before loading; `loaded` contains the final replacement counts. Its preservation check precedes adding the reports; the final verification separately checks original settings against the backup.

## Verification

- Reports, inventory, exact client SKU search, locations, products, SKUs, company trends, data quality, decisions and latest forecast: authenticated HTTP 200. Counts and stock units asserted against the source. See `api-verification.json`.
- Browser: normal Swecha sign-in succeeded. Report figures/periods and inventory totals/six locations rendered. Forecasts explicitly refused generation because all 13,783 SKUs lack dated sales history. Screenshots: `client-reports.png`, `inventory.png`.
- New backend tests: 2 passed, covering authentication, other-workspace isolation, industry mismatch and withholding unrelated settings. Initial RED failures were HTTP 404.
- Report component and page tests: 4 passed, covering distinct periods, limitations, source names, existing currency behavior and recoverable report errors.
- Final frontend typecheck and lint: passed. Full frontend after the approved projection: 61 files, 299 tests passed in 76.14 seconds. Production build passed in 20.96 seconds with existing bundle-size warnings.
- Full backend after projection: 914 passed, 4 warnings in 280.97 seconds. After final wording corrections, 65 targeted projection, inventory and digest tests passed in 23.31 seconds. The browser caught a correct average-coverage value paired with the old dated-week explanation; a failing assertion reproduced it and the corrected explanation now gives the reported quantity and 298-day denominator. The earlier initial full run had one Hypothesis input-generation timing health-check failure (899 passed); its recorded-seed allocation recheck passed all 9 tests, and the subsequent full run passed allocation too.
- ML suite: 73 passed, 2 warnings. Real Chronos runtime smoke: cached pretrained model, explicitly synthetic 16-week input, four forecast steps, finite samples and ordered quantiles; 18.77 seconds; no database writes. This proves runtime inference, not client forecast accuracy.
- Manual review covered tenant/industry scope, periods, tax basis, empty states, tables, error handling and preservation of existing analytics. Tracked source diff whitespace checks passed. No push, deployment or live provider evaluation was performed.

## Demo limits

Start with Forecasts' Average-sales projection, then Inventory and Sales Analytics. Products and SKUs contain the real client catalogue.

The sales file has store/day totals without SKUs. The gross-margin file has SKU totals without sale dates. Purchases have supplier invoice totals without SKU lines. All sheets and hidden rows/columns were rechecked; no dated SKU sales were found. See `forecast-source-inspection.json`. No daily SKU history was fabricated. Chronos client forecasts, statistical uncertainty, automated recommendations, accuracy and realised ROI require additional inputs. Request dated SKU sales with quantity, returns, revenue and store, plus supplier lead times.

Stock snapshot date is not supplied; records use import time. Reserved stock, inbound stock and reorder thresholds are also missing. The app flags missing inputs. Catalogue prices use the first reported location per SKU; source location costs, retail prices and closing values remain on each stock record. The original reports remain the source of truth for location valuation.

Provider-backed AI explanations require configured provider access; service health alone does not establish live generation or forecast accuracy.

## Approved average-sales projection

The user approved using reported period totals as a separate constant-rate projection. The gross-profit report's inclusive 1 January–25 October 2026 period is 298 days. Projection = reported SKU quantity / 298 × future days. Horizon, SKU/product search, pagination and store details work in the Forecasts view. Chronos remains a separate selectable model view; opening the projection does not launch model inference.

Exact source SKU matches: 4,125. Positive eligible SKU totals: 4,014. Nonpositive totals excluded: 111. Current catalogue SKUs without a matching gross-profit record: 9,658. No absent record is treated as observed zero demand. Source periods ending in the future or over 90 days old are unavailable. The full active catalogue remains 13,783 SKUs; inventory remains 38,419 units.

Source SKU/location totals were added to existing SKU attributes under RLS after hash verification; no schema, historical-sales or model-forecast records were introduced. Period totals reconcile to the original report. Inventory coverage uses a labelled period-average fallback only after model forecasts and dated trailing actuals; local cover needs local matching sales. Missing, nonpositive and stale evidence remains unavailable. These averages do not create purchase/transfer recommendations and cannot establish seasonality, launch dates, recent trends, stockout-censored demand or confidence intervals. Catalogue prices still retain the previously documented representative-location limitation.

Verification: 50 targeted backend tests and 35 targeted frontend tests passed before full suites. The API verified 4,014 eligible SKUs, 298 source days, correct horizon multiplication, page separation, exact SKU search and estimated inventory coverage. Read-only endpoints for the main feature areas returned HTTP 200. Complete inventory (16,519 rows), SKU (13,783) and product (12,148) CSV exports were counted; stock export summed to 38,419 units. Details: `feature-verification.json`, `period-enrichment.json`, `chronos-runtime-smoke.json`.

Example for demo search: SKU `77SHADP0L49996`: 81 reported units / 298 days = about 1.90 units/week; four-week projection about 7.61 units; 17 reported stock units. Its warehouse has stock but no positive matching sales, so local demand/cover is unavailable instead of borrowing another store's rate.

The WhatsApp preview had an unrelated misleading empty-queue all-clear. A failing regression test reproduced it; the renderer now states only that recommendations are absent and asks the user to review coverage. No notifications were sent. WhatsApp is not configured; its provider is console-only. External connectors remain dependent on their respective credentials. Billing is test-mode. HTTP success/preview rendering does not prove live external delivery or integration sync.

Manual review covered scope, exact matching, denominator, positive-only eligibility, source freshness, model/actuals precedence, source-period labels, paging, tenant isolation and unchanged stock. Unrelated pre-existing working-tree changes were preserved. No dependency was added, and no PR, push or hosted deployment was performed.
