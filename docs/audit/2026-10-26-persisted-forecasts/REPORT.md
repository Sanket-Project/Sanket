# Persisted forecasts — 26 October 2026

Implemented the user-approved design with manual Superpowers workflows:
root-cause investigation, design approval, written plan, RED/GREEN tests,
isolated implementation tasks, independent review and live verification.
Existing uncommitted import and Chronos batching fixes were preserved.

Dashboard and Forecasts now read `/api/v1/forecasts/latest`; inference is a
separate `/api/v1/forecasts/refresh` arq job. The last completed production run
is displayed with its real age, dates, source and horizon. Backtests are
excluded. Forecasts no longer constructs a decision-derived indicative curve.
Failures retain the saved run and expose the error; an empty workspace shows
queued/generating only after dispatch succeeds.

Migration 0028 adds forced-RLS refresh/input-change state, a tenant-wide unique
active-job index and read indexes. Statement-level sales triggers invalidate
forecasts for CSV, POS, connectors and corrections. Migration 0029 captures the
committed input revision so late import commits cannot falsely appear fresh.
Both migrations were applied to `sanket_recovered_20261026` with
`MIGRATION_DATABASE_URL`. Application and ML processes continue using the
non-superuser application role.

The worker calls baseline inference, verifies persistence, and applies
`ensure_location_split` to that exact run. Location repairs serialize, mark
completed empty splits, reuse legacy rows and insert in buffers of at most
1,000 rows. Location reads accept a tenant/industry-validated run ID and filter
the selected SKU in SQL, preserving original dates.

Atomic reservations and stable arq IDs prevent refresh pileups. A separate
PostgreSQL advisory lock remains held by the actual ML compute thread through
persistence, even after caller cancellation. Refresh IDs recover committed
results after interruption. Queue failures, missing dispatch and dead worker
heartbeats have explicit recovery paths. Across industries, the UI waits for
the tenant slot and then dispatches the requested industry.

Freshness defaults to 24 hours (`FORECAST_FRESHNESS_S`). Worker and ML budgets
are independent of browser requests (`FORECAST_JOB_TIMEOUT_S=21600`,
`FORECAST_ML_TIMEOUT_S=21000`). Existing `ML_API_TIMEOUT_S` remains unchanged.
The dashboard aggregates in SQL; Forecasts pages SKU IDs and fetches only that
bounded set. Chronos reduces sample tensors to quantiles per batch instead of
retaining every batch's sample paths.

Live swecha-demo evidence:

- Dashboard reload: chart visible in 1,530 ms; age displayed.
- Forecasts reload during active refresh: saved charts visible in 2,113 ms.
- Saved summary API: 163 ms / 12 weekly rows / 209 SKUs.
- Saved SKU API: 153 ms / 72 rows for six SKUs.
- Four concurrent force-refresh requests returned one refresh ID.
- A read during refresh retained the same saved run and completed in 132 ms.
- Worker completions: 140.49 seconds and 131.49 seconds; polling displayed the
  new saved run after completion without waiting for a page reload.
- Server pagination showed SKUs 7–12 of 209. The selected run's location view
  showed Alwal, Boduppal, Dilsukhnagar, Kukatpally, LB Nagar and Uppal with dates
  2026-10-26 through 2027-01-11.

See `live-api.json`, `worker.log`, `ml.log` and `dashboard.png`.

The 25k-SKU regression uses 200k persisted forecast points, reconciles summary
aggregation including multiple-model averaging, and checks a bounded page
under stale planner statistics with a ten-second ceiling. The original joined
label subquery exceeded that ceiling; selecting page IDs once fixed it.
A full 25k-SKU CPU inference run was not benchmarked. Runtime remains
hardware/model/horizon dependent; the configurable worker budgets do not
guarantee a specific inference completion time.

Final verification (completed 27 October 2026, Asia/Calcutta):

| Check | Actual result |
| --- | --- |
| `cd backend; uv run pytest` | 674 passed, 2 deprecation warnings; 364.25 seconds |
| `cd backend/ml; .venv/Scripts/python.exe -m pytest -q` | 73 passed, 2 deprecation warnings; 17.83 seconds |
| `cd frontend; npm run typecheck` | Passed |
| `cd frontend; npm run lint` | Passed |
| `cd frontend; npm test` | 46 files, 232 tests passed; 165.23 seconds |
| Targeted backend/ML Ruff and `git diff --check` | Passed |

The initial unrestricted frontend run exhausted Node memory during concurrent
verification. Bounded-worker runs passed, and the final ordinary `npm test`
also passed after the other suites finished; no test configuration was changed.

Independent review findings were reproduced with failing tests before fixes:
interrupted/undispatched jobs, a blocked heartbeat during splitting, stale
planner statistics, cross-industry slot handoff, deferred manual refresh intent,
and import commits crossing the forecast snapshot. No implementation changes
were made after the final applicable checks.

Final application-role database inspection confirms revision 0029, two completed
refresh jobs and no pending/running jobs. The newest run has 14,736 location
points; the largest difference between summed location P50 and its SKU P50 is
0.0002 units (rounding). See `final-db.json`. Saved forecast read latency and
background generation were verified in the in-app Browser pane. Existing
unrelated workspace changes remain uncommitted; no commit or PR was created.
