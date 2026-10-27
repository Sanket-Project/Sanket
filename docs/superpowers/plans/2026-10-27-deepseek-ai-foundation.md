# Phase 0: DeepSeek Flash foundation implementation plan

Date: 2026-10-27

Status: approved by the user on 2026-10-27; Phase 0 implemented and verified on `codex/ai-foundation`. See `docs/audit/2026-10-27-ai-foundation/REPORT.md` for evidence and the migration-dependency release boundary. Stopped for Phase 0 review.

Approved design: [DeepSeek AI layer and import mapping](../specs/2026-10-27-deepseek-ai-layer-design.md).

## Goal and boundary

Build a tested backend AI foundation using the latest DeepSeek Flash serving alias, with no customer-facing AI behavior yet. It must remain safe and inert when flags, credentials, sharing permission, or required infrastructure are absent. Stop after Phase 0 verification for human review. Import layout discovery, mapping suggestions, confirmation UI, saved mapping profiles, and the exact-file Redwine acceptance run belong to the next approved feature plan.

The user approved both the design and this implementation plan on 2026-10-27. Follow the manual executing-plans and strict RED/GREEN/REFACTOR workflows from `AGENTS.md`; no Superpowers invocation is available to Codex. Execute sequentially in bounded task contexts, review each result against its spec and code quality, and do not begin the next task while its prerequisite is red.

## Verified provider contract

Official sources checked through the in-app Browser on 2026-10-27:

- [Model catalog](https://api-docs.deepseek.com/quick_start/pricing): `deepseek-flash` currently serves **DeepSeek-V4.1-Flash-1017**. The older `deepseek-v4-flash` and `deepseek-v4-flash-vision-exp` names are legacy aliases for retired models. Use `deepseek-flash` as the default.
- [API quick start](https://api-docs.deepseek.com/): OpenAI-compatible base URL `https://api.deepseek.com`; chat-completions path `/chat/completions`.
- [JSON output](https://api-docs.deepseek.com/guides/json_mode): `response_format={"type":"json_object"}`, a system-prompt JSON example, and an explicit output cap. Empty output is possible and must be unavailable, not treated as a valid result.
- [Thinking mode](https://api-docs.deepseek.com/guides/thinking_mode/): thinking is enabled by default. Explicitly disable it for the mapping task with `thinking={"type":"disabled"}`. Non-thinking Flash is still the same current Flash model.

Keep provider identity, base URL, model, and capability options configurable. Do not silently route to Pro, an old model, or a different provider. The serving alias can change its backing revision; record the current verification date/release in operator documentation and rotate a cache-generation setting when a known revision changes. Do not invent a version when the response reports only an alias. Reverify the official catalog immediately before implementation/release.

## Existing seams and proposed files

Use existing HTTPX, Pydantic, Redis, and SQLAlchemy dependencies. Do not add a model SDK, prompt framework, vector database, forecasting changes, or new customer-facing endpoint.

| Area | Existing files to change or use | New files |
| --- | --- | --- |
| Configuration | `backend/app/config.py`, `backend/.env.example`, root `.env.example` if it documents backend variables | None |
| Typed contracts | Existing industry/tenant enums | `backend/app/services/llm/contracts.py`, `errors.py`, `__init__.py` |
| Workspace settings and minimization | `Tenant.settings`, `IndustryProfile.feature_flags`, `User`, existing RLS session wrapper | `backend/app/services/llm/policy.py` |
| Provider transport | Existing HTTPX dependency | `backend/app/services/llm/client.py` |
| Shared state | Existing application Redis client | `backend/app/services/llm/state.py` |
| Metering and audit | `backend/app/models/billing.py`, `backend/app/services/usage.py`, `backend/app/services/audit.py` | `backend/app/services/llm/telemetry.py`, one additive token-meter migration |
| Orchestration | `backend/app/main.py` lifespan, shutdown, app state | `backend/app/services/llm/service.py` |
| Verification | `backend/tests/conftest.py`, existing RLS/billing/lifespan fixtures where needed | `backend/tests/llm/conftest.py`, focused `test_config.py`, `test_contracts.py`, `test_policy.py`, `test_client.py`, `test_state.py`, `test_telemetry.py`, `test_service.py`, `test_lifecycle.py`, `test_rls.py` |
| Opt-in evaluation | Existing scripts convention | `backend/scripts/eval_llm.py`, non-sensitive JSON fixtures, `docs/strategy/2026-10-27-ai-foundation-operations.md` |

Keep `state.py` cohesive around the AI Redis namespace; split it only if the resulting implementation needs separate focused objects. Keep new tests scoped under `tests/llm/` so the focused suite is one command.

The observed migration head is `0029`. Reserve `0030_llm_token_meters.py` only if it is still free when implementation begins; otherwise use the next revision and actual current head. Never overwrite or renumber an unrelated migration.

## Test and execution rules

Each numbered task below is a 2–5 minute unit. For a production change: first add the specified behavioral test, run its node and observe the intended failure, implement only that behavior, rerun green, then review/refactor. If a task cannot fit that unit, split it into another RED/GREEN pair before coding. The final full suites and running-app checks are verification jobs and may run longer than a task unit.

Use HTTPX `MockTransport`, fake clocks, deterministic jitter, and a Redis test double for ordinary unit tests. Capture exact outbound request JSON and forbid real provider HTTP in all automated tests. For atomic Redis scripts/concurrency, also use a disposable real Redis fixture; a dictionary fake does not establish cross-worker atomicity. For RLS/migrations/usage, use the actual PostgreSQL migration chain and `sanket_app` role.

Set both `DATABASE_URL` and `MIGRATION_DATABASE_URL` to the disposable test database for migration tests. Existing `alembic/env.py` gives the migration variable precedence, so inheriting an operator's value could target the wrong database. Never print either connection string. Never use the application role to bypass RLS.

## Tasks

### A. Establish the test boundary and configuration

1. **Checkpoint the working context.** Record branch/status and focused diffs for the files this plan will touch. Reconfirm the model catalog and migration head. Inspect this chat's attached worktrees before choosing an existing suitable checkout; create an isolated checkout only if needed and preserve required current local changes. When starting implementation, use `codex/ai-foundation` or a non-conflicting `codex/` branch. Do not copy unrelated changes into a commit. Verification: documented starting state and no lost modifications.

2. **Block accidental live model calls in tests.** Add `tests/llm/conftest.py` with explicit dummy credentials, injected mock transport, and a fixture that rejects an unmocked provider dispatch. Test that the guard itself catches an attempted dispatch without sending traffic. Keep existing app-test environment isolation intact. Verification: `uv run pytest tests/llm/test_client.py -k network_guard -q` rejects an unmocked request locally.

3. **Add safe default settings.** In `test_config.py`, require `LLM_BASE_URL=https://api.deepseek.com`, `LLM_MODEL=deepseek-flash`, and an optional `SecretStr` key. Starting without a key is valid. Verify the key cannot appear in repr/JSON-safe diagnostics. Add only the corresponding config fields. Verification: `uv run pytest tests/llm/test_config.py -k defaults -q`.

4. **Validate budgets and capability configuration.** Add bounded settings for deadline (15s), one maximum retry, cache TTL (24h), request limits (10/minute, 100/day), daily token allowance (initially 1,000,000), input bytes (32 KiB), output tokens (4,096), provider-response bytes (64 KiB), breaker threshold (5), and cooldown (60s). Add an operator-set cache generation and a DeepSeek versus generic-compatible request profile. Reject invalid/negative/unbounded values and credential-bearing base URLs; allow explicit server-configured self-hosted destinations. Verification: config parameterized invalid-value tests are green.

5. **Document configuration without secrets.** Add blank/example values to the appropriate `.env.example` files, including the current Flash alias, and explain that workspace flags still default off. Use only known dummy test keys in tests. Verification: inspect the examples/diff and run config tests; actual `.env` files remain untouched.

### B. Contracts, policy, and minimization

6. **Define bounded result/error contracts.** Test success versus disabled/policy-blocked/unavailable/rate-limited results, fixed safe reason codes, strict schemas, forbidden extras, and bounded collections/strings. Add the corresponding contracts. Verification: `uv run pytest tests/llm/test_contracts.py -k result -q`.

7. **Bind output to supplied IDs.** Test a typed task specification whose result can refer only to its supplied input IDs and allowed enums, with no arbitrary fields. Confidence uses High/Medium/Low/Unknown semantics rather than invented percentages. Reject invalid JSON, duplicates, unknown references, numeric payloads in text-only contracts, and oversized output. Implement the generic validator hook and an internal test task; do not implement the import feature's prompt or parser. Verification: contract validation tests pass and invalid outputs never become successful results.

8. **Load the current workspace policy.** Test existing and missing `IndustryProfile`/settings: flags default off, non-pharma sharing defaults to headers only, pharma sharing defaults disabled, and malformed settings fail closed for AI. Resolve policy using one authenticated workspace/industry context and tenant-scoped sessions. Missing/mismatched context must fail before data is loaded. Verification: `uv run pytest tests/llm/test_policy.py -k defaults -q`.

9. **Protect policy changes.** Test a service operation that verifies the actor's active membership and owner/admin role in the same workspace, rejects viewers/analysts/foreign/inactive actors, and preserves unrelated JSON settings/flags. Use fresh JSON copies and row locking to avoid lost concurrent updates. Persist the setting change and its audit record atomically; return failure if audit fails. No public route or settings UI yet. Verification: policy mutation tests plus rollback test.

10. **Minimize header-only inputs.** Test sanitization/bounding of caller-provided column labels and structural hints, including Unicode/Hindi headers and labels containing contact information. Header-only mode must have no cell-value field in its outbound contract. Implement the pure projection. Verification: `uv run pytest tests/llm/test_policy.py -k headers -q` inspects the complete outbound payload.

11. **Minimize opted-in examples.** Test a maximum of three projected examples with typed/format hints, consistent local identifier tokens, unknown free-text omission, contact/payment/order/customer removal, and product-name inclusion only on a specifically approved, screened field. Exact sales quantities/prices/dates and complete transactions must never leave. Input strings that resemble instructions remain data. Implement the allowlist projection without a dependency. Verification: redacted-sample and prompt-injection fixtures pass.

12. **Prove tenant isolation for policy.** Add PostgreSQL tests under `sanket_app` for two workspaces: reads cannot return the other's policy, actor IDs cannot cross scopes, and settings updates cannot affect a foreign tenant. Use existing RLS fixtures without setting `app.bypass_rls`. Verification: `uv run pytest tests/llm/test_rls.py -k policy -q` against the real database.

### C. Provider transport

13. **Serialize the current Flash request.** Test the exact HTTPX request: configured base URL/model, `/chat/completions`, Bearer key only in the header, non-streaming JSON output, and explicitly disabled thinking for the bounded task. System instructions own the JSON contract; uploaded content is a separate JSON data payload with no tools. Implement request serialization with a mock transport. Verification: `uv run pytest tests/llm/test_client.py -k request -q` asserts `deepseek-flash` and no key in payload/URL.

14. **Keep the protocol configurable.** Test a different configured base URL/model and generic-compatible profile that omits DeepSeek-only options. Disable redirect following and prevent accidental proxy-environment credential transmission; normalize a configured API path without duplicating it. No automatic fallback provider or model. Verification: provider-override and redirect tests pass.

15. **Parse bounded successful responses.** Test the completion envelope, safe provider request ID, model identity if returned, finish reason, content, and actual input/output usage. Bound streamed response bytes before materializing/parsing the full body. Reject tools, multiple unexpected choices, empty/truncated content, bad JSON/schema, and malformed or oversized envelopes. Never retain `reasoning_content`. Verification: client response tests pass.

16. **Classify failures without leaking payloads.** Test connection/timeout/429/5xx as transient and authentication/other 4xx/config/validation as non-retryable. Return safe codes only; do not log exception strings that include response bodies or headers. Capture logs with sentinel secrets/PII in fake error bodies. Verification: failure and log-redaction tests pass.

17. **Respect one deadline and bounded retry.** Test fake-clock 15s end-to-end deadlines, one transient retry, bounded Retry-After/jitter, cancellation, no retry on validation/authentication, and no retry when the remaining budget is insufficient. Expose individual provider-attempt outcomes for accounting. Verification: deterministic deadline tests prove at most two dispatches and no additional dispatch after cancellation.

### D. Shared cache, limits, and circuit breaker

18. **Isolate cached results.** Test cache identity across workspace/task/policy/model/base URL/prompt/schema/cache-generation and exact minimized payload. Cache only validated structured output for 24h; never cache raw files/prompts/unredacted rows. Reject malformed cached values. Verification: `uv run pytest tests/llm/test_state.py -k cache -q`.

19. **Deduplicate concurrent work.** Test two orchestrators claiming the same tenant-scoped request. Use an ownership-token lease longer than the dispatch deadline; only its owner releases it, and waiters remain inside their deadline. A crash/expired lease must recover without stealing another owner's lock. Verification: fake-clock lease tests plus a disposable-Redis concurrency test show one provider dispatch for overlapping requests.

20. **Enforce workspace request limits atomically.** Test rolling/fixed window semantics as selected and documented, minute/day boundaries, tenant isolation, and parallel callers at the limit. Incoming orchestrator requests, including cache hits, consume request allowance; a duplicate provider retry is not a new user request. Implement a single atomic Redis admission operation; no mutation of the existing generic API rate limiter. Verification: real Redis contention cannot exceed 10/minute or 100/day with defaults.

21. **Reserve and settle token budgets.** Test a finite daily allowance when billing quotas are absent, concurrent reservations, configured input/output upper bounds, actual-usage settlement, failures before dispatch, and unknown usage. The conservative admission reservation is a limit, not a reported token count; reserve against the bounded input-byte ceiling plus configured output-token ceiling. Retain unknown/in-flight dispatch reservations until reconciliation/window expiry. Never record missing provider usage as zero. Verification: budget tests cannot overspend under concurrency and report only actual observed usage.

22. **Share circuit-breaker state.** Test five qualifying transient failures opening a provider/model breaker, 60s cooldown, one half-open probe across workers, success reset, and failed-probe reopening. Invalid schema/authentication do not count as provider outages. Ensure every exit releases probe ownership correctly. Verification: fake-clock and real Redis contention tests pass.

23. **Fail closed for AI infrastructure failures.** Test missing Redis, unavailable Redis, script error, cache-read error, and lost lease: return AI unavailable and make no new provider call. A post-dispatch Redis failure still permits bounded accounting/cleanup and never releases a foreign lease. Do not alter existing manual import or other app fallbacks. Verification: infrastructure-failure tests assert dispatch counts and bounded completion time.

### E. Usage and audit

24. **Make telemetry failures observable to the caller.** Add failing tests for opt-in strict behavior in `usage.record` and `audit.record` while preserving the default behavior for all existing callers. Add a keyword-only strict mode that re-raises recording failures for the AI wrapper; do not rely on a swallowed exception to signal success. Verification: new strict/default compatibility tests and existing billing/audit tests pass.

25. **Add AI token meters.** Test that `MeterKind` and the actual migrated PostgreSQL enum accept separate `llm_input_token` and `llm_output_token` usage events. Add the enum members and additive migration from the observed head. Do not add speculative pricing or bill a zero for unknown usage. Verification: migration and actual usage insert/read tests pass.

26. **Verify migration rollback behavior.** On disposable databases, test upgrade from the previous head, existing-meter writes, AI-meter writes, and the documented downgrade behavior. PostgreSQL enum labels cannot simply be dropped: retain additive labels/history on downgrade and document that this is not a full enum reversal. Operational rollback disables AI and retains an enum-aware application version when AI history exists. Never delete usage history or rebuild the enum destructively to claim reversibility. Verification: downgrade/upgrade preserves all usage rows and leaves existing meters functional.

27. **Record every provider attempt safely.** Test audit allowlisted metadata, actual token usage for each returned attempt, unknown usage, retries, cache hits with no token charges, and idempotent event IDs. The telemetry wrapper uses separate `db.session(str(tenant_id))` transactions and strict recording mode; no prompt/cell/header/product/filename/response-body fields. Verification: `uv run pytest tests/llm/test_telemetry.py -q` and billing rollup coverage.

28. **Make accounting failures fail honestly.** Test an audit-write failure before dispatch blocks the call; a failure after dispatch yields unavailable, retains the conservative budget reservation, and prevents subsequent calls from using a healthy AI state until recording recovers. No partially committed usage/audit pair and no poisoned import transaction. Do not hide that the provider may have billed an unrecorded failed-to-persist attempt; keep an opaque retryable attempt ID and safe operational error. Verification: fault-injection tests plus a database rollback test.

29. **Prove telemetry isolation with RLS.** Under the real non-superuser role, test tenant-scoped writes and reads for AI usage/audit, including a foreign-tenant write rejection. Verify missing/foreign actor context never dispatches. Verification: `uv run pytest tests/llm/test_rls.py -k telemetry -q`.

### F. Orchestration and lifecycle

30. **Compose the gated request path.** Test one typed service entry point: resolve authenticated context/policy; reject disabled/task-disabled/policy-blocked before dispatch; enforce request limit; use a validated cache hit or acquire the request lease; reserve budget/check breaker; persist attempt-start metadata; call the client; validate/account; cache only success; release owned resources. Recheck workspace policy immediately before dispatch and before returning cached or generated output. Verification: `uv run pytest tests/llm/test_service.py -k gating -q` including policy-change races.

31. **Cover successful and degraded orchestration.** Test successful mock response and repeat/cache hit, same payload in two workspaces, unknown usage, invalid response, retry exhaustion, timeout, open circuit, disabled task, recording failure, and Redis outage. Ensure each safe failure is distinguishable while no customer data or fabricated text is returned. Verification: service integration tests pass with exact provider/meter/audit call counts.

32. **Initialize and close the foundation.** Add lifecycle tests, then initialize the AI service with the app's DB/Redis references and a dedicated managed HTTPX client in `main.py`. Initialization/startup must not call the provider, even when credentials exist; no AI background loops or model warmups. Close transport cleanly on normal/error shutdown. Verification: `uv run pytest tests/llm/test_lifecycle.py -q`, including missing key and Redis.

33. **Preserve AI-off app behavior.** Add an application-level test proving default startup has no model requests and existing import analyze/manual upload behavior remains available. Do not change import schemas/handlers/UI as part of Phase 0. Preserve existing forecast and external-signal behavior. Verification: lifecycle test plus `uv run pytest tests/test_file_import.py tests/test_sales_import_replay.py tests/test_integrations_hub_db.py -q`.

### G. Opt-in evaluation and operating instructions

34. **Add a guarded real-provider probe.** Test CLI refusal without an explicit `--allow-live` switch, approved sharing policy, configured key, and small call/token caps; unit tests use mock transport. The script calls the same policy/client/orchestration boundary and audits/meters its workspace, using only non-sensitive fixtures. No customer record or Redwine workbook is sent by this probe. A failed/empty/invalid result exits nonzero and prints safe status only. Verification: CLI guard tests exercise every refusal path without network access.

35. **Document operations and future evaluation.** Write the operations document with enable/disable procedure for the internal settings service, default-off guarantees, current Flash alias/backing release/date/sources, environment variables, policy semantics, namespace rotation after provider upgrades, limits, safe telemetry troubleshooting, additive enum rollback limits, and opt-in probe command. Explain that Phase 0 verifies the foundation; real mapping quality and Redwine accuracy await the import feature's eval. Verification: review the document against config and CLI tests; no keys or raw input appear.

36. **Review the implementation diff.** Apply requesting-code-review and verification-before-completion manually. Review auth/tenant boundaries, outbound minimization, mutable JSON merges, secrets, state ownership, retries/cancellation, Redis atomicity, and transaction isolation. Resolve findings with a failing regression test before code changes. Verification: scoped diff contains only authorized Phase 0 changes and every changed production behavior has an observed RED/GREEN test.

## Completion verification jobs

Run after the tasks, and repeat only for new changes/failures that justify it. Capture exact output and exit status; do not convert skips/errors into passes.

| Check | Command or procedure | Required evidence |
| --- | --- | --- |
| Focused foundation | In `backend`: `uv run pytest tests/llm -q` | All new behavior green with mocked provider calls. |
| Full backend | In `backend`: `uv run pytest` | Summary of passed/failed/skipped counts and any actual failure output. |
| Frontend types | In `frontend`: `npm run typecheck` | Exit status, even though frontend source is unchanged. |
| Frontend lint | In `frontend`: `npm run lint` | Exit status and diagnostics. |
| Frontend tests | In `frontend`: `npm test` | Final non-watching test summary. |
| Migration/RLS | Disposable PostgreSQL migration chain; non-superuser scoped tests; disposable Redis concurrency tests | Upgrade/downgrade behavior and real isolation/atomicity verified. |
| AI-off running app | Start against an isolated local database with existing sources/workers controlled by configuration, AI disabled, no key. Use the in-app Browser to exercise upload/analyze and confirm a small non-sensitive manual import | Existing flow succeeds with zero provider requests. Do not import into a customer's current workspace. |
| Foundation running app | In the isolated local environment, invoke the internal service using mock transport; simulate unavailable provider/Redis | Startup and existing UI remain usable; no new AI UI appears. |
| Optional live probe | Explicit opt-in, sanitized fixtures, configured key/policy/allowance | Actual model/status/latency/tokens if run, or explicitly say not run. Do not infer successful real integration from mocks. |

If Windows console-script launchers fail, investigate the exact executable error and use the equivalent module entry point while recording both outcomes. During planning, `uv run alembic heads` failed with `uv trampoline failed to canonicalize script path`; `uv --version` succeeded, and `uv run python -m alembic heads` succeeded with `0029 (head)`. No migration or environment repair was attempted.

Before commit/PR, review the scoped diff and include only this phase's intended work; never bundle preexisting modifications. Attach any PR that is actually created to this chat. Stop after Phase 0 verification/report for review. Do not proceed into import mapping without its approved plan.

## Approval history

The user approved this **Phase 0 only** plan on 2026-10-27, satisfying the original brief's requirement: **"Do NOT write code before the spec and plan are approved by me."** Stop after Phase 0 verification for review.

The planning turn changed documentation only. Implementation evidence and actual checks are recorded separately under `docs/audit/2026-10-27-ai-foundation/`.
