# Fashion Readiness Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve audit findings F01–F12 and the order-dependent suite failure, add a leakage-free
forecast evaluation, and verify the import → forecast → accuracy → inventory → decisions → export
workflow end to end.

**Architecture:** Sales rows gain a tenant-scoped `record_key` so imports are idempotent and
duplicates are provable; one explicit Monday-UTC weekly calendar runs from loader to accuracy;
honest status objects (eligibility, signal evidence, coverage, ROI tiers, WhatsApp state) replace
hard-coded or defaulted UI claims.

**Tech Stack:** FastAPI, SQLAlchemy 2 (asyncpg), Alembic, PostgreSQL 16 + RLS, pandas, Chronos,
statsforecast; React 18 + TypeScript + TanStack Query + Vitest + Playwright.

**Spec:** `docs/superpowers/specs/2026-10-26-fashion-readiness-remediation-design.md`

## Global Constraints

- App DB role stays `sanket_app` (NOSUPERUSER, NOBYPASSRLS); migrations only via `MIGRATION_DATABASE_URL`.
- Never weaken auth, tenancy or entitlement checks; never skip/xfail/retry a test to go green.
- Weekly calendar: Monday 00:00 UTC, `date_trunc('week', <ts> AT TIME ZONE 'UTC')`; run metadata `calendar = "W-MON-UTC"`.
- No synthetic fallback data; unknown is reported as unknown with a reason.
- Icons only from `frontend/src/components/ui/icons.tsx`.
- Isolated stack only: PG 55433, Redis 56380, API 8011, ML 8002, web 5174. Never touch 55432/56379/8010/8001/5173/8000.
- No messages sent, no orders, no payments, no deploy, no push.
- Commit after each task with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

**Test commands** (from repo root):
- Backend: `cd backend && ./.venv/Scripts/python.exe -m pytest <path> -q`
- ML: `cd backend/ml && ./.venv/Scripts/python.exe -m pytest <path> -q`
- Frontend: `cd frontend && npx vitest run <path>`

---

## Workstream S — suite isolation

### Task 1: Stop the test lifespan from calling live signal sources

**Files:**
- Modify: `backend/tests/conftest.py` (module top, before any `app` import)
- Modify: `backend/tests/test_external_signals.py`

**Interfaces:** Produces env defaults `SIGNAL_PIPELINE_ENABLED=false`, `SHOPIFY_POLL_ENABLED=false`, `WHATSAPP_DIGEST_WORKER_ENABLED=false` for the whole suite.

- [ ] **Step 1: Write the failing tests** (`test_external_signals.py`)

```python
@pytest.fixture(autouse=True)
def _closed_trends_cooldown():
    """The cooldown is a process-global breaker; each test states its precondition."""
    from app.services.external_signals.trends_ratelimit import cooldown
    cooldown.record_success()
    yield
    cooldown.record_success()


@pytest.mark.asyncio
async def test_open_cooldown_suppresses_regional_fetch_without_calling_google():
    from app.services.external_signals.trends_ratelimit import cooldown
    cooldown.record_rate_limited("test")
    with patch("pytrends.request.TrendReq") as trend_req:
        samples = await RegionalDemandConnector().fetch("fashion")
    assert samples == []
    trend_req.return_value.build_payload.assert_not_called()


def test_suite_does_not_start_live_signal_pipeline():
    from app.config import get_settings
    get_settings.cache_clear()
    assert get_settings().signal_pipeline_enabled is False
```

- [ ] **Step 2: Run** `pytest tests/test_health.py tests/test_external_signals.py -q` → `test_suite_does_not_start_live_signal_pipeline` FAILS (`True is False`).
- [ ] **Step 3: Implement** — at top of `conftest.py` after imports:

```python
# The app lifespan starts background loops that call third-party services
# (Google Trends, Reddit, FRED, Shopify). A test suite must never do that: a
# real 429 from Google opened the shared Trends cooldown and made
# test_regional_demand_connector_fetch order-dependent.
os.environ["SIGNAL_PIPELINE_ENABLED"] = "false"
os.environ["SHOPIFY_POLL_ENABLED"] = "false"
os.environ["WHATSAPP_DIGEST_WORKER_ENABLED"] = "false"
```

- [ ] **Step 4: Run** the same command → all pass; grep `-s` output for `signal_pipeline.started` → absent.
- [ ] **Step 5: Commit** `test(signals): isolate suite from live signal pipeline and reset Trends cooldown`

---

## Workstream A — ingestion integrity (F01, F07, F12)

### Task 2: Pure sales identity keys

**Files:**
- Create: `backend/app/services/sales_identity.py`
- Test: `backend/tests/test_sales_identity.py`

**Interfaces — Produces:**
```python
IdentityMode = Literal["transaction", "period"]
def canonical_money(v: Decimal | None) -> str            # "" or 4dp HALF_UP
def canonical_time(dt: datetime) -> str                  # UTC "YYYY-MM-DDTHH:MM:SS.ffffff"
def base_key(*, source: str, mode: IdentityMode, sku_id: UUID, sale_time: datetime,
             channel: str, region: str | None, location: str | None, units: int,
             gross: Decimal | None, net: Decimal | None,
             order_id: str | None, line_id: str | None) -> str
def assign_record_keys(bases: list[str], mode: IdentityMode) -> list[str]   # appends "#n" in transaction mode
```
Key formats exactly as spec §2.2.

- [ ] **Step 1: Failing tests**

```python
from datetime import UTC, datetime
from decimal import Decimal
import uuid
from app.services import sales_identity as si

SKU = uuid.UUID("00000000-0000-0000-0000-000000000001")
T = datetime(2026, 8, 24, tzinfo=UTC)

def _base(**kw):
    args = dict(source="upload", mode="transaction", sku_id=SKU, sale_time=T, channel="Boduppal",
                region=None, location=None, units=5, gross=Decimal("6000"), net=Decimal("5900"),
                order_id=None, line_id=None)
    args.update(kw)
    return si.base_key(**args)

def test_order_key_uses_line_then_sku():
    assert _base(order_id="A-1") == f"upload|o|A-1|{SKU}"
    assert _base(order_id="A-1", line_id="2") == "upload|o|A-1|2"

def test_fingerprint_is_stable_and_content_sensitive():
    assert _base() == _base()
    assert _base() != _base(units=6)
    assert _base().startswith("upload|f|")

def test_money_and_time_canonicalisation_match_postgres_text():
    assert si.canonical_money(Decimal("6000")) == "6000.0000"
    assert si.canonical_money(Decimal("1.23455")) == "1.2346"
    assert si.canonical_money(None) == ""
    assert si.canonical_time(T) == "2026-08-24T00:00:00.000000"

def test_occurrence_ordinals_keep_identical_rows_distinct():
    keys = si.assign_record_keys(["b", "b", "c"], "transaction")
    assert keys == ["b#1", "b#2", "c#1"]

def test_period_mode_key_and_no_ordinal():
    k = _base(mode="period", order_id="IGNORED")
    assert k == f"upload|p|{SKU}||Boduppal|2026-08-24"
    assert si.assign_record_keys([k, k], "period") == [k, k]
```

- [ ] **Step 2: Run** `pytest tests/test_sales_identity.py -q` → FAIL (module missing).
- [ ] **Step 3: Implement** `sales_identity.py` (md5 over `|`-joined canonical fields; `ROUND_HALF_UP`; period key date = `sale_time` UTC date).
- [ ] **Step 4: Run** → PASS. **Step 5: Commit** `feat(import): deterministic tenant-scoped sales record keys`

### Task 3: Migration 0022 — `record_key`, `location`, backfill

**Files:**
- Create: `backend/alembic/versions/0022_sales_record_identity.py`
- Modify: `backend/app/models/sales.py` (add `record_key`, `location`, `in_stock` mapped columns)
- Test: `backend/tests/test_sales_record_identity_migration.py`

**Interfaces — Produces:** columns `historical_sales.record_key TEXT`, `historical_sales.location TEXT`; index `idx_hsales_tenant_record_key`; SQL backfill identical to Task 2 rules for `metadata->>'source'='upload'`.

- [ ] **Step 1: Failing test** — seed two tenants via `db_session` (superuser test container), insert legacy upload rows the old way (same content in two `upload_id`s plus one distinct row, one order-keyed pair), then call the migration's backfill SQL (exposed as module constant `BACKFILL_SQL`) and assert: duplicates share a key, distinct rows differ, keys equal `si.base_key(...)+"#1"` computed in Python, other tenant untouched, row counts unchanged.
- [ ] **Step 2: Run** → FAIL (no column / module).
- [ ] **Step 3: Implement** migration: `ALTER TABLE historical_sales ADD COLUMN IF NOT EXISTS record_key text, ADD COLUMN IF NOT EXISTS location text;` index; `BACKFILL_SQL` using
  `md5(concat_ws('|', sku_id::text, to_char(sale_time AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US'), channel, coalesce(region,''), coalesce(location,''), units_sold::text, coalesce(gross_revenue::text,''), coalesce(net_revenue::text,'')))`
  and `row_number() over (partition by tenant_id, metadata->>'upload_id', base order by id)`; `UPDATE ... SET record_key = base || '#' || rn WHERE record_key IS NULL`. Downgrade drops index + columns. Model gets the columns.
- [ ] **Step 4: Run** test + `alembic upgrade head` on PG 55433 → PASS / `0022 (head)`.
- [ ] **Step 5: Commit** `feat(db): sales record identity columns with non-destructive backfill`

### Task 4: Idempotent sales import (transaction + period modes)

**Files:**
- Modify: `backend/app/services/integrations/file_import.py` (`map_sales_row`, sales branch of `import_rows`, aliases)
- Modify: `backend/app/schemas/integrations.py` (`UploadResult`)
- Modify: `backend/app/routers/integrations_hub.py` (`upload_file` Form fields `identity`, `currency`)
- Test: `backend/tests/test_sales_import_replay.py` (DB, `rls`-scoped)

**Interfaces:**
- Consumes: Task 2 `base_key`, `assign_record_keys`.
- Produces: `import_rows(..., identity: IdentityMode = "transaction", currency: str | None = None)`; stats keys `rows_inserted`, `rows_unchanged`, `rows_updated`, `identity_mode`, `warnings: list[str]`; `map_sales_row` returns `_order_id`, `_line_id`, `location`, `in_stock`, `returns`.

- [ ] **Step 1: Failing tests** (real DB, `Database` as in conftest, tenant seeded with subscription):
  1. `test_replaying_the_audit_file_changes_nothing` — import `docs/audit/2026-10-25-fashion-readiness/synthetic-training-sales.csv` twice; second stats `rows_inserted==0`, `rows_unchanged==first.rows_inserted`; DB count/units/revenue identical.
  2. `test_identical_rows_inside_one_file_are_two_sales` — CSV with two identical no-ID lines → 2 rows; replay → still 2.
  3. `test_distinct_orders_with_same_sku_time_qty_stay_distinct` — order IDs A/B → 2 rows.
  4. `test_corrected_order_line_updates_in_place` — import A-1 qty 5, then qty 7 → 1 row, units 7, `rows_updated==1`, `metadata.revision==2`.
  5. `test_period_mode_correction_replaces_value` — `identity="period"`, same SKU/date 10 then 12 → 1 row 12.
  6. `test_period_mode_rejects_duplicate_keys_in_one_file` — both rows reported as errors, 0 inserted.
  7. `test_concurrent_uploads_of_same_file_insert_once` — `asyncio.gather` of two imports → final count == single import.
  8. `test_failed_upload_leaves_nothing_and_retry_is_clean` — patch `session.flush` to raise after half the rows → exception; count 0; retry → full count.
  9. `test_partial_then_full_file_inserts_only_the_remainder`.
  10. `test_import_is_tenant_scoped` — tenant B importing the same file gets its own rows; tenant A unchanged.
- [ ] **Step 2: Run** → tests 1,2(replay),4,5,6,7,9 FAIL.
- [ ] **Step 3: Implement** in the sales branch:
  - `await session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:k, 0))"), {"k": f"sanket:sales-import:{tenant_id}"})`
  - resolve SKUs, compute `bases`, `keys = assign_record_keys(bases, identity)`; in period mode, collect duplicate keys → row errors, drop them.
  - load existing rows `WHERE tenant_id=:t AND record_key = ANY(:keys)` (chunks of 1000) → `{key: [rows]}`.
  - per row: absent → `session.add(HistoricalSale(..., record_key=key, location=..., in_stock=..., returns=..., metadata_={"source","order_id","line_id","upload_id","revision":1}))`; one existing & same content (`units, gross, net, channel, region, location, sale_time, in_stock, returns`) → unchanged; differs → `UPDATE historical_sales SET ... , metadata = metadata || {"revision": r+1, "corrected_by_upload": upload_id} WHERE id=:id AND sale_time=:old` ; ≥2 existing → unchanged + `warnings` "N rows match keys that already have duplicate copies — see Data Quality".
  - `rows_imported = inserted + updated`; `sales_rows = inserted`.
  - router: `identity: Annotated[Literal["transaction","period"], Form()] = "transaction"`, `currency: Annotated[str | None, Form()] = None` passed through; `UploadResult` new fields with defaults.
- [ ] **Step 4: Run** new tests + `tests/test_file_import.py` → PASS.
- [ ] **Step 5: Commit** `fix(import): idempotent sales import with order, fingerprint and period identity (F01)`

### Task 5: Zero demand, availability, returns, location (F07)

**Files:**
- Modify: `backend/app/services/integrations/file_import.py` (`map_sales_row`, `_ALIASES`)
- Modify: `backend/tests/test_file_import.py` (replace `test_map_sales_row_rejects_bad_quantity` expectation for `"0"`)
- Test: `backend/tests/test_zero_demand_import.py`

- [ ] **Step 1: Failing tests**
```python
def test_zero_quantity_is_observed_zero_demand():
    out = fi.map_sales_row({"sku": "A", "quantity": "0", "timestamp": "2026-06-15"}, _hmap())
    assert out["units_sold"] == 0

@pytest.mark.parametrize("q", ["-1", "abc", ""])
def test_negative_or_missing_quantity_still_rejected(q): ...

def test_in_stock_and_returns_and_location_columns():
    hmap = fi._build_header_map(["sku", "qty", "date", "in_stock", "returns", "location"])
    out = fi.map_sales_row({"sku": "A", "qty": "0", "date": "2026-06-15", "in_stock": "no",
                            "returns": "2", "location": "Alwal"}, hmap)
    assert out["in_stock"] is False and out["returns"] == 2 and out["location"] == "Alwal"

def test_stockout_column_is_inverted(): ...   # stockout=yes → in_stock False
```
  DB test: import a series with leading, interior and trailing zero weeks + one gap week; assert rows exist for zero weeks, Data Quality `missing_weeks` counts only the gap, replay inserts nothing, and `HistoricalSalesLoader`-equivalent SQL (Task 8) sees first/last week = the zero weeks.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** (`qty < 0 → "negative quantity for SKU X — book returns in the returns column"`; `None → "missing/invalid quantity"`; bool parser for `yes/no/true/false/1/0/y/n`; `returns` ≥ 0 else row error). Update the existing test to assert `"0"` is accepted and `"-3"` is rejected.
- [ ] **Step 4: Run** → PASS. **Step 5: Commit** `fix(import): accept observed zero demand; map availability, returns and location (F07)`

### Task 6: Push ingest uses the same identity

**Files:** Modify `backend/app/routers/integrations_hub.py` (`ingest` handler); Test `backend/tests/test_integrations_hub_db.py` (append).

- [ ] **Step 1: Failing test** — push the same two events (with `order_id`) twice via the push endpoint → 2 rows total; event without order_id pushed twice → 1 row.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** — reuse a new helper `upsert_sales_rows(session, tenant_id, rows, identity, source, upload_id) -> stats` extracted from Task 4 into `file_import.py` (Task 4's branch calls it too). Response adds `unchanged`.
- [ ] **Step 4: Run** → PASS. **Step 5: Commit** `fix(ingest): push ingest is replay-safe (F01)`

### Task 7: Duplicate detection and safe repair (F12)

**Files:**
- Modify: `backend/app/services/data_quality_audit.py` (`_duplicate_sales`, `_dedupe_sales`, new `_possible_duplicates`, `confirmed_duplicate_count`)
- Test: `backend/tests/test_dedupe_sales.py` (DB)

**Interfaces — Produces:** `async def confirmed_duplicate_count(session, tenant_id, industry) -> int` (extra rows in removable+conflicting groups); `apply_fix(... "dedupe_sales")` result keys `rows_affected, applied, dry_run, groups_removable, groups_conflicting, units_removed, survivor_rule, sample`.

- [ ] **Step 1: Failing tests**
  1. `test_preview_reports_without_mutation` — two uploads of a 3-row file → preview `rows_affected==3`, `units_removed==sum`, table unchanged.
  2. `test_repair_keeps_one_copy_per_group` — confirm → 3 rows remain, totals == single upload; survivor == lowest `id::text` of each group.
  3. `test_legitimate_identical_rows_in_one_file_survive` — identical rows in one file (keys `#1`, `#2`) untouched.
  4. `test_conflicting_copies_are_reported_not_deleted` — same `record_key`, different units (inserted directly) → `groups_conflicting==1`, nothing deleted.
  5. `test_repair_is_tenant_isolated` — tenant B duplicates untouched by tenant A repair (run as `sanket_app` via `db.session(str(tenant_a))`).
  6. `test_repair_rolls_back_with_its_transaction` — run confirm inside a session that then raises → rows intact.
  7. `test_no_uuid_aggregate_is_used` — preview runs on PG16 without error (regression for `min(uuid)`).
- [ ] **Step 2: Run** → FAIL (500 path / old semantics).
- [ ] **Step 3: Implement** — groups query:
```sql
SELECT record_key, count(*) n,
       count(DISTINCT md5(concat_ws('|', sku_id, sale_time, channel, region, location,
             units_sold, gross_revenue, net_revenue, returns, in_stock, promo_flag, markdown_pct))) variants,
       min(id::text) keep_id, sum(units_sold) units
FROM historical_sales
WHERE tenant_id=:t AND industry=:i AND record_key IS NOT NULL
GROUP BY record_key HAVING count(*) > 1
```
  removable = `variants == 1`; delete `WHERE tenant_id=:t AND record_key = ANY(:keys) AND id::text <> keep` per batch. Finding text: "Remove the extra copies — one identical copy of each is kept." `_possible_duplicates` = identical content, `record_key IS NULL`, severity warning, no autofix.
- [ ] **Step 4: Run** → PASS. **Step 5: Commit** `fix(data-quality): provable duplicate identity and deterministic repair (F12)`

### Task 8 is in Workstream B. Task 9 below completes Workstream A.

### Task 9: Forecast gate on confirmed duplicates

**Files:** Create `backend/app/services/forecast_gate.py`; modify `backend/app/routers/forecasts.py`, `backend/app/routers/hybrid_forecast.py` (`POST /hybrid/runs`, `POST /hybrid`), `backend/app/routers/decisions.py` (`POST /refresh`); Test `backend/tests/test_forecast_gate.py`.

**Interfaces — Produces:** `async def assert_forecastable(session, tenant_id, industry: str) -> None` raising `HTTPException(409, detail="Duplicate sales detected: N extra rows … Data Quality → Remove duplicate sales")`.

- [ ] **Step 1: Failing test** — seed duplicates; `POST /api/v1/forecasts/generate` → 409 with the count (ML mocked with `respx`/monkeypatched `http.post` that must NOT be called); after repair → ML called. Same for `/decisions/refresh` and `/forecast/hybrid/runs`.
- [ ] **Step 2–4:** run → FAIL; implement; run → PASS.
- [ ] **Step 5: Commit** `fix(forecast): refuse to forecast on confirmed duplicate sales (F01)`

---

## Workstream B — calendar, accuracy, eligibility (F02, F08)

### Task 8: ML loader complete weeks, Monday future dates, eligibility

**Files:**
- Modify: `backend/ml/sanket_ml/data/loader.py` (`load`: UTC bounds, `AT TIME ZONE 'UTC'`, default `end`, panel-end reindex, `observation_counts`)
- Modify: `backend/ml/sanket_ml/inference/zero_shot.py` (future dates `W-MON`, `history_end`, `omitted`)
- Modify: `backend/ml/sanket_ml/inference/api.py` (`ForecastRequest.history_end`, response fields, persisted metadata)
- Create: `backend/ml/sanket_ml/data/calendar.py` (`week_start(d) -> date`, `current_week_start(now=None) -> date`, `CALENDAR = "W-MON-UTC"`)
- Test: `backend/ml/tests/test_calendar_alignment.py`, `backend/ml/tests/test_zero_shot_eligibility.py`

**Interfaces — Produces:**
- `TimeSeriesPanel.observation_counts: dict[str, int]` (default empty), `TimeSeriesPanel.last_week: pd.Timestamp | None`.
- `ZeroShotResult.history_end: date | None`, `.first_forecast_week: date | None`, `.omitted: list[dict]`.
- `ForecastResponse` optional `history_end`, `first_forecast_week`, `calendar`, `omitted`.
- `ForecastRequest.history_end: date | None` (must be a Monday; forces zero-shot; ignored with `series_context`).

- [ ] **Step 1: Failing tests** (no DB: monkeypatch `HistoricalSalesLoader.load` / `_chronos_predict`)
```python
def test_future_dates_continue_monday_buckets():
    # panel last week Monday 2026-08-24 → first forecast Monday 2026-08-31
    ...
    assert [d.date().isoformat() for d in res.forecast.ds[:2]] == ["2026-08-31", "2026-09-07"]
    assert all(pd.Timestamp(d).weekday() == 0 for d in res.forecast.ds)
    assert res.history_end == date(2026, 8, 31)

def test_series_ending_early_is_extended_to_panel_end_with_zeros(): ...
def test_reindex_panel_to_end_uses_monday_anchor(): ...           # _reindex_panel(df, "W", end=...)
def test_omitted_lists_unsold_short_and_capped_skus():
    # active SKUs: A(10 obs) B(3 obs) C(0 obs) D(9 obs) with max_series=1
    assert {o["sku_id"]: o["reason"] for o in res.omitted} == {
        "B": "insufficient_history", "C": "no_sales_history", "D": "series_cap"}
def test_no_eligible_series_raises_with_counts(): ...
def test_history_end_must_be_monday(): ...                        # ValueError
def test_default_end_is_current_week_start():
    assert current_week_start(datetime(2026, 10, 28, 15, tzinfo=UTC)) == date(2026, 10, 26)
```
  SQL check (string assertion on the query text): contains `AT TIME ZONE 'UTC'` and `sale_time <  :end` with tz-aware bounds.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**:
  - `load(..., end=None)`: `end = end or current_week_start()`; params `start/end` as `datetime(..., tzinfo=UTC)`; bucket expr `date_trunc(:bucket, sale_time AT TIME ZONE 'UTC')`; `observation_counts = df.groupby("unique_id").size()` before filtering; `_reindex_panel(df, freq, end=df["ds"].max())` extends each series to the panel's last week with `y=0` (gap-filled), and adds column `observed` (1 for real buckets, 0 for filled).
  - zero-shot DB path: active SKUs via `load_skus_metadata`; `omitted` computed from `observation_counts` + cap; future dates `pd.date_range(last_week + pd.Timedelta(weeks=1), periods=horizon, freq="W-MON")`; `history_end = (last_week + 7d).date()`.
  - request-context path: `last_week = current_week_start() - 7d`.
  - api: pass `history_end` to loader; persisted `run_metadata` adds `calendar`, `history_end`, `first_forecast_week`, `omitted_count`, `omitted`, `mode` ("zero_shot" | "backtest").
- [ ] **Step 4: Run** `cd backend/ml && ./.venv/Scripts/python.exe -m pytest -q` → all pass (existing 34 + new).
- [ ] **Step 5: Commit** `fix(ml): Monday-UTC weekly calendar, complete weeks only, explicit omissions (F02, F08)`

### Task 10: Explicit backtest endpoint

**Files:** Modify `backend/app/routers/forecasts.py` (`POST /forecasts/backtest`); Test `backend/tests/test_forecast_backtest.py`.

**Interfaces — Produces:** body `{cutoff: date (Monday, < current week start), horizon: 1..26}` → proxies ML `/forecast` with `force_zero_shot=True, history_end=cutoff`; gated by Task 9; returns ML JSON.

- [ ] **Step 1: Failing tests** — non-Monday cutoff → 422; future cutoff → 422; valid → ML called with `history_end` and `force_zero_shot`; duplicates → 409.
- [ ] **Steps 2–4**, **Step 5: Commit** `feat(forecast): explicit leakage-free backtest endpoint (F02)`

### Task 11: Date-matched production and backtest accuracy

**Files:** Rewrite live path of `backend/app/routers/forecast_accuracy.py` into `backend/app/services/forecast_accuracy.py` (pure selection + SQL loaders); Test `backend/tests/test_forecast_accuracy.py`.

**Interfaces — Produces:** `compute_accuracy(session, tenant_id, industry, now) -> dict` with keys `industry, source="live", calendar, rows, summary, excluded, backtest`.

- [ ] **Step 1: Failing tests** (seed runs/results directly with explicit `completed_at`, `metrics`):
  1. `test_actuals_match_the_intended_monday_week` — run completed 2026-08-30 (history_end 2026-08-31) forecasting 2026-08-31; sales Mon 31 Aug and **Sun 6 Sep 23:00 UTC** → actual includes both; WAPE computed.
  2. `test_forecast_generated_after_week_start_is_excluded` (`generated_after_period_start`).
  3. `test_run_trained_on_the_week_is_excluded` (`history_end > week_start` → `trained_on_period`).
  4. `test_latest_eligible_run_wins` — two eligible runs → later one used.
  5. `test_legacy_sunday_runs_are_excluded` (`legacy_calendar`).
  6. `test_unmatured_week_excluded` (`period_not_complete`).
  7. `test_missing_rows_count_as_zero_only_when_feed_covers_the_week` (`awaiting_actuals` otherwise).
  8. `test_backtest_runs_reported_separately` — mode=backtest run completed today with history_end 2026-08-31 → in `backtest`, not in `rows`.
  9. `test_tenant_isolation` — other tenant's runs/sales never contribute.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement** (selection in Python over at most 50 runs × 5000 rows; actuals via `date_trunc('week', sale_time AT TIME ZONE 'UTC')` with `sale_time >= min_week AND sale_time < max_week + 7d`). Remove the `forecast_accuracy_metrics` short-circuit.
- [ ] **Step 4: Run** → PASS. **Step 5: Commit** `fix(accuracy): date-matched, leakage-free accuracy with explicit exclusions (F02)`

### Task 12: One week convention across backend consumers + export

**Files:** Create `backend/app/core/calendar.py` (`week_bucket(col)`, `week_start(d)`, `current_week_start()`, `CALENDAR`); modify `data_quality_audit._series_health`, `decision_builder.weekly_history`, `roi._forecast_improvement`, `services/hybrid_forecast._persist_accuracy_snapshot` (metrics calendar/history_end), `routers/export.py` (week columns); Test `backend/tests/test_calendar_convention.py`.

- [ ] **Step 1: Failing tests** — with the session `SET TIME ZONE 'Asia/Kolkata'`, a sale at `2026-08-30 20:00 UTC` (Mon 01:30 IST) buckets to 2026-08-24 in `_series_health`/`weekly_history` (UTC rule); compiled SQL of `week_bucket` contains `timezone('UTC'`; export headers include "Week start (Mon, UTC)" and "Week end (Sun)".
- [ ] **Steps 2–4**, **Step 5: Commit** `fix(calendar): explicit Monday-UTC weekly buckets everywhere (F02)`

---

## Workstream D — catalogue (F06)

### Task 13: Fashion size normalisation and validation

**Files:** Create `backend/app/services/fashion_sizes.py`; modify `industry_context.py` (`FASHION` enum, `normalize_sku_attributes`), `routers/skus.py` (create + PATCH), `services/integrations/file_import.py` (size → attributes for products/sales/inventory created SKUs), `routers/industries/fashion.py` (size curve); Test `backend/tests/test_fashion_sizes.py`.

**Interfaces — Produces:** `CANONICAL_SIZES: tuple[str, ...]`; `normalize_size(raw: str) -> str | None`; `IndustryContext.normalize_sku_attributes(attrs: dict) -> dict`.

- [ ] **Step 1: Failing tests**
```python
@pytest.mark.parametrize("raw,canon", [("4XL","4XL"),("5xl","5XL"),(" xxxl ","3XL"),("2XL","XXL"),
    ("XXXXL","4XL"),("Free Size","FREE"),("m","M")])
def test_normalize(raw, canon): assert normalize_size(raw) == canon
def test_unknown_size_rejected(): assert FASHION.validate_sku_attributes(FASHION.normalize_sku_attributes({"size": "7XL"}))
def test_label_preserved(): assert FASHION.normalize_sku_attributes({"size": "xxxl"}) == {"size": "3XL", "size_label": "xxxl"}
```
  API: `POST /skus/{pid}/skus` with size `5XL` → 201 stored `5XL`; PATCH with `"9XL"` → 422; PATCH `"4xl"` → 200 `4XL`. Import products CSV `sku,name,size` with `KURTI-5XL,…,5XL` and `KURTI-BAD,…,ZZ` → one SKU created with size, one row error; two size variants remain two SKUs. Size curve with legacy `XXXL` + new `3XL` SKUs → one `3XL` bucket; ordering XS…6XL.
- [ ] **Steps 2–4**, **Step 5: Commit** `fix(fashion): support and normalise 3XL–6XL/FREE sizes on create, edit, import and curves (F06)`

---

## Workstream E — signals and inventory (F05, F09)

### Task 14: Monthly trend partitions

**Files:** Create `backend/alembic/versions/0023_trend_signal_partitions.py`; Test `backend/tests/test_partitions.py` (append).

- [ ] **Step 1: Failing tests** — after migration: partitions for current month −2..+3 exist; `SELECT sanket_ensure_monthly_partitions('trend_signals', 0, 2, DATE '2026-12-15')` creates `trend_signals_2027_01`/`_02` (month/year boundary) and returns 2, second call returns 0; insert at `2027-01-01 00:00 UTC` succeeds as `sanket_app` (SET ROLE); `sanket_maintain_partitions()` returns a `trend_signals` row; fresh-install path covered by the session migration chain.
- [ ] **Step 2–4:** implement function (SECURITY DEFINER, `SET search_path = pg_catalog, public`, `to_regclass` existence check, name `parent_YYYY_MM`), replace `sanket_maintain_partitions()` adding `trend_signals` (2 back, 3 ahead), `SELECT sanket_maintain_partitions()` in upgrade; downgrade restores 0013 body.
- [ ] **Step 5: Commit** `fix(db): rolling monthly partitions for trend_signals (F05)`

### Task 15: Signal evidence status

**Files:** Modify `services/external_signals/signal_pipeline.py` (`last_run`), `routers/trends.py` (`/score` evidence), `schemas` for `TrendScoreOut` (`volatility: float | None`, `evidence`); Test `backend/tests/test_trend_evidence.py`.

**Interfaces — Produces:** `evidence = {status, sample_count, source_count, newest_sample_at, min_samples: 3, stale_after_hours: 48, last_ingest, message}`; `SignalIngestionPipeline.last_run: dict | None` = `{"finished_at", "industries": {ind: {"samples", "persisted", "error"}}}`.

- [ ] **Step 1: Failing tests** — no rows → `status="unavailable"`, `volatility is None`; 2 rows → `insufficient`; 5 rows newest 3 days old → `stale`; 5 fresh rows → `available` with numeric volatility; pipeline `run_once` with a connector returning samples and `_persist` raising → `last_run.industries.fashion.error` set and surfaced as `last_ingest`.
- [ ] **Steps 2–4**, **Step 5: Commit** `fix(signals): report missing, insufficient, stale and failed signal evidence (F05)`

### Task 16: Inventory coverage endpoint

**Files:** Create `backend/app/services/coverage.py`; modify `routers/inventory.py` (`GET /inventory/coverage`); Test `backend/tests/test_inventory_coverage.py`.

**Interfaces — Produces:** response per spec §6:
```python
{"as_of", "calendar", "policy": {"forecast_max_age_days": 14, "trailing_weeks": 8, "min_weeks": 4,
 "stale_stock_days": 30, "low_multiplier": 1.5},
 "skus": [{"sku_id","sku_code","lead_time_days","lead_time_assumed": bool,
   "demand": {"basis": "forecast"|"trailing_actuals"|None, "weekly_units", "run_id", "reason"},
   "sku_wide": {"available_units","inbound_units","cover_days","status","reason"},
   "locations": [{"location","available_units","on_hand_units","inbound_units","as_of","stock_stale",
      "location_demand": {"weekly_units","weeks_observed","basis"}, "cover_days","status","reason"}]}]}
```
- [ ] **Step 1: Failing tests**
  1. two locations, stock 30 vs 190, location-tagged sales 20/wk vs 5/wk over 8 weeks → different location cover (10.5 d vs 266 d) and statuses; SKU-wide cover from pooled stock.
  2. no location-tagged sales → location `cover_days is None`, reason mentions SKU-wide.
  3. no forecast, 8 weeks of actuals → basis `trailing_actuals`; no forecast and 2 weeks → `unknown`.
  4. stale forecast (completed 20 days ago) → falls back to actuals.
  5. stock `as_of` 40 days old → `unknown` with reason.
  6. no decisions exist → statuses still computed (not "healthy" by default).
  7. after `/decisions/refresh` the endpoint result is unchanged (independent of decisions).
  8. tenant isolation.
- [ ] **Steps 2–4**, **Step 5: Commit** `feat(inventory): demand- and lead-time-based coverage per SKU and location (F09)`

---

## Workstream C — money and claims backend (F03, F10)

### Task 17: Currency-aware sales analytics and import currency

**Files:** Modify `routers/sales_analytics.py` (summary/timeseries/top-products), `services/integrations/file_import.py` (currency resolution + mismatch row error), `routers/export.py` (`skus.csv` currency present — verify); Test `backend/tests/test_sales_currency.py`.

- [ ] **Step 1: Failing tests** — INR-only tenant: summary `currency=="INR"`, totals == raw SQL sum; mixed INR+USD SKUs: `currency is None`, `gross_revenue is None`, `revenue_by_currency == {"INR": x, "USD": y}`; top-products rows carry `currency`; import with `currency="INR"` creates INR SKUs; import row `currency=USD` for an INR SKU → row error; import without any currency source → SKU USD + `warnings` contains "currency".
- [ ] **Steps 2–4**, **Step 5: Commit** `fix(sales): carry source currency through analytics and import (F03)`

### Task 18: ROI tiers without realized claims

**Files:** Modify `services/roi.py`; Test `backend/tests/test_roi_tiers.py`.

- [ ] **Step 1: Failing tests** — lifecycle: open PO rec → `tiers.opportunity` has value, `estimated_at_approval` zero/None; accept → value moves to `estimated_at_approval`, `observed.realized_savings.value is None` with reason; response has no `total_value_realized`; carrying-cost line `additive is False`; two currencies → `values_by_currency`; key `approved_orders_on_alerted_skus` replaces `stockouts_avoided`.
- [ ] **Steps 2–4**, **Step 5: Commit** `fix(roi): separate opportunity, approval estimates and observed outcomes (F10)`

---

## Workstream C' — frontend (F03, F04, F05, F08, F09, F10, F11, F01/F02 UI)

### Task 19: Currency formatting with explicit source and manual dated rate

**Files:** Modify `frontend/src/stores/currency.ts`, `frontend/src/hooks/useFormattedCurrency.ts`, every `formatPrice` caller, `frontend/src/components/layout/TopBar.tsx` (toggle becomes "Display: source / USD / INR" plus a manual-rate entry with date); create `frontend/src/components/ui/CurrencyNote.tsx`; Test `frontend/src/hooks/useFormattedCurrency.test.ts`, `frontend/src/pages/SalesAnalytics.test.tsx`.

**Interfaces — Produces:** store `{ display: "source" | "USD" | "INR"; manualRate: { usdToInr: number; setAt: string } | null; setDisplay; setManualRate; clearManualRate }` (persist `version: 2`, migrate drops `exchangeRate`); `formatPrice(amount, sourceCurrency: string, opts?)`; `convertVal(amount, sourceCurrency) -> { val, code, converted: boolean }`.

- [ ] **Step 1: Failing tests** — INR→INR identity (`13091162` renders `₹1,30,91,162`); display USD without rate → still INR + `converted false`; with manual rate 84 set 2026-10-01 → USD = amount/84 and note "manual rate · set 1 Oct 2026"; legacy persisted `{currency:"INR",exchangeRate:83}` migrates to `manualRate: null`; SalesAnalytics with API `currency:"INR"` shows the API total, mixed response shows per-currency lines and no combined total.
- [ ] **Steps 2–4** (`npm run typecheck` drives every caller to pass a currency), **Step 5: Commit** `fix(currency): never convert without an explicit source and user-entered rate (F03)`

### Task 20: Forecast page tells the truth and shows every SKU

**Files:** Modify `frontend/src/pages/Forecasts.tsx`, `frontend/src/api/forecasts.ts` (types), `frontend/src/pages/industries/FashionDashboard.tsx` (+ shared `IndustryHero` "models" wording and other industry pages' hard-coded insight callouts), `frontend/src/pages/industries/PharmaDashboard.tsx` title, `frontend/src/pages/landing/sections/ForecastEngine.tsx`; Test `frontend/src/pages/Forecasts.test.tsx`, `frontend/src/pages/landing/sections/ForecastEngine.test.tsx`.

- [ ] **Step 1: Failing tests** — 6-SKU response: "6 SKUs forecast" and all 6 charts on page 1 (page size 6); with 8 SKUs page 2 is reachable and shows "Showing 7–8 of 8"; source `chronos_zero_shot` renders "Chronos zero-shot" and never "TFT"/"DeepAR"/"Prophet"/"12%"; `omitted` reasons listed; indicative path labelled "Indicative estimate — not a model forecast"; 422 shows the server reason; 503 shows "Forecast service unavailable"; landing copy no longer claims never-sold SKUs get a curve.
- [ ] **Steps 2–4**, **Step 5: Commit** `fix(forecasts): show actual model, omissions and all SKUs; remove unsupported claims (F04, F08)`

### Task 21: Trend evidence UI and signal disclosure

**Files:** Modify `frontend/src/pages/TrendAnalysis.tsx`, `frontend/src/api/trends.ts`, `frontend/src/pages/HybridForecasts.tsx` (disclose zero-sample adjustment); Test `frontend/src/pages/TrendAnalysis.test.tsx`.

- [ ] **Step 1: Failing tests** — `sample_count 0` → "Insufficient signal evidence", no "%" agreement, no "Demand looks stable"; `insufficient` → "2 samples (need 3)"; `stale` → "Signals are stale"; `available` → agreement shown.
- [ ] **Steps 2–4**, **Step 5: Commit** `fix(trends): never present missing evidence as agreement (F05)`

### Task 22: Inventory page from coverage

**Files:** Modify `frontend/src/pages/Inventory.tsx`, `frontend/src/api/inventory.ts`; Test `frontend/src/pages/Inventory.test.tsx`.

- [ ] **Step 1: Failing tests** — unknown demand renders "Unknown — no demand basis" (not "Healthy"); location row with location cover shows "Store cover 11 d"; row without shows "SKU-wide cover 26 d (all locations)"; KPI counts derive from coverage statuses; no decision needed.
- [ ] **Steps 2–4**, **Step 5: Commit** `fix(inventory): status from demand coverage; pooled vs store cover labelled (F09)`

### Task 23: ROI and dashboard readiness wording

**Files:** Modify `frontend/src/pages/ROIDashboard.tsx`, `frontend/src/api/roi.ts`, `frontend/src/components/dashboard/PlanningBriefDashboard.tsx`; Test `frontend/src/pages/ROIDashboard.test.tsx`, `frontend/src/components/dashboard/WhatsAppStatus.test.tsx`.

- [ ] **Step 1: Failing tests** — ROI shows "Estimated at approval — not observed savings", observed "Not measurable yet" with reason, no "not modelled, not projected"; WhatsApp status: `enabled:false` → "Digest disabled"; enabled + `configured:false` → "Preview only — delivery not connected"; enabled + configured + 0 recipients → "No recipients"; ready → "Delivery configured"; query error → "Status unavailable".
- [ ] **Steps 2–4**, **Step 5: Commit** `fix(ui): honest ROI tiers and WhatsApp readiness (F10, F11)`

### Task 24: Upload counters, period mode, accuracy sections

**Files:** Modify `frontend/src/api/integrations.ts`, `frontend/src/pages/Integrations.tsx`, `frontend/src/pages/onboarding/StepData.tsx`, `frontend/src/pages/ForecastAccuracy.tsx`, `frontend/src/api/forecastAccuracy.ts`, `frontend/src/api/forecasts.ts` (`backtest`); Test `frontend/src/pages/ForecastAccuracy.test.tsx`, `frontend/src/pages/Integrations.test.tsx` (append).

- [x] **Step 1: Failing tests** — upload result "0 new · 459 already imported · 0 corrected"; "Weekly/daily totals (corrections replace)" option sends `identity=period`; accuracy page shows "Production accuracy" and separately "Backtest (cutoff 31 Aug 2026)" with exclusion reasons; backtest form posts a Monday cutoff.
- [x] **Steps 2–4**, **Step 5: Commit** — `db8528b`; verification recorded in `docs/audit/2026-10-26-fashion-remediation/task24/RESULTS.md`.

---

## Workstream F — evaluation, E2E, verification

### Task 25: Rolling-origin evaluation

**Files:** Create `backend/ml/benchmarks/rolling_origin.py`, `backend/ml/tests/test_rolling_origin.py`; output `docs/audit/2026-10-26-fashion-remediation/evaluation/`.

**Interfaces — Produces:** `load_fixture(training_csv, heldout_csv) -> pd.DataFrame` (unique_id, ds Monday, y, explicit zero weeks); `folds(panel, cutoffs, horizon) -> list[Fold]` asserting `train.ds.max() < cutoff <= test.ds.min()`; `evaluate(panel, models, val_cutoffs, test_cutoff, horizon) -> dict`; CLI `python -m benchmarks.rolling_origin --out <dir>`.

- [x] **Step 1: Failing tests** — leakage assertion, Monday dates, hand-computed metrics, validation-only routing, short-history omission, complete horizons and matching routing denominators. Ten tests pass after review corrections.
- [x] **Step 2–4:** all six real models evaluated on CPU; results and immutable model/version/fixture metadata saved in the evaluation directory. Repeated metrics match exactly on this host.
- [x] **Step 5: Commit** — `02f1d61`.
- [x] **Step 6 (conditional):** routing improved validation but failed held-out comparison (13.22% versus Chronos 7.45% WAPE). Production routing unchanged; limitation disclosed in UI and report.

### Task 26: Configurable E2E stack and the full-journey spec

**Files:** Modify `frontend/playwright.config.ts` (`E2E_BASE_URL`, `E2E_SKIP_WEBSERVER`), `frontend/vite.config.ts` (`VITE_PROXY_TARGET`); create `frontend/e2e/fashion-remediation.spec.ts` (runs only when `E2E_REMEDIATION=1`), `backend/scripts/seed_remediation_fixture.py` (refuses any port other than an explicit `--db-port`, labels data synthetic), `docs/audit/2026-10-26-fashion-remediation/start-remediation-stack.ps1`, `RUNBOOK.md`.

- [x] **Step 1:** real-service opt-in spec covers the complete specified journey, independent date/SKU WAPE calculation, and every XLSX Monday/Sunday pair.
- [x] **Step 2:** clean-tenant run passed (1 test, 1.1m): 1,064 training inserts, 96 held-out inserts, 0 new on replay. Screenshots and evidence saved.
- [x] **Step 3: Commit** — `e4ca770`, with clean-tenant runbook note `2cca2ae`. Includes minimal root-cause fixes for stale Vite config selection and hidden modal accessibility ancestry.

### Task 27: Verification, review and report

- [x] All six commands passed; 149 frontend, 517 backend and 56 ML tests. Exact counts, warnings and exit codes recorded.
- [x] Fresh DB `55433`, read-only populated current-audit dump/restore on `55434`, and recreated synthetic legacy `0021` dump/restore/upgrade to `0024` passed. Original historical audit DB/dump unavailable; this limitation is explicit in the report.
- [x] RLS/industry/entitlement/RBAC neighbours included and passed in the full backend run.
- [x] Manual requesting-code-review workflow with independent focused reviewer; addressed benchmark, currency, latest-forecast/ROI, E2E and UI evidence findings. No remaining focused-review blockers.
- [x] `REPORT.md` and `verification-summary.json` written with final evidence and remaining external prerequisites.
