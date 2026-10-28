# Copilot follow-up verification

28 October 2026. Review only; application code and client data unchanged.

| Check | Independently observed result |
|---|---|
| Original 14 regression probes | 14 passed in 30.46 seconds |
| New follow-up acceptance probes | 7 failed, 1 warning in 38.80 seconds; final log in followup-results.txt |
| frontend: npm run typecheck | Exit 0 |
| frontend: npm run lint | Exit 0 |
| frontend: npm test | Exit 0; 66 files, 324 tests passed in 135.32 seconds |
| backend: uv run pytest | 1,118 passed, 3 deprecation warnings in 432.59 seconds |

The original regression fixes are real. The seven new failures distinguish remaining implementation defects from uncompleted read-model/catalog integration. They do not contradict a successful normal suite; the normal suite lacks those scenarios.

## Reproduction

From the backend directory, PowerShell:

```powershell
$env:PYTHONPATH = "$PWD;$PWD\tests"
uv run pytest -p conftest ../docs/audit/2026-10-28-retail-v2-verification/test_review_repros.py -q --tb=short
uv run pytest -p conftest ../docs/audit/2026-10-28-retail-v2-copilot-review/test_followup_repros.py -q --tb=short
```

The first command passed all original 14 probes. The second failed all seven new acceptance cases: failed-return identity cleanup, draft approval, zero-value return, inventory retry, unresolved SKU/location preview, application analytics history, and final partial-return rounding remainder. Each case's actual failure and explanation appears in REPORT.md and followup-results.txt. Six initial follow-up probes were expanded once to add the distinct rounding case; the saved output is the final seven-case run.

Service database cases use the existing app_role_db fixture connected as sanket_app in a disposable testcontainer built with actual Alembic migrations. HTTP cases use synthetic workspaces through the test ASGI client. No production database was accessed. This review did not apply a live migration, enable a source authority, deploy, or modify application code. No browser/E2E check was performed because the V2 frontend workflow is not wired; that absence was confirmed by source searches.

The follow-up tests live outside backend/tests and are not included automatically in normal testpaths. Preserve the original suite and promote required scenarios into normal regression coverage as implementation proceeds. Do not weaken assertions to make the suite green.

reviewed_sources.json records the exact reviewed V2 files, migration files and upload router. Migration 0036's SHA256 still matches the earlier independent review; Copilot added migration 0037 for the tenant-safe FK instead of rewriting 0036.
