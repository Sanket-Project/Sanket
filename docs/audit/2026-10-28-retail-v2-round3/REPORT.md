# Third verification of the Fashion Retail V2 implementation

28 October 2026. Verdict: **several prior repairs are verified, but the frontend import flow is blocked and the new projection/return logic has additional correctness defects. The complete P0 build remains unfinished.** No application source was modified during this review.

## Verified improvements and a corrected test assumption

The original 14-case review suite and the seven-case follow-up suite were independently rerun together. Result: 20 passed, 1 failed. The one failure is the old analytics probe that confirms an operational sale into an empty tenant catalog. Copilot is correct that this fixture is now invalid: the endpoint returns HTTP 400 with unresolved SKU/location messages. That failure should be addressed by seeding valid tenant references, not by weakening reference validation.

A new fixture-correct test creates a tenant product, SKU and location, posts a sale through HTTP, retries it, and verifies exactly one historical_sales row. **That test passes.** Basic reference-resolved sale projection and sequential sale retry therefore work. The five earlier rollback/draft approval/zero-value return/snapshot retry/final-remainder cases also pass in the old suite.

These improvements do not prove the claimed full frontend or financial behavior. The remaining findings below are reproduced with valid fixtures where applicable.

## 1. [P1] The V2 Import button cannot execute confirmation

Locations: frontend/src/components/integrations/ImportUploader.tsx:68–78,119–125,209.

analyze() clears analysis, detects a V2 CSV, sets v2Preview and returns without setting analysis. The Import button's disabled condition correctly allows v2Preview without analysis, so the button appears enabled. However, run() immediately returns when `!analysis`, before reaching its v2Preview branch. Clicking Import therefore calls no confirmation API. This blocks every file that takes the intended V2 preview path.

Required correction: gate the handler on the active preview mode, or handle V2 before the legacy-analysis requirement. Add an interaction test that supplies a V2 File with readable prefix, waits for preview, clicks Import and asserts v2Confirm was called. The existing ImportUploader tests mock only legacy analyze/upload, so their passing result does not verify V2 confirmation. Also test onImported/query invalidation after success: the V2 branch currently sets a local result/toast without invoking the existing completion callback.

Review test: frontend/review/V2Upload.review.test.tsx. Review configuration: frontend/vitest.retail-review.config.ts. These are review artifacts outside normal src testpaths; no production component was changed. See ui-results.txt for the actual interaction failure.

## 2. [P1] Partial-quantity returns can claim almost the entire sale value

Location: backend/app/services/integrations/v2/event_registry.py:315–334.

The rounding repair removed the old per-quantity value cap. It now caps nonfinal returns only against the remaining whole sale value and checks proportional tax, not the original unit/discount allocation.

Reproduction: the sample sale recognizes two equally priced kurtis for INR 1,800 net plus INR 90 tax. Returning one should credit INR 900 plus INR 45. The API instead accepts one returned unit claiming INR 1,700 net and INR 85 tax, with a refund of INR 1,785. The second remaining unit would then be forced to take only INR 100 net on final return. This is not a paise remainder issue: it is an incorrect original-price allocation.

Required correction: preserve original allocation by unit/quantity, with a bounded deterministic remainder on the last units. Keep whole-sale cumulative caps and original-sale locking. Any goodwill or additional price adjustment must use a separately identified financial workflow rather than over-crediting a physical return line. Do not restore an inflexible independently rounded cap that breaks the previously fixed final-remainder test.

Reproduced through authenticated preview/confirmation by `test_partial_quantity_return_cannot_claim_almost_all_sale_value`: expected HTTP 400, actual HTTP 200.

## 3. [P1] Return projection changes the original sales day instead of recording the return day

Location: backend/app/services/integrations/v2/upload.py:231–253.

Approved returns UPDATE the original historical_sales row, increasing its returns and subtracting its revenue, while retaining that row's original sale_time. No dated credit/return projection is added. As a result, a later return rewrites earlier period results and is absent from the actual return day's history-based analytics.

Reproduction with valid tenant fixtures: sale on 2 October has INR 1,800 ex-tax net. A one-unit INR 900 credit occurs on 3 October. After confirming the return, the 2 October historical sales value becomes INR 900 rather than preserving its recognized INR 1,800 and recording the credit on 3 October. This contradicts the approved default recognition-date reporting contract. A cohort/original-sale-attribution report can be useful, but must be separately labeled and must not replace credit-date financial reporting.

Required correction: project dated sale/credit facts or update readers to consume dated canonical return events with explicit reporting basis. Preserve gross demand, net revenue, return quantities and exactly-once behavior without counting the credit in both the modified original row and a new credit row.

Reproduced by `test_return_does_not_restate_the_previous_days_sale`: actual original-day value INR 900, expected INR 1,800 under the approved recognition-date contract. This is a database read-model verification; no browser report rendering is claimed.

## 4. [P1] Colon-concatenated projection keys can silently merge distinct source events

Locations: backend/app/services/integrations/v2/upload.py:195–203,236.

The event registry correctly uses a tuple of source/transaction/line. The projection flattens these values to `v2:{source}:{transaction}:{line}` without escaping or length-prefixing, then treats that string as unique identity. External identifiers are unrestricted text and may contain colons.

Reproduction: source `REVIEW:A`, transaction `B` and source `REVIEW`, transaction `A:B`, with the same line ID, are two different canonical event identities. Both confirmations succeed and create separate V2 sale events. Both form the same historical record key, so only one historical sale is projected. One sale disappears from analytics; a later return can also target the wrong projected record through the same key construction.

Required correction: use an unambiguous encoded tuple/hash or canonical event UUID to identify each projection. Apply the same identity function to sale and return paths. Migrate existing keys safely and retain retry behavior.

Reproduced by `test_distinct_external_identities_do_not_collide_in_projection`: two events confirmed, only one historical sale instead of two.

## Remaining scope and static findings

- The approved P0 scope is still not complete. Products/SKUs, suppliers, locations and purchase import persistence remain unsupported. Complete stock-authority/balance projection, movements, separate payment/refund records and persisted historical issue-cost provenance are not delivered by this patch.
- Inventory confirmation still writes snapshot facts without updating the existing inventory balance read model. Do not imply stock displays are operationally updated by those uploads until authority/projection behavior is completed and verified.
- Source registration is not resolved by validate_tenant_references; it checks SKU/location strings. It also enumerates the compacted valid-row list from row 2, so reference error row numbers can be wrong when an earlier row has a scalar validation failure. These are static findings, not additional claimed probe failures.
- The preview does not yet show full original-sale/duplicate/authority/financial effect validation. The frontend statement that financial controls passed is stronger than the database checks actually performed in preview.
- The lifecycle transition and concurrent inventory behavior require wider regression coverage than the old sequential probes. No complete concurrency certification is claimed here.

## Verification and evidence

- Original and previous follow-up probes: 20 passed, 1 fixture-incompatible failure in 44.37 seconds.
- New reference-correct HTTP projection tests: 1 passed, 3 failed in 94.72 seconds. Output: projection-results.txt.
- New frontend confirmation interaction: 1 failed, with the 324 existing frontend tests passing in that invocation; see ui-results.txt. The initial review config inherited the existing includes, so that invocation also ran existing tests. The saved review config now explicitly narrows discovery to review/ for focused reruns.
- Full normal repository checks and exact counts are recorded in VERIFICATION.md after completion.

The same allocation property-test name failed during the independent full backend run, but the actual error was Hypothesis FailedHealthCheck for slow input generation under load, not a failed supply/need assertion. Neither that test nor backend/app/services/allocation.py has a working-tree diff. This should be reported separately from V2; it is not proof of a pre-existing allocation correctness bug, nor grounds to call the full run green.

No production migration, client data mutation, deployment or live stock-authority cutover was performed. Database and HTTP probes use synthetic tenant records in disposable migrated PostgreSQL testcontainers. Application source was left unchanged. Review-only tests/configuration and this report were added for reproducibility.
