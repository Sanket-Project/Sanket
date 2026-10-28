# Review of Copilot's V2 repair

28 October 2026. Verdict: **the previous 14 failure cases are fixed, but the requested P0 build is still incomplete and additional acceptance cases fail.** This review changes no application code. Test evidence uses disposable PostgreSQL databases, not client data.

## What improved

- The original independent 14-case reproduction suite now passes: 14 passed in 30.46 seconds.
- Migration 0037 adds the tenant-scoped return-to-sale FK without rewriting the existing migration. The original application-role cross-tenant test passes.
- Event registration uses INSERT ON CONFLICT and compares the existing payload. The original concurrent duplicate test passes.
- Sale groups have a savepoint. The original partial-sale rollback case passes.
- The reviewed CSV duplicate/width errors, inventory timezone/negative bucket cases, numeric zero, default variant uniqueness, tax mismatch and returns-only profitability crash are corrected for their tested scenarios.
- Draft/rejected returns no longer increment the sold-unit counter. This fixes the old probes but does not complete the approval lifecycle, as finding 3 explains.
- Authenticated `/api/v1/integrations/v2/preview` and `/v2/confirm` now exist for CSV sales, returns and inventory snapshots. The simple legacy upload route rejects V2-marked CSVs.
- The progress document now calls the implementation partial and explicitly lists unsupported catalog, purchasing, settlement, stock authority and historical cost work. This is more accurate than the earlier P0-complete claim.

## Remaining findings

### 1. [P1] Resolve tenant SKU/location references before enabling sale and stock imports

Locations: backend/app/services/integrations/v2/upload.py:85–122 and backend/app/services/integrations/v2/event_registry.py:137.

The preview calls pure scalar validators, not database reference validation. An empty tenant catalog receives `can_confirm=true` for sample SKU/location codes that do not exist. Confirmation then accepts the sale. The sale and snapshot tables store text codes without catalog/location FKs, so this is not caught later by the database.

Required correction: resolve the tenant's SKU, product parent, selling/fulfillment/receiving location and registered source before successful confirmation; surface errors in preview and revalidate at posting time. If the intended feature is unlinked analytical staging, label it staging and prevent posting success being presented as a valid operational sale. The current HTTP happy-path test asserts success without seeding any catalog, so it misses this requirement.

Reproduced by `test_v2_http_rejects_unknown_sku_and_location`; the separate analytics probe also confirms a successful HTTP insert into an empty tenant's V2 sale facts. No cross-tenant catalog access is asserted by these probes.

### 2. [P1] Distinguish an identical inventory retry from a stale conflicting observation

Location: backend/app/services/integrations/v2/upload.py:127–136.

Confirmation checks `incoming.as_of <= max(as_of)` before checking source/snapshot identity or payload. After a successful two-position snapshot import, repeating the identical file with the same preview token fails with `Inventory snapshot is stale for this SKU and location`. A client retry after a lost response therefore cannot obtain the prior success outcome. Snapshot ingestion does not use the event registry.

Required correction: identify an exact same-source/snapshot/position retry and return its previous result/skip; distinguish changed payload conflicts from genuinely stale new observations. Make the per-position time/authority guard concurrency-safe so overlapping confirmations cannot both validate against an old max timestamp. The stale query currently also ignores source authority.

Reproduced by `test_inventory_exact_retry_is_idempotent`.

### 3. [P1] Provide a draft-to-approved transition for returns

Locations: backend/app/services/integrations/v2/event_registry.py:194–204, and compute_payload_hash.

A draft return is registered and stored under the final return identity, with status included in its payload hash. Reposting the same return as approved raises EVENT_PAYLOAD_CONFLICT. There is no approval/update API to advance that draft. Requiring a new return ID would lose the single lifecycle identity and is not an adequate implicit workaround.

Required correction: define authorization/draft storage separately from immutable posted return effects, or add an explicit versioned transition with locking and exact-once approved effects. Keep immutable posted-event conflict protection. Also correct remaining_sold_qty: the result subtracts the draft's quantity even when the persisted counter was correctly left unchanged.

Reproduced by `test_draft_return_can_be_approved_under_same_identity`.

### 4. [P1] Handle zero-value original sales without dividing by zero

Location: backend/app/services/integrations/v2/event_registry.py:240.

The return tax check divides original tax by original net_sale_ex_tax. A supported fully discounted sale has net=0 and tax=0. Returning one unit at zero credit/tax raises decimal.InvalidOperation/DivisionUndefined instead of recording the quantity return. The public confirm route catches ValueError/TypeError, not this decimal exception, so this path is not a clean row-level validation response.

Required correction: use the original tax/allocation facts without dividing by a possibly zero monetary base. Define zero-price/fully-discounted return behavior and test it through HTTP as well as the posting service.

Reproduced by `test_zero_value_sale_has_valid_zero_value_return`.

### 5. [P1] Allocate the final return's rounding remainder from original totals

Locations: backend/app/services/integrations/v2/event_registry.py:240,265–272.

Each return is independently capped at a rounded per-unit share, and tax is recomputed from that return's credited amount. This cannot reproduce the original totals when paise do not divide evenly.

Reproduction: three units produce original ex-tax net 10.00 and tax 0.50. The first two one-unit returns credit 3.33 and tax 0.17 each. The final return must credit the remaining 3.34 and tax 0.16 to reconcile exactly. It is rejected with RETURN_TAX_MISMATCH; the fixed per-unit value cap would also reject the final 3.34. quantize calls here also use the ambient rounding mode rather than the documented explicit half-up policy.

Required correction: preserve deterministic original allocation and cumulative credited amounts. The last return consumes the remaining allocation, under the same original sale lock, without exceeding original quantities/value/tax. Cover prices, discounts and rounding residuals across multiple partial returns.

Reproduced by `test_final_partial_return_gets_original_rounding_remainder`.

### 6. [P1] Give return posting the same failure boundary as sale groups

Location: backend/app/services/integrations/v2/event_registry.py:187–204.

Sale posting now has begin_nested(), but return posting still registers its event before validating the original sale and has no service-level savepoint. When the original sale is absent and the caller catches ValidationError, the caller transaction retains one registry entry with no return fact. If that caller continues and commits other work, a retry can be skipped against a nonexistent posted return.

The current HTTP confirm transaction rolls back when the error escapes; the reproduction does not claim a failed HTTP request itself commits an orphan identity. It proves that the reusable posting-group/partial-import contract remains unsafe for callers that catch business errors, the same usage that motivated the repaired sale-group test.

Required correction: wrap the entire return registration/validation/counter/fact group in an enforced savepoint or equivalent group transaction contract. Add return failure/catch/continue coverage, not only sale failure coverage.

Reproduced by `test_invalid_return_does_not_leave_registered_identity`.

### 7. [P1] Complete application reads and UI before presenting V2 as a working retail import

Locations: backend/app/services/integrations/v2/upload.py:120–173; frontend/src; existing analytics/inventory read services.

The new endpoints insert V2 side tables. No production reader outside the V2 package consumes those tables, and the existing sales history and inventory balance paths remain separate. An HTTP-confirmed sample sale succeeds while the tenant's existing historical_sales count remains zero. This is evidence of missing integration, not a requirement to blindly duplicate every V2 row into the legacy table. A correctly designed canonical read projection or updated readers would also satisfy the requirement.

There are no V2 endpoint references under frontend/src. The existing upload UI therefore cannot run the new preview/confirm workflow. Preview returns column names, row count and scalar errors but no business effects, financial controls, catalog resolution or database duplicate/link checks. Its parser is CSV-only; no XLSX table selection or retailer column mapping is connected to this V2 path.

Required correction: connect supported V2 events to the agreed read model and existing analytics without duplicate effects; wire the UI and mapping/preview/confirmation boundary with integration/E2E tests. Keep unsupported modules unavailable until implemented. This is consistent with the progress document's partial status and should remain a release blocker for the requested end-to-end build.

Reproduced missing read-model bridge by `test_v2_sales_appear_in_existing_analytics_history`; static searches confirm missing frontend V2 callers and missing non-V2 table readers. No browser UI execution is claimed.

## Explicitly unfinished scope, not newly completed functionality

Copilot's updated progress record acknowledges these remain unsupported:

- Product/SKU persistence and full category-governed reference validation.
- Supplier/location/purchase import lifecycle.
- Independent payment/refund facts and settlement reconciliation.
- Complete stock authority, balance projection, movement ledger and cutover.
- Persisted historical issue-cost provenance.

These are substantial parts of the original P0/P1 design. The repair did not complete the build requested in the prompt. It improved a subset of safety behavior and added a narrow backend CSV API. The accurate status is **partial repair with passing original probes; additional defects and end-to-end scope outstanding**.

## Test coverage and evidence

Original review: 14 passed in 30.46 seconds. The original probes remain separate from backend/tests and are not promoted into normal regression coverage; the normal suite gained only the two upload-flow tests. Those tests cover one successful sale confirmation and one legacy upload rejection, not all authentication/atomicity/rollback/return/inventory scenarios their names might suggest.

Follow-up review: 7 failed, 1 warning in 38.80 seconds. The tests specify required behavior and expose the remaining failures. Six initial probes were run first; after identifying the distinct rounding-remainder issue, the expanded seven-case suite was run once. followup-results.txt contains that final run.

See VERIFICATION.md for the independently rerun full repository results. Testcontainers/real migrations and the restricted app-role fixture were used for service database cases. HTTP cases use synthetic signed-in workspaces in a disposable database. No application code, existing progress claims or client data was modified by this review. No production migration, deployment or browser/E2E test was performed.
