# Fashion readiness remediation — final verification

26 October 2026 · explicitly synthetic data · local verification only

The remaining implementation, evaluation and verification work is complete. The import, forecast, historical backtest, inventory, decision, scenario and Excel-export journey runs with real local services. The remediation also passed the full backend, frontend and ML suites. This establishes the tested software behavior; it does **not** establish Swecha forecast accuracy, realised savings, or production readiness under real load.

## Forecast quality

The frozen rolling-origin diagnostic uses the original synthetic training and held-out CSVs. Validation cutoffs are 13 April, 11 May, 8 June and 6 July 2026; the untouched test cutoff is 31 August 2026. Every horizon is eight Monday-UTC weeks. Training ends strictly before each cutoff. Missing in-span weeks become explicit zero weeks; insufficient-history series are reported as omitted.

| Model | Validation WAPE | Test WAPE | Test points | Test interval coverage |
| --- | ---: | ---: | ---: | ---: |
| Chronos zero-shot | 20.96% | **7.45%** | 48 | 75.00% |
| Repeat last value | 24.89% | 12.36% | 48 | Not provided |
| Four-week mean | 23.12% | 23.45% | 48 | Not provided |
| Seasonal naive, 52 weeks | 34.09% | 18.98% | 40 | Not provided |
| Croston-SBA | 28.55% | 22.76% | 48 | Not provided |
| Repository ADIDA | 23.43% | 23.01% | 48 | 56.25% |

Seasonal naive omits the newer PALAZZO series because it lacks 52 training weeks. Its 40-point test score is therefore on a different subset and must not be read as a direct 48-point portfolio comparison. Validation covers five eligible SKUs; all six are eligible for the Chronos test fold. Cohort and omission counts are retained in the JSON.

The best routing rule was selected using validation only. It improved validation WAPE to 19.96%, but its test WAPE was **13.22%**, worse than Chronos. The production gate failed, so **no new routing rule was shipped**. The forecast page now explicitly says the model has not been shown to beat simple baselines on every SKU and requires validation against the customer's own sales.

Execution used CPU, `amazon/chronos-t5-small`, 100 samples, seed `25102026`, 104-week context cap, and the same training-only censoring preprocessing as production. The resolved model revision is `a971ba21945c4f1796b17a91fe69214b5f4ad472`. Fixture hashes, exact dependency versions and censoring settings are in [results.json](evaluation/results.json). A second run reproduced every model metric and routing result exactly on this host: [reproducibility.json](evaluation/reproducibility.json).

## Verification results

| Command | Exit | Actual result |
| --- | ---: | --- |
| Frontend `npm run typecheck` | 0 | Passed |
| Frontend `npm run lint` | 0 | 0 errors, 28 warnings |
| Frontend `npm test` | 0 | **149 passed**, 34 files |
| Frontend `npm run build` | 0 | Passed; chunk-size warning remains |
| Backend `uv run pytest` | 0 | **517 passed**, 111 warnings, 400.96 seconds |
| ML `.venv/Scripts/python.exe -m pytest -q` | 0 | **56 passed**, 2 warnings, 25.17 seconds |
| Opt-in real Playwright journey | 0 | **1 passed**; see final browser log |
| `git diff --check` | 0 | Clean |

The backend run includes `test_rls_isolation.py`, `test_industry_scope.py`, `test_entitlement.py` and `test_rbac.py`. No tests were skipped, marked expected-failure, or given retries to produce the unit/integration results above. The remediation browser spec is deliberately skipped during ordinary unrelated E2E runs unless `E2E_REMEDIATION=1`; it was enabled for this verification.

An initial concurrent frontend run timed out in five interactive tests with the default worker fan-out. Vitest now runs at most two jsdom workers; its normal timeouts remain unchanged. The full suite subsequently passed while real ML/browser work was active. Initial failure logs remain locally available. A seed-test import failure under the prescribed `uv run pytest` invocation and a Modal-test type error were also corrected before the final runs.

The warning counts above are not zero-warning claims. They include existing deprecations, existing lint warnings, and a backend unawaited-AsyncMock warning. The production bundle still contains chunks larger than 500 kB. These were not hidden or suppressed.

## Real browser journey

The test uses PostgreSQL `55433`, Redis `56380`, API `8011`, ML `8002`, and web `5174`. The application and seed use `sanket_app` with `NOSUPERUSER` and `NOBYPASSRLS`; administrative connections are confined to migration/backup verification.

The final clean-tenant journey verifies:

1. Login to an explicitly synthetic workspace with seven SKUs, including unsold size 5XL.
2. Import **1,064 new training rows**, replay with **0 new / 1,064 unchanged / 0 corrected**, and import **96 new held-out rows**, with no skipped rows. The two-store split preserves original portfolio demand.
3. Generate six real Chronos forecast series, 72 live predictions, six visible chart elements, the Monday calendar, and an explicit reason for the unsold SKU's omission.
4. Backtest from Monday 31 August 2026. Independently match all 48 predictions to held-out SKU/week totals, calculate WAPE, compare the rounded API value, and verify the displayed value. Production accuracy remains separate from after-the-fact backtests.
5. Show two-store inventory coverage with different store-cover values.
6. Refresh recommendations and accept one synthetic purchase recommendation. This changes the internal decision ledger; it does not place a supplier order.
7. Run a real scenario preset and download Excel. Validate 72 data rows and every exported Monday-start/Sunday-end pair.

The exact final run values and responses are in [journey-evidence.json](e2e/journey-evidence.json). The endpoint's stochastic run can differ from the fixed-seed benchmark; its independently verified WAPE is recorded separately. Screenshots and [forecast.xlsx](e2e/forecast.xlsx) are in `e2e/`.

## Migration, restore and tenant isolation

- **Fresh database:** the complete Alembic chain ran through revision `0024` on the isolated database. The original fresh-chain log is preserved.
- **Populated current audit backup:** a read-only `pg_dump` from `55433` restored successfully into the dedicated `55434` target. Migration-to-head passed; table counts and sale totals matched. This snapshot contains 1,160 sale rows, 19,100 units, 7 SKUs, 14 inventory rows, 16 forecast runs and 1,056 forecast results. A later clean-tenant E2E run is separate from that already verified snapshot.
- **Restored RLS:** the app role is neither superuser nor bypass-RLS. It sees 1,160 own-tenant sales, zero without tenant context, and zero under a foreign context. See [current-restore-verification.json](restore/current-restore-verification.json).
- **Legacy upgrade:** a separate, recreated synthetic revision-`0021` database was seeded through the app role, dumped read-only, restored, and upgraded through `0022`–`0024`. All original sale-field hashes, counts and totals were preserved. Duplicate upload groups received matching identities; zero-demand non-upload rows stayed unkeyed. Both tenants saw zero foreign rows. See [legacy verification](restore/LEGACY-VERIFICATION.md).

**Historical evidence limitation:** the original 25 October audit database/container was no longer present, and no saved dump was available. Its exact historical state could not be restored. The recreated legacy test and the current populated-audit restore above are explicitly identified substitutes, not claims that the missing original database was tested.

## Findings covered

| Finding | Remediated behavior and evidence |
| --- | --- |
| F01 — duplicate imports | Tenant-scoped identities, replay counters and period corrections; importer/replay tests and real browser replay |
| F02 — accuracy dates | Monday-UTC matching, explicit exclusions and separate backtests; latest eligible forecast chosen once per SKU-week across model changes |
| F03 — currency | Explicit source currency and dated manual conversion; mixed totals separated; explicit upload currency cannot silently conflict with an existing SKU |
| F04 — unsupported claims | Actual model/source shown; forecast cards describe demand rather than invent purchase or stockout advice; model-quality limitation disclosed |
| F05 — missing trend evidence | Missing, insufficient and stale evidence represented honestly; partition and signal tests pass; live external-provider availability remains unproven |
| F06 — fashion sizing | Canonical extended sizes, including 5XL; size tests and real synthetic 5XL catalogue entry |
| F07 — duplicate repair | Restricted tenant-checked correction path and repair tests; legacy backfill preserves rows rather than silently deleting them |
| F08 — catalogue coverage | Six charts displayed and unsold SKU explicitly omitted with reason; pagination tests |
| F09 — inventory coverage | Coverage-based status and labelled store/SKU-wide basis; two different store covers verified |
| F10 — ROI honesty | Opportunity, approval estimates and observed outcomes separated; realised savings remain unmeasurable; measured improvement reuses the same latest eligible forecasts as accuracy |
| F11 — WhatsApp readiness | Disabled, preview, no-recipient and configured states tested; no live delivery claim |
| F12 — suite interaction | Live signal loops disabled in tests and cooldown isolated; complete backend suite passes |

## Review and remaining limits

Independent focused review found and resolved evaluation preprocessing/denominator errors, an explicit-upload currency conflict, cross-model double counting in production accuracy, and averaging historical forecasts in ROI. Browser execution found stale generated Vite configuration shadowing the TypeScript config and an inaccessible modal ancestor. Explicit config selection and modal accessibility regressions now cover those causes. Screenshot review additionally removed purchase advice unsupported by stock/lead-time evidence. The final focused review reported no remaining blockers; it was not an exhaustive security or scalability audit.

Real Swecha data, client-specific accuracy, realised business outcomes, live POS/ERP/Shopify synchronization, WhatsApp delivery, real payments, deployment and load behavior remain outside this verification. No messages, payments, real supplier orders, push or deployment were performed.

Use the app for a transparent supervised demo and validate it on the customer's actual historical data before relying on its forecasts for purchasing. See [RUNBOOK.md](RUNBOOK.md) for the isolated stack and repeatable journey, and [verification-summary.json](verification-summary.json) for machine-readable results.
