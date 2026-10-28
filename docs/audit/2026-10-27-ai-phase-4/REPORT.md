# Phase 4 implementation and verification

Date: 2026-10-27. Scope follows the approved phases 1–4 design/plan. This report records Phase 4 evidence; the final combined release checks and browser evidence are tracked by the main task.

## Implemented

- `POST /ai/scenarios/interpret`: bounded, screened text; explicit aggregate permission and current membership; exact source spans; server-owned numeric conversions and existing simulator bounds. The model selects candidate IDs only. Duplicate, contradictory, negated and out-of-range assumptions fail safely. Unsupported magnitudes/durations ask for clarification. Interpretation never invokes simulation.
- Scenario UI: editable numeric review, explicit Apply action, then the existing Run simulation action. Applying interpreted assumptions resets unrelated physical preset shocks while preserving selected horizon/review windows. Manual sliders/presets remain available with AI disabled.
- Optional explanation of the actual just-computed engine result. The server projects baseline/scenario figures, source run, missing money and advisory status; the model cannot replace calculations or accept browser-supplied outcomes. The option defaults off.
- `POST /ai/data-qa`: strict finite plans for analytics, trends, scoped SKU reads, inventory and saved forecasts. Up to three distinct reads share one deadline. Existing read handlers run with the current authenticated identity, subscription gate, filters and application-role RLS. No SQL, arbitrary endpoint, refresh, mutation, export or messaging operation exists.
- Q&A numbers and citations are rendered from a server fact ledger. Saved forecast answers expose up to twenty stored weekly bands with their dates/run IDs. Explicit named analytics periods must match the user's question; unsupported prior/date windows fail safely. The final ephemeral narrative input retains the screened question so fact selection has the original intent.
- Questions/plans/answers do not enter the AI output cache. Existing admission, concurrency leases, token accounting and safe telemetry remain active. Real Redis tests verify no raw question or serialized answer plan is stored.
- Chat is memory-only, capped to eight visible exchanges, clears on workspace/user/language changes, and aborts old requests. HTTP disconnects cancel the backend operation. Source URLs are allowlisted and model text is rendered as text.
- Preferred summary language is sent from persisted communication preferences. All newly added routes are registered; management communications routes inherit the business entitlement gate and personal preference routes are available during setup.

## Observed RED → GREEN

Initial contract suite: 16 expected failures for missing interactive contracts/registry; 16 passed after implementation. Initial service suite: five expected failures for the missing coordinator; five passed after implementation. Initial UI suite failed on missing components; review/cancel/identity cases then passed.

Additional observed regressions demanded the targeted changes:

- Explicit named period validation, final question context and saved forecast quantities: three failures, then green.
- Negated scenario assumptions: expected exception was absent, then green.
- Opaque UUID mistaken for a phone number: identifier preservation failed, then green while phone redaction remained intact.
- Backend disconnect cancellation: missing helper failed, then seven service tests passed.
- Preset leakage: applying demand retained outage `8` instead of expected `0`; the corrected review flow passed.
- Preferred language propagation: request language was undefined instead of `te`; corrected request propagation passed.
- Actual-browser pending state: a StrictMode regression reproduced a successful result with Run simulation permanently disabled. The initial effect dispatched before StrictMode cleanup detached its TanStack observer. A cancellable zero-delay initial dispatch leaves one request owned by the final mounted observer; the regression passes and asserts exactly one initial engine call.

## Fresh checks

Backend command (developer key explicitly removed from the process; provider transport mocked):

```text
uv run pytest tests/llm/test_interactive_contracts.py tests/llm/test_interactive_service.py tests/llm/test_interactive_integration.py tests/llm/test_service.py tests/llm/test_registered_service.py tests/test_scenario_simulator.py tests/test_scenario_readiness.py -q
76 passed, 1 warning in 47.55s
```

See `focused-backend.log`. Warning: existing passlib/Argon2 version deprecation.

Frontend command:

```text
npx vitest run src/pages/WhatIfScenario.test.tsx src/components/ai/Interactive.test.tsx
2 test files passed; 11 tests passed (including the final StrictMode regression)
```

React Router future-flag notices remain. `npm run typecheck` exited 0. Phase-owned `git diff --check` exited 0 (Git emitted only CRLF normalization notices).

The integration suite uses disposable PostgreSQL with the non-superuser application role, disposable Redis, real authenticated local API endpoints and a mocked provider. It verifies cross-tenant inventory/SKU isolation, inactive membership, disabled AI without dispatch, source-derived inventory `17`, explicit scenario review and ephemeral cache behavior.

## Running-app fixture

`tmp/ai_phases34_smoke.py` creates separate disposable PostgreSQL/Redis, asserts application-role RLS, seeds synthetic subscription/catalogue/stock/sales/saved-forecast/accepted-decision records, and mocks the provider. SMTP and external data workers are disabled. API port 50409, frontend port 5181; `tmp/ai-phases34-context.json` records only synthetic identifiers.

The first fixture was started during implementation and imported incompatible old/new module versions; its 422 was reproduced and resolved by a clean fixture restart. Synthetic fixture email was corrected to a syntactically accepted `example.com` address; no message is sent to it. The restarted fixture returned HTTP 200/success for source inventory `500` and HTTP 200 with the interpreted demand assumption `20`. Final browser walkthrough evidence belongs to the main task; API success alone is not browser acceptance.

No production workspace was enabled. No live model-quality evaluation or real-recipient delivery is claimed. Unsupported scenario grammar and unsupported analytics windows remain explicit clarification/unavailable states rather than guessed values.
