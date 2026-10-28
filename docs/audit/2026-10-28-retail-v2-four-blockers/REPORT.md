# Four V2 blockers — repair verification

**Application update, 28 October 2026:** following the user's instruction to
apply the changes, the configured local database `sanket_recovered_20261026` was
backed up and upgraded from **0035 through 0038**. Alembic exited 0. Post-upgrade
checks confirmed revision 0038, all **34,370** existing history rows preserved,
FORCE RLS on all five new V2 tables, and the application role still having
neither superuser nor BYPASSRLS privileges. A nonexistent tenant could see zero
history rows. This database had no pre-existing V2 history or canonical V2
events to repair. The PostgreSQL custom-format backup is stored under
`backups/sanket_recovered_20261026_before_0038_20261028T070107Z.dump`; its catalog
was verified with `pg_restore --list`. See `local-migration.json` for results.
This supersedes the earlier not-applied status below. No Prisma dev server was
running on its configured ports, so no running-app smoke-test claim is made.

28 October 2026. Scope: the four reported blockers and their retry/migration
neighbors. This record does not certify the rest of the V2 roadmap.

## Repairs

- The import handler accepts either V2 preview or legacy analysis. V2 success
  calls the existing completion callback with import counters so parents refresh.
  Invalid previews, viewers and failed confirmations do not signal completion.
- Non-final returns require the sold quantity's proportion of the original
  discounted net value and original tax, rounded half-up in paise. The final
  return receives the remaining value and tax. Failed posting rolls back its
  registry identity as well as its financial event.
- Sale history remains at the original recognized value. An approved return
  projects zero gross units/revenue and negative net revenue on `return_at`, with
  its positive return quantity. Credit rows do not inflate sale transaction
  counts. Draft and rejected events have no financial projection.
- Projection keys use canonical event UUIDs with distinct sale/return namespaces,
  so delimiters in source/transaction/line IDs cannot merge separate events.
  Existing sale locks and return registry locks serialize posting/projection.
- Concurrent identical return registration now honors the duplicate outcome;
  existing return identities are locked before processing draft approval.

## Existing-data repair and deployment

Forward Alembic migration **0038** rebuilds the V2 history of tenants already
using that projection from canonical sale and approved return events. It restores
sales hidden by old key collisions and moves credits out of the original sale
day. V1 history is preserved. The migration locks the affected tables during
repair and fails explicitly for missing canonical provenance or unresolved or
ambiguous SKUs. It requires `MIGRATION_DATABASE_URL` credentials with cross-tenant
migration privileges; application code continues to use tenant-scoped sessions.

No client/development database was migrated or deployed by this task. Upgrade
through 0038 before enabling this implementation against existing V2 history.
Downgrade retains the financial data correction rather than restoring the faulty
projection. Previously issued credit amounts remain canonical audit facts; this
migration does not silently change an already-approved over-credit.

## Test evidence

Before fixes, the promoted HTTP regression tests produced **3 failed, 1 passed**:
the partial credit returned 200 instead of 400, original-day net was 900 instead
of 1800, and two distinct events projected only one sale. The new UI regression
also failed with **zero** confirmation calls. Subsequent retry tests reproduced
a duplicate return primary-key exception and two reported insertions for one
concurrent draft approval before their fixes.

Regression coverage now includes authenticated financial writes and analytics
through the `sanket_app` RLS role, credit-date timeseries and period summaries,
draft approval/replay, concurrent sale/return confirmations and draft approvals,
rollback after over-credit rejection, zero-value allocations, three-unit rounding,
and a populated migration with damaged history, a missing collided sale and a V1
control row. The UI tests exercise the production component with mocked HTTP;
they do not claim live browser/E2E verification.

| Command/check | Actual result |
| --- | --- |
| `npx vitest run src/components/integrations/ImportUploader.test.tsx` | 11 passed; all 11 also passed in the full run |
| `uv run pytest tests/test_v2_projection_integrity.py tests/test_v2_event_registry.py -q --tb=short --show-capture=no` | 12 passed, 1 deprecation warning in 86.04 seconds |
| Strengthened cross-month HTTP/reporting regression | 1 passed, 1 deprecation warning in 33.18 seconds: September sale stays 1800, October net is -900 with zero gross units/sale transactions, year net is 900 |
| `npm run lint` | Exit 0 |
| `npm run typecheck` | Exit 1: `Forecasts.test.tsx:68` reads `sku_labels` on `ForecastResponse`; that field exists on `PersistedForecast` |
| `npm test` | 323 passed, 8 failed across 4 other files, 273.52 seconds |
| Isolated rerun of the 4 other frontend files | 57 passed, 2 failed, 31.39 seconds; remaining failures are duplicate `Orders due` dashboard selectors |
| `uv run pytest` | 1118 passed, 10 failed, 4 warnings in 731.70 seconds; all V2 tests passed |
| New projection regression and migration Ruff checks | All checks passed |
| Scoped tracked `git diff --check` | Exit 0 (line-ending warning only) |

The eight frontend failures are in unchanged `usePersistedForecast.test.tsx`
(2), `Forecasts.test.tsx` (1), `Inventory.test.tsx` (1), and
`PlanningBriefDashboard.test.tsx` (4). They involve expected forecast request
arguments versus current search arguments, a missing inventory empty-state
string, and duplicate dashboard labels. They are recorded rather than weakening
their assertions or modifying unrelated product behavior. Full outputs are
saved alongside this report. No live browser/E2E run was performed.

Other forecast/inventory source and test files changed outside this repair while
verification was running (their write times are later than the full-run start).
The isolated rerun therefore measures a later workspace state; it is not evidence
that all six disappearing failures were timing-only. Those edits were preserved.
`repair-source-hashes.json` records the reviewed repair source files separately.

The ten backend failures are outside the four-blocker implementation:

- Seven forecast scale/persistence cases fail with PostgreSQL
  `AmbiguousParameterError: could not determine data type of parameter $3` on
  the nullable search parameter in the saved-forecast count query.
- Two interactive integration cases fail: a direct inventory adapter receives a
  FastAPI `Query` default rather than a supported attention-filter string; the
  HTTP scenario request returns 422 where the existing test expects 200.
- The allocation property test raises Hypothesis `FailedHealthCheck` for slow
  input generation (2 valid inputs in 1.45 seconds). Its isolated rerun passed
  (1 passed in 0.62 seconds), without changing or suppressing its health checks.

Manual completion review checked the active-mode guard/callback, proportional
net/tax allocation and rounding, original-sale locking, duplicate registration
outcomes, serialized draft approval, credit signs/dates/identity, transaction
counts, and migration scope/failures. Reviewed repair-source hashes remained
unchanged through the final check. No merge, commit, deployment, live migration,
or broader V2-completion claim was made. The four repairs have passing focused
coverage; the shared workspace's full verification is **not clean**.
