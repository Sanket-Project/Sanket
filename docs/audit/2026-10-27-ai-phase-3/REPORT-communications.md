# Phase 3 communication implementation evidence

Date: 2026-10-27. Shared checkout; preserve unrelated work. This report covers personal preferences, weekly scheduling and SMTP delivery. Management reports/supplier drafts and translation/browser QA are recorded separately.

## Implemented behavior

- `/communications/preferences` reads/writes only the authenticated member's language (`en`, `hi`, `te`, `ta`), explicit weekly opt-in, valid IANA timezone and local delivery hour. Defaults are English, weekly off, Asia/Kolkata, 08:00.
- The settings notification tab exposes the persisted preferences, configured/unavailable delivery and queue status, next planned time, and last weekly delivery status. The obsolete browser-only weekly checkbox was removed. Other pre-existing browser-only notification preferences were preserved.
- Additive revision `0034`, based on current head `0033`, creates preferences and durable delivery identities with FORCE RLS, workspace policies and application-role grants. Revision `0035` adds pre-SMTP leases and attempt limits. Existing business tables/data are untouched.
- Scoped ARQ jobs carry tenant/user/industry/due time, schedule the following Monday and recheck active membership, workspace AI policy and current opt-in before generation and send. The existing ARQ worker initializes the same guarded AI service. Weekly facts come from the real ROI ledger; no engine calculations are delegated to the model. Sources use the operator-configured application origin.
- TLS SMTP has no console-success fallback, header/address validation, bounded content, hidden password repr and operator-owned settings. Missing transport returns `unavailable`. The SMTP DATA acceptance uncertainty is represented as `ambiguous` rather than automatically resent.
- Durable `(tenant,user,delivery_key)` identity and content fingerprint prevent duplicate dispatch or reuse for another reviewed message. A `claimed` row has an expiring owner lease and can recover before SMTP dispatch. Known failures are bounded to two attempts. A committed `sending` row is conservatively treated as ambiguous after interruption. No raw body or recipient is persisted in these delivery rows.
- The final eligibility callback runs under current membership and source-record locks after TLS/authentication, immediately before SMTP DATA. Weekly opt-in/policy and reviewed supplier/report source revisions are checked again at that boundary. An old queued job whose due time no longer matches the member's timezone/hour is rejected. Known weekly delivery rejection schedules one deferred retry with the same weekly identity; ambiguous acceptance never auto-resends.
- Explicit report/supplier email uses the same delivery service and requires current administrator permission and confirmation. Weekly delivery is limited to the active authenticated member's address.

## Fresh verification

All test commands set `DEEPSEEK_API_KEY=''`; no live provider calls or real recipient sends were used.

1. New primitive/service scaffolds initially failed collection for missing modules. Implementations then passed. Worker-registration regression failed because `run_weekly_summary` was absent from registered functions; it passed after registration. Password-repr regression failed with the synthetic password visible and passed after hiding that field.
2. `uv run pytest tests/test_communication_primitives.py tests/test_communications.py tests/test_weekly_workflow.py tests/test_communications_api.py tests/test_email_sink.py -q`: **18 passed**, one existing Argon2 deprecation warning, in 51.12 seconds. This count predates two subsequently added focused cases.
3. Expanded `tests/test_weekly_workflow.py`: **5 passed** in 7.97 seconds, including a synthetic opted-in coordinator response with the current user email, stable weekly identity, actual selected fact value and source link.
4. `uv run pytest tests/test_communications_migration.py -q`: **1 passed** in 66.17 seconds. Real disposable PostgreSQL downgrade to 0033 then upgrade to head preserves the existing workspace and restores FORCE RLS.
5. API/RLS/delivery suite independently: **4 passed** in 33.74 seconds. Uses the real migration chain and non-superuser `sanket_app` role; verifies server persistence, rejected user-id injection, invalid timezone, foreign-row invisibility/insert rejection, concurrent single dispatch, changed-content rejection and non-retry of ambiguous acceptance.
6. `tests/test_email_sink.py`: **1 passed** in 4.80 seconds. A real loopback SMTP server performs STARTTLS with a generated test certificate, accepts a synthetic message, and verifies its fact value/source body. This is transport acceptance, not a claim of delivery to an external mailbox.
7. `npm test -- --run src/components/ai/CommunicationPreferences.test.tsx`: **1 passed** in 5.32 seconds. Loads persisted Telugu, keeps opt-in unsaved until explicit Save, and reports unavailable delivery honestly.
8. Focused Ruff check for changed communication services/router/tests: **All checks passed**.
9. Post-review regressions observed RED for stale schedule, absent eligibility/lease API, and missing deferred weekly rejection retry. Implementation then passed the combined primitives/services/weekly/API/RLS/TLS/migration suite: **24 passed**, one Argon2 warning, in 43.25 seconds. Expanded weekly suite with rejection retry: **7 passed** in 5.81 seconds. The concurrent pre-dispatch claimant now correctly reports `pending`, rather than an ambiguous SMTP acceptance.
10. Full weekly coordinator to real TLS sink journey: **2 sink tests passed** in 47.60 seconds before lease hardening and passed again in the combined post-hardening suite. Uses real PostgreSQL/RLS preferences/policy and ROI ledger, a mocked model selecting server facts, actual STARTTLS SMTP DATA acceptance, decoded subject/body/recipient checks, durable `sent` state and replay without a second dispatch. No external recipients were contacted.
11. Final eligibility-boundary regression: **1 passed**, four deselected, in 18.40 seconds. Confirms callback runs both on initial claim and immediately before DATA, and a revocation on the latter check prevents dispatch.

The initial real API/RLS tests were added after service scaffolding and passed on their first run; no API-specific RED observation is claimed. Full application checks and visual QA are owned by the integrating agent and must be reported from their fresh runs.

## Remaining acceptance limits

- ARQ retains scheduled work across process restarts. A scoped `/communications/weekly/recover` endpoint and saving preferences recreate the authenticated member's schedule. No global tenant-enumerating bootstrap was added. Loss of the Redis dataset requires member-scoped recovery; unattended global recovery is not verified or claimed.
- The combined weekly coordinator-to-TLS journey is verified with a mocked model and real PostgreSQL facts/delivery rows. ARQ scheduling is separately verified with a captured queue call; actual production worker/Redis deployment operation is not claimed by those tests.
- Localized label/rendering and four-script browser/PDF inspection are separate integration work. Selecting a persisted language alone is not evidence that every source explanation is translated correctly.
- Normal-workspace migration application, production SMTP configuration, worker operation in deployment, real DeepSeek output quality and external mailbox acceptance are not established by these disposable tests.

## Operator configuration

Apply migrations through `0035` with the migration connection, configure `REDIS_URL`, and run `uv run arq app.workers.forecast_worker.WorkerSettings` beside the API. `backend/.env.example` documents `SMTP_HOST`, `SMTP_PORT` (587), `SMTP_SENDER`, `SMTP_USERNAME` and `SMTP_PASSWORD` with empty placeholders. STARTTLS is mandatory. `APP_BASE_URL` supplies trusted links in messages and reports. Workspace AI/task/aggregate sharing and per-user weekly opt-in remain off until explicitly enabled. Configuring the transport alone does not authorize a message.
