# Fashion Retail V2 P0 Repair and Integration Plan

Date: 28 October 2026  
Status: Approved execution plan for the independently verified partial baseline.

## Root-cause summary

The review reproductions fail because V2 helpers are isolated from the real
import workflow, several validators coerce typed zero/invalid CSV shapes
silently, the return table has a tenant-unsafe foreign key, event registration
uses a check-then-insert race, posting groups share the caller transaction, and
return/financial validation trusts values that must be reconciled to the
original sale. Inventory, catalog, and valuation also lack persisted authority
and provenance checks required by the approved architecture.

## Execution tasks

Each task follows RED -> GREEN -> REFACTOR and is verified before the next task.

1. **Promoting review probes to regression coverage**
   - Add the 14 required scenarios to normal backend regression tests without
     weakening the review assertions.
   - Verification: targeted test files fail for the same reasons, then pass
     after their corresponding repairs.

2. **Hardening CSV and scalar validation**
   - Reject duplicate/normalized-collision headers, invalid row widths, unknown
     schema/entity versions, and nonfinite/invalid numeric values while
     preserving row/cell locations.
   - Preserve native numeric zero and require timezone-aware business times.
   - Verification: contract, sales, inventory, and review regression tests.

3. **Repairing tenant-safe schema relationships**
   - Inspect the live migration state and preserve applied migration 0036.
     Add a forward migration for composite tenant-scoped references and
     application-role cross-tenant tests.
   - Verification: disposable migrated database with RLS and direct FK probes.

4. **Making return lifecycle and reconciliation explicit**
   - Permit only approved returns to affect facts, revenue, tax, settlement, or
     stock; validate original source/transaction/line, SKU, currency, dates,
     discounted allocations, cumulative quantity/value/tax, disposition, and
     refund limits.
   - Verification: draft/rejected/retry/correction and original-sale mismatch
     tests, including no duplicate effects.

5. **Making registry and posting groups concurrency-safe**
   - Replace check-then-insert with a unique-conflict-safe registration protocol
     that returns the committed outcome for identical payloads and an explicit
     conflict for different payloads.
   - Add savepoint/transaction boundaries so failed groups leave no facts or
     registry rows while independent valid groups can continue.
   - Verification: concurrent upload tests, commit-before-ack retry, duplicate
     fact/stock assertions, and rollback-after-earlier-line tests.

6. **Completing catalog, inventory authority, and historical valuation**
   - Resolve tenant-scoped parent references and preserve declared SKU/product
     fields; enforce variant identity and category/size/currency/pricing rules.
   - Validate all inventory buckets and authority periods, connect stale checks
     to persisted updates, and prevent replaying historical sales into an
     already-baselined snapshot.
   - Persist historical issue-cost provenance and qualify unavailable margin
     rather than substituting current cost.
   - Verification: focused catalog, inventory, authority, costing, and
     profitability tests.

7. **Connecting V2 to authenticated upload flow**
   - Dispatch supported V2 files/tables before legacy mapping, safely handle
     versions, reuse mapping/review/confirmation machinery, validate all rows,
     preview errors/changes, require explicit confirmation, atomically persist
     supported P0 records, and audit the result.
   - Keep unsupported kinds explicitly unavailable and prevent V1/V2 double
     posting for the same return.
   - Verification: authenticated HTTP integration tests plus relevant frontend
     typecheck/lint/unit and Playwright coverage where the upload UI is wired.

8. **Completion verification**
   - Review the diff and run targeted suites after each task, then the required
     full frontend and backend commands.
   - Report actual results, migration/V1 compatibility impact, unsupported
     behavior, and remaining warnings. Never mark the progress record complete
     while required P0 scope is unavailable.

## Follow-up execution breakdown (28 October 2026)

The independent seven-case reproduction was rerun before edits and failed 7/7.
The implementation sequence is:

1. **Return boundary and allocation** (independent): add a nested savepoint
     around registry, original-sale lock, validation, counter, and fact writes;
     verify failed callers can continue without an orphan identity. Add the
     draft-to-approved transition, zero-value behavior, and explicit final
     remainder allocation. Verify the return follow-up cases and original 14.
2. **Inventory retry identity** (independent): compare the complete
     source/snapshot/position payload before the stale watermark guard; count
     exact retries as skipped and reject changed payloads. Verify retry and
     concurrent snapshot tests.
3. **Tenant reference boundary** (depends on 1 and 2): resolve SKU and
     location codes under the authenticated tenant during preview and again at
     confirmation. Unknown operational rows remain blocked and are reported by
     row. Verify cross-tenant and unresolved-reference HTTP tests.
4. **Canonical application projection** (depends on 3): project only
     reference-resolved V2 sales into the existing historical-sales read model
     using a stable V2 record key; apply approved return credits once. Verify
     analytics readers and replay accounting without duplicating facts.
5. **Authenticated frontend flow** (depends on 4): detect V2 CSVs in the
     existing upload surface, call preview/confirmation, display row errors and
     final counters, and retain the existing mapping workflow for non-V2 files.
     Verify typecheck, lint, unit tests, and available E2E coverage.
6. **P0 audit and coverage** (depends on 4): record actual support for all
     eight schemas, add regression coverage for lifecycle, retries, references,
     projections, and migration state, then run the full required suites.
