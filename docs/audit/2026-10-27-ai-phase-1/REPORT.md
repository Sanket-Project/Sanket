# AI Phase 1 verification record

Date: 2026-10-27. Branch: `codex/ai-phase-1`.

Status: implementation and review in progress. This is not a completion claim for Phase 1 or later phases.

The user approved the remaining-phase design and plan with “proceed with the build,” then requested continued work after interruption. The original checkout contained substantial unrelated edits. [Starting-state hashes](starting-state.json) record the reviewed baseline; no unrelated edits were reset.

## Implemented paths under verification

- Private typed AI task registry, independent task flags, explicit aggregate/product-name permissions, task/version/language/actor/snapshot cache separation, and actual task metadata in accounting.
- Fact-ledger narrative selection. The model selects bounded fact/proposition IDs; source values and links are rendered by the server.
- Authenticated workbook analysis, bounded local discovery, physical column IDs, delayed/multilingual/merged headers, formula-cache warnings, kind-aware sheet ranking, row exclusions, and explicit ambiguous-date choices.
- Signed workspace/actor/file/kind analysis binding; validation of selected tables before a shared import transaction; atomic successful-import-only format memory; replay success and RLS-protected management.
- Shared import review in Integrations and onboarding; stale-response/duplicate-mapping checks and visible model-estimate confidence.
- Server-grounded onboarding/connector assistance and data-quality explanations; reviewed attribute/category cleanup and duplicate hypotheses; version-checked confirmed writes with transactional audit.
- Repair previews bound to the source snapshot. Junk-row repair executes through a narrow non-login, non-superuser, non-BYPASSRLS role, preserving FORCE RLS.

## Observed RED/GREEN evidence

| Behavior | Observed RED | Observed GREEN |
| --- | --- | --- |
| Task registry | Missing registry module; unknown task and extra-field tests | Registry plus original contract suite: 13 passed. |
| Task policy/cache | Missing task-specific arguments and permission fields | Policy/default/cache tests passed; subsequent real Redis/service regression batch: 60 passed. |
| Facts and narrative grounding | Missing fact module, unknown narrative task | Strict reference/proposition/source/snapshot tests: 16 passed together with registry/policy cases. |
| Layout | Missing structured parser | Parser plus original importer: 56 passed; later layout/profile batch recorded separately. |
| Redwine inventory ranking | Selected Sales Ledger with an unfamiliar stock header | Correct sales and inventory sheets selected locally. |
| Format memory and analysis binding | Missing profile/binding implementation | Four real DB/token tests passed. |
| Confirmed writes | Missing confirmation service | Seven profile/binding/confirmation tests passed before additional date/replay cases. |
| API integration | No structured table response; then local `json` import shadowed the module | Two API tests passed after removing the shadowing import. |
| Shared UI | Missing uploader; parent forms did not show enhanced review | Shared uploader/Integrations/onboarding: 11 tests passed after date-review additions. |
| Settings | Missing configuration operation and routes | Settings plus existing policy tests: 14 passed. |
| Onboarding/data quality | Missing server context builder; natural connector question unresolved | Context/route/date group: 7 passed; later Phase 1 focused batch: 12 passed. |
| Product cleanup | Unregistered task; missing confirmation service | Six strict extraction tests and two real confirmation/rollback tests passed; UI preview/confirm test passed. |
| Replay | A zero-new-row replay was rejected | Revised acceptance counts include unchanged accepted rows; confirmation/Redwine batch: 7 passed. |
| Repair permissions | Application-role DELETE denied for `historical_sales` | Narrow RLS-bound function; repair and existing dedupe batch: 12 passed. |
| Stale repair preview | Missing preview-binding service | Stale source changes rejected; repair API/current-record batch: 3 passed. |
| Saved-format controls | Missing management methods/routes; JSON literal accidentally parsed as a SQL bind | Management/settings batch: 9 passed after parameter-safe JSON comparison. |
| Real SKU named Total | Inventory detail row silently excluded | Required-detail evidence retains such rows; included in the full suite. |

All automated model responses are mocked. No real DeepSeek call or real model-quality claim is included.

## Exact Redwine acceptance

The source workbook remained in its original local location and was not copied into the repository's fixtures. SHA-256: `6d3c3ce4fcd7f0ee94aaa111f4632bd510c997449c0748d607206d03f1a143d6`.

The exact-file test passed with real disposable PostgreSQL/Redis, the application role, real policy/accounting/orchestration, and mocked HTTPX provider responses:

- Sales Ledger: 500 accepted source rows; SKU, quantity, gross revenue, and location reconciled against deterministic row mapping.
- Warehouse Inventory: 150 accepted source rows; SKU and stock quantity reconciled against the selected source.
- Formula cells without cached results were reported as missing, not evaluated by the model.
- Re-upload applied the workspace-confirmed format without another provider dispatch and retained the Import action.

`uv run pytest tests/test_import_confirmation.py tests/llm/test_redwine_acceptance.py -q --tb=short`: **7 passed in 18.76s**, exit 0, before the final management additions.

## Full verification jobs

| Command | Observed result |
| --- | --- |
| Frontend `npm run typecheck` | Passed, exit 0. |
| Frontend `npm run lint` | Passed, exit 0. |
| Frontend `npm test` | **58 files, 281 tests passed**, 100.08s, exit 0. React Router future-flag notices emitted. |
| Backend first `uv run pytest` | **875 passed, 1 failed**, 3 warnings, 314.72s. Failure was the existing allocation property's Hypothesis input-generation health check: one draw took 1.145s. No allocation assertion failed. |
| Exact failed seed in isolation | `uv run pytest tests/test_allocation.py::test_never_exceeds_supply_or_need --hypothesis-seed=273030760587662207551261764074865507015 -q --tb=short`: **1 passed in 0.54s**. No test suppression or allocation code change. |
| Fresh full backend rerun | **876 passed**, 4 warnings, 267.59s, exit 0. |
| Final frontend after review regressions | Typecheck and lint exit 0; **58 files, 284 tests passed**, 81.12s. |
| Final backend after review regressions | **881 passed**, 3 warnings, 253.18s, exit 0. |
| Repair role and rollback checks | **3 passed**, 14.88s: non-superuser, non-bypass role; application DELETE denied; cross-tenant isolation and audit rollback. |
| Diff whitespace | `git diff --check`: exit 0; existing CRLF normalization warnings reported. |

## Running-app evidence

A distinct disposable PostgreSQL/Redis pair served the current backend on a dynamically selected loopback port. The application connected as `sanket_app`, and strict tenant-isolation checks passed. The frontend ran separately on port 5179. External signal, Shopify, WhatsApp, webhook retry, and real ML/model calls were disabled or replaced with test-only local transport. All business writes were to the synthetic smoke workspace.

Through the in-app Browser:

1. Signed into the synthetic workspace with AI disabled.
2. Analyzed a one-row CSV, reviewed the mapping/source preview, selected remember-format, and clicked Import.
3. Observed **1 new · 0 already imported · 0 corrected**. [Screenshot](ai-off-manual-import.png).
4. Enabled only test-workspace AI permissions and Phase 1 flags, with the provider still mocked.
5. Analyzed a synthetic Hindi `मात्रा` quantity column and unfamiliar retail-price column. The UI displayed **AI-generated · Model estimate: high**.
6. Confirmed the import and observed one new row. [Screenshot](mock-hindi-mapping.png).
7. Removed/reselected the same file. The UI displayed **Saved workspace format applied. Review and press Import**, with human-confirmed provenance. [Screenshot](saved-format-reuse.png).

The screenshots capture the actual narrow browser pane. Desktop/keyboard and degraded-state inspection remain review items until explicitly recorded. The test dashboard honestly reported the disabled ML source as unavailable; this is not a successful real-forecast check.

## Checkpoint review

- Review regressions cover malformed workbook XML, numeric-looking headers, bounded header search, contradictory category suggestions, repair audit rollback, preserved manual header choices, and currency scope reset.
- Reviewed 102 staged files. A credential-pattern scan found only the preexisting Docker development connection string; the Docker diff contains configuration variable references and no live secrets. Unrelated forecast/inventory changes, deletions, backups, and local credentials remain outside the index. The staged config excludes unrelated forecast settings.
- Phase 0 and migration revisions 0028/0029 are required dependencies of this checkpoint; unrelated forecast source is excluded.
- Browser evidence covers the narrow pane. A separate desktop viewport and complete keyboard walkthrough were not performed and are not claimed. Automated interaction/accessibility assertions passed; this remains a visual QA limitation.
- No real provider evaluation, production enablement, production email, or merge was performed. Later phases remain pending at this checkpoint.
- PR identity is recorded after creation.
