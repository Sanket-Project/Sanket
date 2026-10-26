# Synthetic fashion remediation stack

All data in this journey is synthetic. It is a regression fixture, not evidence of Swecha forecast accuracy or realised savings. This stack uses PostgreSQL `55433`, Redis `56380`, API `8011`, ML `8002`, and Vite `5174`. The original audit ports are not used.

From the repository root in PowerShell:

```powershell
& docs/audit/2026-10-26-fashion-remediation/start-remediation-stack.ps1
```

The script creates named Docker containers if absent, runs the full Alembic chain through `MIGRATION_DATABASE_URL`, and starts hidden local API, ML and frontend processes. An occupied service port causes an explicit error; inspect the owning process rather than starting another stack on another port. Service modes `api`, `ml`, `frontend`, `migrate`, and `seed` can be run separately. Migrations use the local administrative role; API, ML, and fixture provisioning use `sanket_app` with RLS enabled. No bypass-RLS application connection is permitted.

Wait for `http://127.0.0.1:8011/health`, `http://127.0.0.1:8002/health`, and `http://127.0.0.1:5174/login` to respond, then prepare the fixture:

```powershell
& docs/audit/2026-10-26-fashion-remediation/start-remediation-stack.ps1 -Mode seed
```

The seed creates an explicitly labelled synthetic workspace, seven fashion SKUs (one unsold, size 5XL), a test subscription, and stock at two locations. It derives upload CSVs by splitting each original synthetic total between two locations, preserving total demand. It does not insert sales. The UI test imports those files. Account details live in `e2e/fixture.json` and are local test credentials. The seed validates the explicit port, loopback address, application username and actual database role flags before writes; it refuses another database port or a privileged role.

To prove the new-row path again without changing an existing tenant, seed a new unique slug before running Playwright:

```powershell
$env:DATABASE_URL='postgresql+asyncpg://sanket_app:remediation-local@127.0.0.1:55433/sanket'
Push-Location backend
& .venv/Scripts/python.exe -m scripts.seed_remediation_fixture --db-port 55433 --slug synthetic-remediation-fresh
Pop-Location
```

Choose a new slug if that one has already been used. This updates `e2e/fixture.json` for the next journey and preserves existing tenants. On a clean tenant, verify the saved evidence has `training.rows_inserted = 1064`, `heldout.rows_inserted = 96`, and the second training upload has `rows_inserted = 0`, `rows_unchanged = 1064`, and `rows_updated = 0`. The doubled file row count comes from splitting each original total across two stores; portfolio demand is unchanged.

Run the journey:

```powershell
Set-Location frontend
npx playwright install chromium
$env:E2E_REMEDIATION='1'
$env:E2E_BASE_URL='http://127.0.0.1:5174'
$env:E2E_SKIP_WEBSERVER='1'
npx playwright test e2e/fashion-remediation.spec.ts --workers=1
```

Without `E2E_REMEDIATION=1`, the remediation test is skipped. It never targets the ordinary development tenant. It exercises real login, UI uploads/replay, Chronos forecasts, explicit historical backtests, date-matched accuracy, location cover, a synthetic recommendation acceptance, a scenario preset, and XLSX download. Accepting that synthetic recommendation records an application ledger decision; it does not place a supplier order or send a message.

Artifacts are saved in `e2e/`: screenshots, `journey-evidence.json`, and `forecast.xlsx`. The downloaded workbook must contain explicit Monday-start and Sunday-end columns. API/ML/frontend logs and `fresh-migration.log` are beside this runbook. Chronos runs on CPU with 100 samples and the configured `amazon/chronos-t5-small` checkpoint.

To stop, identify the API/ML/Vite PIDs bound to the isolated service ports and stop only those processes; then stop `sanket-remediation-db` and `sanket-remediation-redis`. Preserve the containers and evidence for review. No deployment, messages, payments, or real purchase orders are part of this workflow.
