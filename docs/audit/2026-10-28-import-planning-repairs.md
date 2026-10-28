# Import and planning repairs — 28 October 2026

Scope approved in chat. Existing uncommitted workspace changes were preserved;
no data was deleted or reimported and no commit was created.

## Findings, repairs and regression evidence

- **Production RLS startup:** inspection exceptions and missing role/table metadata
  previously passed. Three regression cases failed before the guard change.
  Production also launched its inspection in a background task; a lifespan test
  proved other services could start first. Isolation verification now runs before
  other services, closes the database on failure, and aborts startup. Development
  retains warning-only behavior. This is a startup-guard repair, not a comprehensive
  audit of every RLS policy.
- **Sales before returns:** four API regressions reproduced 900 instead of 1,000
  using a sale/aggregate-return row plus legacy and V2 standalone returns.
  Summary, timeseries, product ranking and location comparison share the same gross
  expression. Explicit return events and legacy zero-sold-unit return rows with
  negative gross amounts are excluded from gross sales. Net amounts and returned
  units remain intact. Standalone legacy returns no longer inflate sale-record counts.
- **Inventory import:** the frontend already paginated at the supported 200-row
  limit. Backend ordering by creation timestamp alone repeated/omitted rows when
  bulk-created SKUs shared a timestamp. A 1,199-SKU integration fixture reproduced
  the omission. A unique ID tiebreaker now gives stable ordering. The product list
  had the same defect and received the same repair after a failing integration test.
- **Products:** the page previously requested only 100 products, while its SKU
  count request exceeded the server cap. Both lists now retrieve all bounded pages;
  a later-page failure rejects the partial result. The page displays 24 products
  at a time, searches the full list, scopes query caches by tenant/industry, and
  reports loading/errors without presenting a false empty catalogue.
- **Locations:** transactional sales display location terminology. Explicit branch
  reports retain branch terminology; existing client-report tests pass.
- **Forecast presentation:** the API's stale flag was not exposed to the forecast
  page or dashboard snapshot. Both now visibly identify stale saved results during refresh, and failure
  text explains that the saved result may not include latest data. Two page tests
  failed before the forecast-page changes, and another failed before the dashboard
  wiring change. Healthy saved results remain available.
- **Provider test:** the reported 1-versus-2-call failure reproduced both without
  and with a 40 ms admission delay. A fixed 20 ms sleep was not evidence that a
  second dispatch had started. Cancellation now waits on a dispatch event, with a
  bounded timeout. The deadline case remains separate and uses a ten-second fake
  provider operation to verify a half-second deadline. Production retry code was
  not changed. All 18 provider-service tests passed after this test repair.

## Live read-only verification

The in-app browser was signed out, so the existing signed-in Chrome workspace
was used for read-only checks and returned to its Forecasts page afterward.

- Sales Analytics displayed **₹8,30,85,379 before returns**, matching the source
  figure in the user's report. Its location comparison showed `default` and
  `warehouse-a`, with amounts ₹4,24,73,781 and ₹4,06,11,598 respectively.
- Products displayed **161 products**, including an **Imported items** container
  (`__imported__`). The file importer creates this container; 160 validated source
  rows therefore need not imply exactly 160 product records in the database.
- Forecasts displayed a saved run generated **28 October 2026 at 16:13:03 IST**,
  with **1,116 forecast SKUs**, **83 omissions**, and a **12-week horizon**.
  There was no failed-refresh banner or stale warning. This verifies availability
  of a completed saved result; it does not validate predictive accuracy or prove
  the identity of the earlier retry without a refresh-job trace.

## Final verification

Frontend final verification: `npm run typecheck` and `npm run lint` both exited 0;
`npm test` passed **354 tests in 69 files** (135.06 seconds). This final run includes
the dashboard stale-result regression added during review.
Backend `uv run pytest` exited 0: **1,159 passed**, with three deprecation warnings,
in 515.07 seconds. The formerly failing deadline/cancellation test passed for both
normal and delayed admission. Warnings concern Argon2 version access and existing
uses of `datetime.utcnow()`.
Focused guard/isolation, sales/currency/location/gap, pagination, catalogue,
location-label, client-report and provider-service checks passed as recorded above.
`git diff --check` passed (line-ending notices only).

Manual review covered the startup ordering and error paths, sales return predicate
and net-revenue preservation, stable page ordering, complete-list error propagation,
tenant/industry query keys, report-versus-location terminology, stale-state display,
and the dispatch/cancellation handshake. No migrations or dependency changes were
needed. Live imports were not rerun because their reconciled inventory was already
present; import lookup correctness was exercised against a disposable 1,199-SKU
database fixture instead.
