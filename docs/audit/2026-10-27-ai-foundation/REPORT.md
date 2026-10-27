# Phase 0 AI foundation review

Date: 2026-10-27

Branch: `codex/ai-foundation`

Status: Phase 0 implemented and verified; ready for human review. AI remains disabled by default.

## Delivered

- Configurable OpenAI-compatible HTTPX client, defaulting to `deepseek-flash` at `https://api.deepseek.com`, with disabled thinking, JSON output, strict bounded validation, no tools, and no provider fallback.
- Workspace flags default off. Current membership and workspace industry are verified through application-role RLS sessions. Owners/admins alone change sharing policy, with an actor/tenant/profile lock and atomic audit. In-flight demotion/deactivation cannot authorize from an older role snapshot.
- Headers-only default outside pharma; sharing disabled by default for pharma; opted-in samples become type hints/local tokens rather than raw sales/customer data. No product-name values are sent in Phase 0.
- Shared Redis cache, atomic request limits and token reservations, ownership-safe request deduplication, and provider/model circuit breaker. Missing Redis fails unavailable for AI.
- One total deadline, one maximum transient retry, cancellation propagation, explicit unknown usage, and safe failure codes without fabricated results.
- Separate input/output token meters, attempt-level metadata-only audit, idempotent writes, separate scoped transactions, and conservative reservations when actual usage is missing or recording fails.
- Inert app initialization and managed transport shutdown; no model warmup, discovery, customer-facing endpoint, or UI was added.
- Docker Compose forwards model/key/limit configuration to the API only. Empty key examples are in root and backend `.env.example` files; no actual `.env` was edited.
- Opt-in one-call, non-sensitive live probe with policy/RLS/Redis/accounting enforcement and small independent caps.

Entry points: [service](../../../backend/app/services/llm/service.py), [provider](../../../backend/app/services/llm/client.py), [policy](../../../backend/app/services/llm/policy.py), [shared state](../../../backend/app/services/llm/state.py), [telemetry](../../../backend/app/services/llm/telemetry.py).

Operating instructions: [AI foundation operations](../../strategy/2026-10-27-ai-foundation-operations.md).

The current model was rechecked through the in-app Browser against the [official catalog](https://api-docs.deepseek.com/quick_start/pricing). On 2026-10-27, `deepseek-flash` serves **DeepSeek-V4.1-Flash-1017**. This is a serving alias, not an immutable version pin. The API key remains server-side and secret-typed.

## Verification

| Check | Actual result |
| --- | --- |
| Configuration RED/GREEN | Initial run: 18 failed, 1 passed because settings were absent. After implementation: 19 passed. |
| Strict recording RED/GREEN | Initial strict-mode calls failed with unexpected keyword argument; compatibility tests then passed for default and strict modes. |
| Contracts/provider/policy/state/orchestrator | New tests observed missing modules/behavior before their implementation, then passed. Includes real Redis contention, actual PostgreSQL RLS, policy demotion races, unknown usage, accounting rollback, deadlines, and cancellation. |
| Focused AI suite | 100 passed before final regression/deployment/app-integration cases. All 105 current AI cases passed in the final full backend run. |
| Full backend, first run | 797 passed, 2 failed. My initial fixture left a migration URL in process environment, contaminating the two existing industry-migration tests. Fixed by setting both URLs only in the schema subprocess; regression plus industry suite: 10 passed. |
| Full backend, intermediate corrected run | 802 passed, 4 warnings. Subsequent app integration and demotion regression added, then the full suite rerun. |
| Full backend, final `uv run pytest` | **804 passed, 4 warnings in 364.25s**, exit 0. Includes all 105 AI tests. [Full output](backend-verification.log). |
| Frontend `npm run typecheck` | Passed, exit 0. |
| Frontend `npm run lint` | Passed, exit 0. |
| Frontend `npm test` | 51 test files passed; 267 tests passed. React Router future-flag warnings were emitted. |
| Ruff: new AI modules/tests/probe/migration | All checks passed. |
| Broader touched-file Ruff inspection | An existing import-order diagnostic remains in the unchanged router import block of `app/main.py`; reproduced from `HEAD` at line 380. No unrelated router reorder was made. |
| Scoped `git diff --check` | Passed. |
| Migration rollback | Disposable PostgreSQL upgrade/downgrade/upgrade retained additive labels and usage history; old-meter writes still worked. |
| Actual CLI without opt-in | Refused before dispatch: `explicit_live_opt_in_and_context_required`, intentional script exit 2. |
| Live provider probe | Not run. No live DeepSeek credentials were requested or printed, and no live model-quality claim is made. |

Real database tests used `sanket_app` (non-superuser, non-BYPASSRLS), not a superuser connection for application behavior. Migration setup alone used disposable privileged migration credentials. All model calls in automated tests were HTTPX mocks; their transport guard rejects unmocked HTTP.

The four final backend warnings were three dependency/datetime deprecations and one SQLAlchemy non-checked-in connection warning reported during an existing RBAC test. They were not converted into passes or suppressed. The final run had no failures or skipped tests.

## Running application evidence

A separate disposable PostgreSQL instance was migrated, provisioned with a clearly named synthetic smoke workspace, and served through the current backend with no DeepSeek key, AI disabled, and external workers disabled. The current frontend ran on a separate port and proxied only to that fixture backend. No customer workspace or existing application database was used.

Through the in-app Browser:

1. Signed into the fixture workspace.
2. Opened Integrations, then CSV Upload.
3. Selected a one-row non-sensitive fixture and verified the existing header mapping/preview.
4. Clicked **Confirm & Import Data**.
5. Observed **1 new · 0 already imported · 0 corrected**.

[Import screenshot](ai-off-manual-import.png). The fixture initially used a `.test` email rejected by the existing email validator; the fixture was corrected to an `example.com` address. No authentication behavior was weakened. The fixture app and Vite server were shut down after verification.

An additional real app-lifespan integration test used the application-role database, disposable Redis, and mocked provider. It verified a successful call, bounded retry on provider failure, unavailable state when Redis is removed, zero dispatch at startup, and resource closure. This is a mocked foundation check, not a real provider evaluation.

## Review findings resolved

- Existing usage inserts had SQLAlchemy-unbound `:meter::meter_kind`/`:meta::jsonb` casts. Actual PostgreSQL tests reproduced the syntax error; explicit `CAST(...)` bindings repaired it.
- The append-only usage table's UPDATE rules reject `ON CONFLICT`. Replaced it with tenant/key transaction advisory-lock idempotency and an existence check. Cross-transaction duplicates are tested; append-only protections and RLS remain.
- A recording failure during a half-open circuit probe retained probe ownership until TTL. A failing regression demanded neutral probe release while keeping the token reservation; it is now green.
- Policy authorization could use a membership role read before an in-flight demotion committed. The actor row is now locked with the policy mutation, and the real PostgreSQL regression rejects the demoted actor.
- The initial test fixture's session-wide migration URL contaminated separate migration databases. Replaced it with a subprocess-local URL and verified existing migration tests.
- Compose originally did not forward the new model/key variables. A rendering test failed for the absent values, then passed with API-only forwarding.

No changes were made to forecast generation, customer-facing import behavior, or existing unrelated frontend/forecast work. Existing local forecast config additions were preserved; they must not be included accidentally in a Phase 0 commit.

## Release boundary and review handoff

Migration `0030_llm_token_meters.py` follows the current checkout's `0029`. The preexisting `0028`/`0029` migrations are still uncommitted work from another feature. A standalone AI PR must wait for those dependencies to land or be based on their reviewed branch. I did not bundle/commit unrelated work or create a PR with missing migration dependencies. The Phase 0 changes remain reviewable in this working tree.

Downgrade retains the new enum labels and billing history deliberately. Roll back behavior by disabling AI and retain an enum-aware application build when AI usage history exists. This is not a full enum reversal.

Per the approved workflow, stop here for Phase 0 review. Import layout discovery, DeepSeek mapping suggestions, per-column confidence UI, confirmation, workspace mapping profiles, and exact-file Redwine acceptance are the next feature slice and have not been implemented or represented as tested here.
