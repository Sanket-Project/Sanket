# Import and planning repairs

Completed. Evidence and final checks: `docs/audit/2026-10-28-import-planning-repairs.md`.

Scope approved by the user on 2026-10-28. Preserve existing uncommitted work.
Follow systematic investigation and RED → GREEN → REFACTOR for each change.

Each numbered step is a small work unit (approximately 2–5 minutes); repeat
investigation units as needed rather than guessing when evidence is incomplete.

1. Reproduce strict RLS inspection failure and missing metadata in isolated tests.
   Verify: tests fail because startup currently succeeds.
2. Make strict startup reject unverifiable isolation; preserve development warnings.
   Verify: guard regressions and existing RLS integration tests.
3. Trace imported return representation and write API regression fixtures covering
   sale, return, aggregate sale-with-returns and mixed currencies.
   Verify: before-return amounts fail in summary, series, ranking and locations.
4. Apply a shared before-return revenue expression without changing net revenue.
   Verify: sales regression and existing analytics tests.
5. Test location terminology separately from explicitly identified report branches.
   Correct transactional sales labels while retaining report branch semantics.
   Verify: Sales Analytics and client report component tests.
6. Reproduce catalogue truncation and inventory lookup truncation beyond page one.
   Verify: pagination/lookup regression tests fail with existing requests.
7. Implement complete paginated catalogue retrieval and inventory SKU lookup,
   including failure states that cannot masquerade as a complete catalogue.
   Verify: API and page regressions, including later-page errors.
8. Reproduce the provider deadline/cancellation test failure; establish whether
   dispatch is reached before cancellation. Fix only the evidenced cause.
   Verify: focused test and neighbouring provider orchestration tests.
9. Trace forecast freshness/error display and inspect available refresh evidence.
   Test and repair misleading saved-result presentation if reproduced.
   Verify: persisted forecast tests; distinguish live verification from fixtures.
10. Run frontend typecheck, lint, tests and backend pytest. Review only this
    task's diff against scope; record actual outcomes and remaining limitations.
