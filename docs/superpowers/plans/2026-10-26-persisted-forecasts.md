# Persisted forecasts and durable refresh

Approved by the user on 2026-10-26. Preserve existing import/batching fixes.

Design: read the latest real production run immediately; request stale/missing
refreshes separately through arq; one refresh per tenant; retain the last good
run on error. Baseline forecasts remain baseline forecasts. Backtests never
become production forecasts. All DB access uses the authenticated tenant/RLS.

Execute each task in RED → GREEN → REFACTOR increments (roughly 2–5 minutes
per test/implementation increment), reviewing its diff before proceeding.

1. Add failing persisted-read API tests: empty state, saved rows, summary,
   pagination, backtest exclusion, tenant isolation, actual horizon/date metadata.
   Verify the tests fail because the route is absent.
2. Implement bounded persisted-run reads, indexed queries and response metadata.
   Verify the read tests pass without an ML call.
3. Add failing refresh tests: concurrent enqueue, freshness, missing queue,
   failed enqueue, stale import, tenant guard and worker lifecycle.
4. Add migration 0028 for RLS-protected refresh state; atomically reserve and
   enqueue refreshes. Add explicit retry/recovery and worker execution.
   Verify refresh tests and existing forecast gates.
5. Add failing ML tests for tenant execution exclusion and persistence errors;
   implement a guard held by actual inference, even after HTTP cancellation.
   Verify ML suite. This isolated ML task is delegated per the repository's
   subagent-driven-development workflow.
6. Add failing location tests for empty completed splits and bounded inserts;
   implement idempotent split completion and worker repair of saved runs.
7. Add failing frontend tests for immediate saved forecasts, background refresh,
   truthful empty/failure/age states, pagination and no indicative substitute.
   Implement shared read/refresh hook and switch dashboard/Forecasts to it.
8. Verify import invalidation, legacy/hybrid execution interaction and long job
   timeouts with targeted regression tests. Review all changed code.
9. Run backend `uv run pytest`, ML pytest, frontend typecheck/lint/tests.
   Apply migration with MIGRATION_DATABASE_URL; restart local stack as needed.
   Use in-app browser to verify swecha-demo saved forecast latency, refresh,
   persisted run identity, and no reload-triggered inference pileup.

Large catalogs: SQL aggregate for dashboard; server-side SKU pagination;
bounded Chronos batches and location inserts; configurable multi-hour worker
budget, independent of browser timeout. Validate 25k response/query shape with
fixtures; do not claim a full 25k CPU inference benchmark without measuring it.

Review-driven regressions added during execution:

- Empty/legacy split markers and concurrent split repairs; heartbeat row remains
  writable during location expansion.
- Read prediction counts from persisted SKU/date points, not configured horizon.
- Bound pagination even with planner statistics from before a bulk import.
- Reconcile orphan pending reservations; expose interrupted worker state.
- Preserve cross-industry refresh requests while the tenant slot is occupied.
- Migration 0029 captures the committed input revision at reservation time;
  equality detects imports that began before queueing but committed after the
  model read. Timestamp ordering alone did not satisfy this invariant.
