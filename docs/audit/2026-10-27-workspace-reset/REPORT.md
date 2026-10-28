# swecha-demo reset — 27 October 2026

The user explicitly approved removing all business/sample data while retaining
credentials, login and settings. Only tenant
`1fea4cb5-b9f3-45fe-8801-d58c13599d00` (`swecha-demo`) in the local recovered
database was cleared. Other workspaces and source-code test fixtures remain.

A validated custom-format PostgreSQL backup is saved at
`backups/swecha-demo-before-clear-2026-10-27.dump` (11,090,230 bytes).
Its SHA-256 and archive validation are recorded in `backup.json`.

The normal dev stack was stopped during cleanup. A rollback rehearsal first
proved all deletion and preservation assertions. The approved one-off data
migration then committed these removals:

| Data | Rows removed |
| --- | ---: |
| Product catalogue | 1 |
| SKUs | 209 |
| Sales | 124,170 |
| Stock positions | 1,254 |
| Locations | 6 |
| Forecast runs | 9 |
| Forecast points | 22,572 |
| Location forecast points | 132,624 |
| Forecast refresh jobs | 3 |

All other targeted business tables were already empty. The sales-deletion
trigger briefly created an input-change marker, which was also removed.

Actual row deletion ran as `sanket_app` with tenant RLS enforced and an explicit
tenant filter on every statement. Missing DELETE grants were temporary within
the migration transaction and revoked before commit; application privileges
were restored. This operation changed no application source or schema.

Full-row digests verified credentials/account data, workspace/industry settings,
subscription, connection/notification settings, invitations and security audit
history were unchanged at commit. Global per-table counts verified other
tenants were unchanged. A fresh connection verified all targeted business
tables were empty. See `dry-run.json` and `apply.json`.

No queued jobs belonged to this tenant. Its Redis response cache was invalidated
and the normal local stack restarted at schema 0029.

Post-restart checks confirm the existing sign-in succeeds (HTTP 200). Products,
SKUs, inventory, coverage, locations and decisions all return empty lists; the
latest saved forecast is null. See `api-verification.json`.

Chrome's browser connector was unavailable. Native Computer Use found its
existing SANKET window already at the sign-in page. No credentials were changed
or entered through native authentication controls. An authenticated empty
Chrome inventory screen was therefore not inspected; empty application data
and functioning sign-in were verified through the API instead.

Frontend typecheck and lint passed. Plain `npm test` passed all 232 tests in 46
files (112.52 seconds).

`cd backend; uv run pytest` reported 673 passed and one failure in 359.36 seconds.
The failure was `tests/test_allocation.py::test_never_exceeds_supply_or_need`:
`hypothesis.errors.FailedHealthCheck: Input generation is slow: Hypothesis only
generated 2 valid inputs after 1.65 seconds.` It occurred while frontend tests
and model startup were also active; it was not an allocation assertion failure.
Rerunning that exact test with the reported Hypothesis seed
`128123753105947099600554786552149811577` passed. No test or application code was
changed to suppress the health check. See `backend-tests.log` and
`backend-rerun.log` for the actual output.

Cleanup, preservation, permission-restoration, other-tenant invariants and
post-restart API checks all passed. The local stack remains running. No source
change, schema change, commit or PR was made for this reset.
