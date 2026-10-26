# Location forecasting implementation report

Date: 26 October 2026. Base: `311214a`. Work stayed on the existing local branch;
nothing was pushed and no PR was opened. Existing unrelated untracked files
were left untouched. Superpowers is unavailable to Codex in this session, so
the approved plan's literal RED → GREEN → review → commit sequence was followed
manually. No subagents were used.

## Task commits and targeted verification

| Task | Commit | Green targeted result |
|---|---|---|
| 1 | `eb351d5` | 41 passed; 25 additional scenario checks passed |
| 2 | `361e0a4` | 6 passed |
| 3 | `2d11925` | 7 passed |
| 4 | `9af9d65` | 4 passed |
| 5 | `16e6de6` | 7 passed |
| 6 | `bf676bc` | 15 passed |
| 7 | `1b67b40` | 14 passed |
| 8 | `08983ab` | 19 passed |
| 9 | `2cb0a53` | 13 passed |
| 10 | `71d9fd5` | 16 passed |
| 11 | `b487961` | 9 passed |
| 12 | `b3ddea1` | 48 passed |
| 13 | `47714a6` | 23 passed |
| 14 | `6249c41` | 8 passed |
| 15 | `3074109` | 26 passed |
| 16 | `4099dc8` | 3 component tests; typecheck and lint passed |
| 17 | `d292be3` | 207 passed / 45 files; typecheck and lint passed |
| 17b | `cbeed0c` | 6 API + 6 component tests; typecheck and lint passed |
| 18 | Commit introducing the final audit files | Final suites recorded below |

Each implementation task was committed separately with the plan's requested
message, and its checkboxes were updated. Final verification corrections belong
to Task 18 and are enumerated below.

## Adaptations and deviations

1. **Task 1:** the removed `MAX_SKUS` constant was also imported by
   `routers/forecasts.py` and `routers/scenarios.py`. Both were updated, as the
   plan's search instruction requires. A mistaken extra test filename
   `tests/test_scenario_api.py` produced `ERROR: file or directory not found`;
   the real `test_scenario_readiness.py` and `test_scenario_simulator.py` were
   then found and run (25 passed).
2. **Tasks 3/7:** exported both models from `app.models.__init__` so metadata
   registration follows the existing pattern. asyncpg returned catalog
   `relkind` as bytes (`assert b'p' == 'p'`); the schema test now casts it to
   PostgreSQL text without changing its assertion.
3. **Tasks 6/8:** entirely unassigned SKU history must not inherit assigned
   category demand. Added failing unit and DB tests, retained evidence even
   when assigned shares are empty, and passed that evidence into blending.
4. **Task 10:** the DB test seeds the same 12-history / 2-holdout-week shape
   directly, with non-flat history so MASE is defined. It uses completed
   historical dates rather than future forecast weeks. The implementation
   follows the plan's location-total scoring algorithm; it does not claim to
   average individual SKU-location scores.
5. **Task 11:** Hypothesis was absent and added to the backend development
   group. `uv add --dev hypothesis` wrote consistent dependency files but then
   returned Windows error 1224 (a user-mapped file was open). `uv lock --check`
   passed, and `uv run` installed the resolved packages. A failing extra test
   exposed the sample's zero-rate surplus allocation (`{'a': 50} != {}`);
   zero-rate stores are now excluded in both supply cases.
6. **Task 12:** also extended the pure `DecisionKind` literal and the router's
   kind-filter validation. An added API test first returned 422 for
   `kind=allocation`; it now returns route codes. ROI was tested with accepted
   allocations and transfers; its purchase-order accounting stayed unchanged.
7. **Task 13:** actual `stock_is_stale` is strictly older than 30 days, so the
   planned exactly-30-day fixture was corrected to 31 days. Added a 30-unit
   supply case because the plan's 100-unit fixture does not actually exhaust
   supply under its 10-day target. Baseline units are assigned at construction
   rather than afterwards with `dataclasses.replace`; the same sales-based
   proportional cap is used. Added frozen band/share/T inputs and degraded
   exclusions omitted from the sample implementation. A SQL metrics update
   left the loaded run stale; a failing refresh test required an ORM refresh.
   Per-location skips also made `skus_evaluated = -1`; the count now uses
   distinct evaluated SKUs. An existing `SimpleNamespace` serialization fixture
   gained the two new nullable fields; its money assertions were unchanged.
8. **Tasks 13/15:** tables without a `source` column were not given invented
   columns. Synthetic fixture provenance is explicit on inventory and in sales
   metadata. Task 15 sets the non-shortage stores to their p50 windows to isolate
   the required F → A transfer. Fixture helpers were copied, not imported across
   test modules.
9. **Task 16:** Network is a dedicated Settings tab (as the approved design
   specifies), rather than an always-visible card below unrelated settings.
10. **Task 17:** actual network decisions have different inputs from POs. Making
    the API type honest exposed eight TypeScript errors in six existing
    dashboard/navigation/alerts/fallback consumers. Added presence checks and
    an unavailable service-level display; no missing number was substituted.
    The route helper is in `pages/decisionsRoutes.ts`. Network working expands
    the frozen inputs rather than applying PO-only arithmetic.
11. **Task 17b:** the existing Forecasts page had no selected SKU, so a SKU
    selector was added for the location table. Final verification added the
    location filter required by design §7. Its test now targets a row header
    because the new option and the table legitimately share a location name.
12. **Task 18 integration corrections:** the real Forecasts page uses the ML
    proxy, not the hybrid-run hook. A new integration test failed with
    `assert 0 == 2` location rows after normal generation. The proxy now splits
    its persisted run, using its historical cutoff for the share window, and
    surfaces a reason if splitting is unavailable. The SKU result remains
    available if this post-step fails.
13. **Task 18 design checks:** added the required last sale/stock timestamps to
    location lists, exposed fresh-run unassigned-share metadata to Network,
    and propagated degraded badges to Inventory. New tests first failed on
    missing fields/warnings. Category-prior tests then showed stockout flags
    were discarded and category sales outside the run were ignored; both
    sample-code defects were corrected. Missing sales now give
    `unassigned_share = null` plus the no-history exclusion, rather than a
    fabricated 0%.
14. **Task 18 environment:** 8000 belonged to an unrelated marketing server;
    it was untouched. The existing local `sanket` DB lacked Alembic bookkeeping,
    so verification used a disposable PostgreSQL on 55434. Temporary API/ML
    servers used 8012/8013 and `sanket_app`; only migrations, synthetic
    entitlement provisioning, and fixture cleanup used the migration role.
    A Windows Alembic entry-point trampoline failed to resolve; the equivalent
    `uv run python -m alembic upgrade head` succeeded. No live keys or connector
    writes were introduced.
15. **Task 18 test execution:** the first full backend run overlapped the ML and
    frontend suites and finished `1 failed, 643 passed`. The failure was
    Hypothesis's input-generation health check, not an allocation invariant:
    `only generated 3 valid inputs after 2.81 seconds`; its slowest strategy
    draw was 2.804 seconds. The same allocation file immediately passed all nine
    tests alone. No assertion, strategy, timeout, or health check was changed;
    the complete backend suite was rerun with the other suites finished. Both
    raw full-run logs are retained.

## Scale and holdout

The first 25k × 6 measurement split 1,200,000 rows in **123.5337 s**, exceeding
the 120-second threshold. Decision build: **29.1170 s** for 84,858 decisions;
persist: **19.5078 s**. This finding was retained; no performance tuning was
done. A final rerun after correctness changes is recorded in the benchmark
README and raw logs.

Final rerun: **119.0793 s** split (10,077.3 rows/s), **26.4297 s** decision build
(3,210.7 rows/s), **18.2784 s** persist (4,642.5 rows/s). The same 1,200,000
forecasts / 84,858 decisions were produced, and the tenant was deleted.

Synthetic retrospective holdout MASE: **Alwal 0.4199**, **Boduppal 0.6036**,
**unit-weighted 0.5317**. See `holdout.md` for exact commands and limitations.

## Full verification

| Check | Result |
|---|---|
| Backend full suite | **644 passed**, 2 warnings in 161.64s on unchanged isolated rerun |
| ML full suite | 58 passed, 2 warnings in 30.63s |
| Frontend full suite | 209 passed, 45 files in 117.54s |
| Frontend typecheck | Exit 0, no errors |
| Frontend lint | Exit 0, no errors |
| Staged diff whitespace check excluding raw `.log` evidence | Passed; raw logs retain emitted trailing whitespace |

Warnings are existing dependency deprecations (argon2, Starlette/httpx,
`datetime.utcnow`) and React Router future flags. No pre-existing main failure
was claimed or hidden. No tests were skipped or marked xfail to obtain green.

The first full backend run's actual failing output was:

```text
FAILED tests/test_allocation.py::test_never_exceeds_supply_or_need
hypothesis.errors.FailedHealthCheck: Input generation is slow: Hypothesis only
generated 3 valid inputs after 2.81 seconds (1 inputs which exceeded the maximum
allowed entropy).
raw | 4 | 100% | -- 0.001, 0.001, 0.004, 2.804
1 failed, 643 passed, 2 warnings in 283.93s (0:04:43)
```

`backend-full.log` retains the whole failure; `backend-full-isolated.log`
retains the complete successful rerun. `ml-full.log`, `frontend-full.log`,
`frontend-typecheck.log` and `frontend-lint.log` retain the other final checks.
The final review checked tenant-scoped reads/writes and FORCE RLS, nullable
money, route identity, input freshness, share invariants and advisory-only
execution. The staged diff whitespace check excluding raw `.log` evidence and a live-payment-key-pattern scan passed. The unfiltered whitespace check reports runner-emitted trailing whitespace and blank lines in the preserved raw logs.

Temporary API/ML processes and the disposable verification container were
removed after evidence capture; pre-existing services and databases were not
changed. The benchmark's split-stage budget margin remains the material
performance finding.
