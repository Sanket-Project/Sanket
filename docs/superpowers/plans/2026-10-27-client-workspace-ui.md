# Approved client workspace redesign — execution plan

Design approved by the user on 2026-10-27: docs/audit/2026-10-27-client-ui-discovery/PROPOSAL.md.

Completed: all implementation/review steps and required checks. Backend 688 passed; ML 73 passed; frontend 262 passed plus typecheck/lint. Browser evidence and bounded collection/attention-filter scope: docs/audit/2026-10-27-client-ui-discovery/IMPLEMENTATION.md.

Follow the manual Superpowers workflows from AGENTS.md: write a failing test, observe the intended failure, implement the smallest change, verify and review before continuing. Work in isolated file ownership contexts; do not restore demo business data. Each numbered item is a short implementation increment (roughly 2–5 minutes), repeated where multiple cases are needed.

## Catalogue trends backend context

1. Read catalogue/sales/geography schemas and existing trend tests; specify a bounded tenant-scoped company trends API. Verification: documented contract agrees with actual schema.
2. Test empty catalogue and cross-tenant exclusion; implement catalogue-driven response. Verification: targeted pytest RED then GREEN.
3. Test period-based uploaded sales totals/change and product/SKU selection; implement SQL aggregation. Verification: targeted pytest including zero prior sales and missing history.
4. Test catalogue keyword matching for public external interest without unrelated products or made-up confidence. Implement bounded relevance filtering and source/freshness. Verification: targeted pytest.
5. Test state/city granularity validation in regional ingestion. Implement preserving granularity and no inferred district scores. Verification: connector tests.

## Trend Analysis frontend context

6. Test searchable labelled combobox selection, filtering, keyboard/Escape/outside dismissal; implement reusable control. Verification: component Vitest RED then GREEN.
7. Test complete Telangana district list, dependent state/district choices and honest district empty state; implement using official reference. Verification: unit/component tests.
8. Test company catalogue API loading, empty import prompt, sales versus external signal labels, product/SKU filters and errors; implement redesigned Trend Analysis. Verification: page tests and typecheck.

## Inventory context

9. Read existing inventory/coverage/recommendation contracts. Test paginated SKU overview, location filtering, search and accurate counts beyond 500 positions. Implement bounded backend query and API types. Verification: targeted backend tests.
10. Test one row per SKU, expandable stores, shortage without recommendation and no pooled-as-store cover. Implement plain-language inventory presentation. Verification: page Vitest RED then GREEN.
11. Test attention filters, pagination and empty import onboarding. Implement controls preserving import/export and provenance. Verification: page tests and existing import tests.

## Dashboard context

12. Test a single aligned confidence field with score, readable band and reasons, including absent evidence. Replace floating capsule and simplify surrounding hierarchy. Verification: dashboard component tests RED then GREEN.

## Integration and completion

13. Review changed interfaces and source diffs for tenancy, honest missing-data handling, bounded requests, accessible controls and unrelated-change preservation. Verification: focused tests for integration issues, then green tests after fixes.
14. Run frontend typecheck, lint and all Vitest tests; backend full pytest; ML pytest regression suite. Record actual outputs and any reproducible failures.
15. Use the in-app browser to inspect dashboard, company trends, Telangana district selection and inventory empty state at desktop/narrow widths. Preserve screenshots and report limitations; keep the live workspace empty. Review diff and report concrete results.
