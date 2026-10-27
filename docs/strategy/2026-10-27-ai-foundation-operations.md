# AI foundation operations

This is the historical Phase 0 runbook. For the current Phase 1/2 UI and local runtime, see [the demo checkpoint](2026-10-27-ai-demo-checkpoint.md) and [Claude handoff](2026-10-27-claude-ai-handoff.md).

Phase 0 adds backend infrastructure only. It adds no customer-facing AI endpoint or import UI. The existing uploader continues to use its current deterministic/manual mapping flow. The next approved feature plan will connect the foundation to layout detection and mapping confirmation, including Redwine acceptance tests.

## Current model

Verified on 2026-10-27 against DeepSeek's [official model catalog](https://api-docs.deepseek.com/quick_start/pricing): use `LLM_MODEL=deepseek-flash`, currently backed by **DeepSeek-V4.1-Flash-1017**. The base URL is `https://api.deepseek.com`. The adapter uses `/chat/completions`, JSON output, non-streaming responses, and explicitly disabled thinking. See [JSON mode](https://api-docs.deepseek.com/guides/json_mode) and [thinking mode](https://api-docs.deepseek.com/guides/thinking_mode/).

The alias follows the provider's serving release; it does not pin an immutable version. Recheck the catalog before release. On a known model revision change, change `LLM_CACHE_GENERATION` to invalidate cached results and rerun the non-sensitive evaluation. Do not silently change to Pro or a retired alias.

## Configuration

Keep `DEEPSEEK_API_KEY` in the backend environment or its gitignored `.env` only. It is a Pydantic secret and is never put in a prompt, response, audit payload, or log. `backend/.env.example` contains the documented defaults and an empty key. Do not put it in frontend/Vite configuration.

| Variable | Default | Meaning |
| --- | --- | --- |
| `LLM_BASE_URL` | `https://api.deepseek.com` | Operator-controlled compatible API base; no credentials/query parameters. |
| `LLM_MODEL` | `deepseek-flash` | Exact serving alias; no automatic provider/model fallback. |
| `LLM_COMPATIBILITY` | `deepseek` | Use `openai_compatible` to omit DeepSeek-only request parameters for another compatible server. |
| `LLM_DEADLINE_S` | 15 | Total request budget, including policy/state/accounting work. |
| `LLM_MAX_RETRIES` | 1 | At most one transient retry; none for authentication or invalid output. |
| `LLM_CACHE_TTL_S` | 86400 | Validated-result TTL, up to 24 hours. |
| `LLM_CACHE_GENERATION` | `flash-1017-v1` | Operator cache-invalidation namespace. |
| `LLM_REQUESTS_PER_MINUTE` | 10 | Fixed UTC-minute limit per workspace, including cache hits. |
| `LLM_REQUESTS_PER_DAY` | 100 | Fixed UTC-day limit per workspace, including cache hits. |
| `LLM_DAILY_TOKEN_LIMIT` | 1000000 | Finite workspace UTC-day allowance, including conservative pending reservations. |
| `LLM_MAX_INPUT_BYTES` | 32768 | Serialized request limit, including instructions and envelope. |
| `LLM_MAX_OUTPUT_TOKENS` | 4096 | Provider output cap. |
| `LLM_MAX_RESPONSE_BYTES` | 65536 | Maximum decoded response bytes read. |
| `LLM_BREAKER_FAILURES` | 5 | Transient failures before opening the provider/model circuit. |
| `LLM_BREAKER_COOLDOWN_S` | 60 | Cooldown before a single recovery probe. |

Redis is required for AI dispatch. AI fails unavailable if shared limits/cache/leases cannot be established. Existing app cache/rate-limit behavior is unchanged. Keep Redis private with the same access controls as the existing app; its AI namespace stores validated IDs/field selections, counters, leases, opaque attempt IDs, and hashes, not uploaded records. Configure a dedicated Redis DB/instance for tests and never flush an operator instance.

## Workspace policy

Every workspace requires both `IndustryProfile.feature_flags.ai_enabled` and `ai_import_mapping` to be true. Missing flags are false. `Tenant.settings.ai.data_sharing_level` accepts:

- `disabled`: no provider calls. Default sharing level for pharma.
- `headers_only`: sanitized labels and structural/type hints only. Default for other industries, with AI still off until explicitly enabled.
- `redacted_samples`: at most three projected examples. Cell values become type hints or local repetition tokens. Exact quantities, prices, dates, identifiers, customer/contact/payment data, and unknown free text never leave. Phase 0 deliberately omits product-name values too; allowing screened product-name values can be added in the import feature if needed.

For the internal foundation, call `PolicyStore.update(AIContext(workspace_uuid, actor_uuid, IndustryCode.fashion), enabled=True, task_enabled=True, sharing="headers_only")` from trusted server-side code using the normal application `Database` instance. Use the workspace's actual industry. The service verifies current active owner/admin membership, locks the tenant/profile rows, preserves other settings, and writes the change with its audit event in one transaction. There is no public management endpoint yet. Do not enable AI through arbitrary user-supplied flags or a superuser SQL session.

Disable AI with the same method and `enabled=False`; saved mappings are not part of this phase. No configuration change or startup triggers a provider warmup/discovery call.

## Audit, accounting, and errors

The application entry point is `app.state.ai.run(context, typed_input)`. The context must come from verified authentication; it is checked against the current database membership and workspace industry. Never construct it from an unverified tenant ID in a request body. The import feature will wire its existing authenticated route to this entry point.

Only strict, bounded selections over supplied column IDs/allowed fields can be returned. Unexpected prose, values, percentages, fields, tool calls, empty/truncated JSON, or invalid references are rejected. No forecasts or quantities are generated. Confidence is an uncalibrated High/Medium/Low/Unknown label.

`ai.call.started`, `ai.call.finished`, and `ai.call.cache_hit` audit events contain only safe metadata: opaque attempt ID, configured model, task/schema, sharing, latency, cache status, safe reason code, and actual token usage if known. They contain no header labels or sample cells. Each finished provider attempt records separate `llm_input_token` and `llm_output_token` events through the existing usage service. Cache hits do not add provider token charges. Retries have separate attempt IDs. Recording is tenant scoped, atomic, and idempotent.

No monetary estimate is shown without configured, versioned rates. Missing provider usage is unknown, never zero. Conservative request reservations limit exposure; they are not billed token measurements. Unknown/in-flight attempts retain their reservations for the UTC-day bucket. A deadline/cancellation can leave a started audit event without a finished outcome, with its opaque attempt ID available for investigation. Lease/probe TTLs recover abandoned work; the service does not retry a canceled request.

If accounting fails before dispatch, no model request is sent. If it fails after dispatch, AI returns unavailable, retains the reservation, and logs only `ai.accounting.failed` with opaque IDs. A provider may still have charged that interrupted attempt; do not report zero or invent usage. Restore recording, compare pending IDs with available provider usage records, and reconcile through trusted scoped telemetry code if actual counts become known. Do not delete immutable audit or usage rows to remove the condition.

Safe failure reasons distinguish disabled policy, missing configuration, provider authentication, provider outage/busy, invalid output, deadline, open circuit, request/token limits, infrastructure failure, and accounting failure. The first import feature must surface these through an AI-unavailable state with manual mapping still usable.

## Database migration and rollback

Apply migrations using `MIGRATION_DATABASE_URL`; run the app with the non-superuser, non-BYPASSRLS application role. Migration `0030` adds two enum labels and has `0029` as its predecessor in the current checkout. The preexisting `0028`/`0029` migrations are uncommitted work from another feature at the time this phase was started: they must land before a standalone Phase 0 PR can depend on them. Do not bundle them into the AI change without their owner's review.

Downgrading `0030` retains the additive enum labels and append-only usage history. This is intentionally not a full enum reversal. To roll back behavior, disable AI and retain an enum-aware application build if AI usage history exists; an old build whose Python enum lacks the new labels may not read that history. Never destructively rebuild the enum or delete billing/audit history. Disposable-database tests verify upgrade/downgrade/upgrade and existing meter writes.

The existing usage writer also required two tested repairs: explicit bound SQL casts, and transaction-scoped advisory-lock idempotency instead of `ON CONFLICT`, which PostgreSQL rejects on this table's append-only UPDATE rules. Append-only protections and RLS remain in place.

## Opt-in live probe

The probe uses a generated non-sensitive column fixture, never the Redwine workbook or customer uploads. It requires an existing workspace, a current active actor, explicitly enabled AI flags/sharing, Redis, an application-role database URL, and the key. It sends at most one request with no retry, at most 2 KiB serialized input, at most 256 output tokens, and a local daily allowance cap of 4096. It uses the same policy/state/client/accounting path and cannot enable policy itself.

From `backend`, after setting configuration privately:

```powershell
uv run python scripts/eval_llm.py --allow-live --workspace WORKSPACE_UUID --actor ACTOR_UUID --industry fashion
```

Replace the placeholders with the intended evaluation workspace and actor and use its actual industry. Without `--allow-live` and full context, it refuses before reading provider configuration. Output includes safe state/reason, configured model alias, actual latency, and actual tokens if returned. A model alias is not evidence of an immutable backing revision. Non-success exits with code 2.

Run automated checks with mocked providers: `uv run pytest tests/llm -q`. The live probe is never part of CI. A successful foundation probe establishes transport/contract behavior on its fixture; it does not establish Redwine mapping quality or later explanation quality. Those evaluations belong to their feature phases.
