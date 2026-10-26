# Synthetic Swecha location holdout — 26 October 2026

The files in `data/demo-swecha/` are synthetic software fixtures, not client
observations. This is a retrospective holdout diagnostic, not a production
accuracy claim or evidence for the Method-C gate.

| Location | MASE | Holdout units | Complete weeks |
|---|---:|---:|---:|
| Alwal | 0.4199 | 553 | 8 |
| Boduppal | 0.6036 | 859 | 8 |
| Unit-weighted | **0.5317** | 1,412 | 8 |

These are location-total MASE scores (SKUs summed per location/week), as Task 10
specifies. They are not an average of individual SKU-location MASE scores.
The scale uses the location's pre-forecast seasonal-naive absolute differences
(52 weeks). Lower is better. Chronos zero-shot produced the SKU bands; the
location method is `share_split_v1`. Stochastic inference can vary between runs.

All training files were uploaded before forecasting. The forecast response
confirmed `history_end = first_forecast_week = 2026-08-31`. Shares used the 12
complete weeks before that cutoff. The eight holdout weeks (31 August through
19 October 2026) were uploaded only afterwards.

The forecast was generated on 26 October, after the historical periods began.
The existing production scorer correctly excluded all 96 SKU-week points as
`generated_after_period_start`; production WAPE remains null. The separate
location holdout diagnostic above must not be presented as production accuracy.

## Exact procedure

Port ownership was checked first:

```powershell
netstat -ano | findstr :8000
netstat -ano | findstr :8001
```

8000 belonged to `D:\Sanket Marketing Agent\scripts\serve.py`; 8001 was unused.
No existing service was stopped. An isolated disposable database was used:

```powershell
docker run -d --name sanket-location-verification -e POSTGRES_PASSWORD=location_bench_local -e POSTGRES_DB=sanket -p 55434:5432 pgvector/pgvector:pg16
cd backend
$env:MIGRATION_DATABASE_URL='postgresql+asyncpg://postgres:location_bench_local@127.0.0.1:55434/sanket'
uv run python -m alembic upgrade head
cd ..
& docs/audit/2026-10-26-location-forecasting/start_verification.ps1 -Service api
& docs/audit/2026-10-26-location-forecasting/start_verification.ps1 -Service ml
cd backend
uv run python ../docs/audit/2026-10-26-location-forecasting/run_holdout.py
```

`run_holdout.py` creates a new synthetic workspace through signup, explicitly
grants only that fixture a test subscription, signs in, then uses the normal
`POST /api/v1/integrations/upload` endpoint with `identity=period`, `currency=INR`:

1. `00-products.csv` (products)
2. `01-steady-training.csv`, `02-seasonal-training.csv`, `03-intermittent-training.csv` (sales)
3. `05-inventory.csv` (inventory)
4. `POST /api/v1/forecasts/generate`, `{"horizon":8,"force_zero_shot":true}`
5. `04-heldout-8-weeks.csv` (sales)
6. `GET /api/v1/forecast/accuracy`

The API and ML service both connected as `sanket_app`; only fixture entitlement
and migrations used the migration role. No connector write-back was used.
The API ran on 8012 and ML on 8013. Both temporary services were stopped after
the measurement. Tokens and passwords are excluded from the evidence JSON.

Raw evidence: `holdout-api.json`, `holdout-mase.json`, `holdout-run.log`.

After the final category-prior correctness changes, the frozen run was checked
again with the final splitter, still anchored at 31 August:

```powershell
cd backend
$env:BENCH_DATABASE_URL='postgresql+asyncpg://sanket_app:changeme@127.0.0.1:55434/sanket'
uv run python ../docs/audit/2026-10-26-location-forecasting/recheck_holdout.py
```

All **192** location quantile rows were exactly unchanged, and the MASE result
was identical (`holdout-final-recheck.json`). The already-imported holdout rows
were excluded by the cutoff in this recheck.
