# Size recognition and import layout verification

## Change

- Backend recognises 1X–6X and FR/FRE aliases through the shared size normaliser.
- Import responses explain numeric clothing sizes, ranges including compact
  `STO2XL`, and unresolved source-specific codes.
- Numeric sizes/ranges are described without converting them into a letter enum.
- Original size codes remain in SKU identity. Explicit blank overrides win.
- File-import dialog supports a 1600px width and a bounded scrolling body.
- Responsive bordered cards label code, row count, meaning and size selection.
- All codes are searchable; the previous 60-code limit is removed.
- Review filtering, keep-blank and reset controls support corrections.

## Checks

- RED: 10 backend tests failed for missing aliases/meanings; UI tests failed
  for hidden recognised codes and missing wide-dialog behavior before changes.
- Focused backend tests: 40 passed, 3 database cases deselected (covered by full run).
- Frontend typecheck and lint: exit 0, including a repeat after added tests.
- Full frontend suite: 67 files, 332 tests passed.
- Final SmartImport focused run: 8 tests passed, including two additional cases
  verifying an explicit blank sent to the API and reset to automatic detection.
- Browser fixture: desktop dialog measured 1600px at a 1920px viewport.
  No horizontal overflow at 375px, 768px or 1440px; controls fit their viewport.
- Browser interactions verified numeric search, clearing an automatic suggestion,
  and resetting it. Light/dark and mobile screenshots inspected.
- Scoped `git diff --check`: clean. Diff reviewed for API compatibility,
  original-code retention, manual overrides, responsive layout and modal scope.

Screenshots use an explicitly labelled preview fixture, not a live customer import.
Temporary preview entry files were removed after visual verification.

Initial full backend suite: **1136 passed, 2 failed, 4 warnings in 424.60s**.
All smart-import, API, transform, fashion-size and new recognition tests passed.

Failures outside the changed size/import path:

- `tests/llm/test_interactive_integration.py::test_qa_adapters_enforce_real_rls_and_scope_foreign_sku`
  raises `ValueError: unsupported inventory attention filter: ... Query(all)`.
  `interactive_service.read_operation` calls the `stock_overview` route directly
  without its `attention` and `sort` arguments, so FastAPI Query descriptors reach
  `inventory_overview` instead of resolved string defaults.
- `tests/llm/test_interactive_integration.py::test_authenticated_http_question_and_scenario_journey`
  receives HTTP 422 (`Use explicit supported assumptions or a read-only workspace
  data question`) on the same AI inventory-question path.

These paths were outside the initial size-recognition change and were not edited
in that initial pass. That test run was not green; the follow-up below repairs it.

## Follow-up: local rollout and AI inventory repair

User requested fixing both failures and clarified that rollout means the local
app only, with no GitHub push or remote deployment.

- Reproduced the two failures: 2 failed, 2 passed in the integration file.
- Fixed the shared cause by supplying `attention="all"` and `sort="sku"`
  explicitly when the AI adapter calls the inventory route directly.
- Focused integration/service/inventory tests: 18 passed.
- Final frontend rerun: 67 files, 334 tests passed; typecheck and lint passed.
- Uvicorn detected the edit but its prior worker did not exit. Stopped only the
  verified stale backend child, allowing its existing reloader to start worker
  11252 successfully. Backend health returned HTTP 200 with status `ok`.
- Local frontend returned HTTP 200 and served the updated size-card and review
  filter source. Local ML health also returned HTTP 200.
- All file edits remain local. No commit, push, or remote deployment was made.

Frontend production build: passed (`tsc -b` and Vite, 1m 23s).
Vite reported its existing large-chunk advisory; compilation succeeded.

Full backend rerun: **1137 passed, 1 failed, 3 warnings in 554.94s**.
Both original AI inventory failures passed in this run.
The remaining failure was Hypothesis `FailedHealthCheck` for slow input
generation in `test_allocation.py::test_never_exceeds_supply_or_need` (one draw
took 1.303 seconds), rather than a failing allocation assertion.

Without modifying production code or disabling test checks:

- Replayed the recorded seed `207125634910250683365405135159967849800`:
  allocation file **9 passed in 1.71s**.
- Reran allocation and AI integration files with normal randomisation:
  **13 passed in 22.43s**.

All cases now have passing verification, but the full-suite invocation itself
was not wholly green because of that input-generation timing health check.
