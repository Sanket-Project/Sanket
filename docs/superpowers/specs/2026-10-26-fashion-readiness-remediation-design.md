# Fashion readiness remediation — design

**Date:** 2026-10-26 · **Branch:** `fix/fashion-readiness-remediation` (from `3dba120`)
**Input:** `docs/audit/2026-10-25-fashion-readiness/` (F01–F12, red suite, forecast diagnostic)
**Status:** approved in chat 2026-10-26 (replay rule: two modes; calendar: explicit UTC;
currency: manual dated rate; implement on a new branch with per-task commits).

## 0. Ground rules

- Original audit artifacts are read-only evidence. New evidence goes to
  `docs/audit/2026-10-26-fashion-remediation/`.
- All live verification runs on an isolated stack: Postgres `55433`, Redis `56380`,
  API `8011`, ML `8002`, web `5174`. The audit demo stack (`55432/56379/8010/8001/5173`)
  and the unrelated server on `8000` are never touched.
- App connections stay `sanket_app` (NOSUPERUSER, NOBYPASSRLS). Elevated access only via
  `MIGRATION_DATABASE_URL`. No auth, tenancy or entitlement check is relaxed.
- Fail honestly: unknown is shown as unknown; nothing is synthesised to fill a gap.

## 1. Root causes (reproduced 2026-10-26 on a fresh PG16, source == `3dba120`)

| ID | Reproduction | Cause |
|---|---|---|
| F01 | same CSV twice: 459→918 rows, 17,482→34,964 units | `import_rows` assigns a random `upload_id` and always `session.add`s; no row identity. Push ingest (`/integrations/ingest`) has the same defect. |
| F12 | `function min(uuid) does not exist` | `_dedupe_sales` aggregates a UUID; its key (sku, time, channel, units) also merges genuinely different sales. |
| F02 | Monday 24 Aug cutoff → Sun 30 Aug, Sun 6 Sep… | `pd.date_range(last + W, freq="W")` is `W-SUN`; accuracy joins exact date strings, uses `sale_time <= max_date` (drops the last week's later days) and only the newest run. |
| F03 | code | `formatPrice(x)` defaults source to USD, store rate is a constant 83, sales API returns no currency, importer creates SKUs with DB default `USD`. |
| F04 | code | hard-coded `INDUSTRY_MODELS`/`INDUSTRY_INSIGHT`, `.slice(0, 4)`; fashion overview hard-codes an insight, health score and season. |
| F05 | `no partition of relation "trend_signals"` | only 2026-05..08 partitions; maintenance covers quarterly tables only; UI computes `(1 - 0) * 100` from an empty default. |
| F06 | 4XL, 5XL, `xl` rejected | fixed enum, no normalisation; PATCH never validates; importer ignores `size`. |
| F07 | 73 zero rows rejected | `qty <= 0 → RowError`. |
| F08 | code | loader drops series with < 8 observations and the `max_series` cap silently. |
| F09 | code | 20-unit absolute rule without a decision; pooled SKU `days_of_cover` shown on every location. |
| F10 | code | "realized" total = working capital + carrying cost (derived from it) + revenue protected, at approval. |
| F11 | code | `Digest enabled` string literal. |
| Suite | `assert 0 > 5` right after `google_trends.cooldown.opened` (429) | test lifespan starts the live signal pipeline (default `signal_pipeline_enabled=True`); a real 429 opens the process-global `cooldown`; the mocked test then short-circuits to `[]`. |

## 2. Sales ingestion integrity (F01, F07, F12)

### 2.1 Schema (migration `0022_sales_record_identity`)
- `historical_sales.record_key TEXT NULL`, `historical_sales.location TEXT NULL`,
  index `idx_hsales_tenant_record_key (tenant_id, record_key) WHERE record_key IS NOT NULL`.
- Backfill `record_key` for existing `metadata->>'source' = 'upload'` rows in SQL using the
  same rules as §2.2 (occurrence = `row_number()` within `(tenant, upload_id, base)`).
  **No row is deleted or modified other than the new column.** Existing duplicate copies end up
  sharing a key and become *confirmed duplicates* (§2.5).

### 2.2 Identity rules (`app/services/sales_identity.py`, pure, unit-tested)
`source` namespaces every key (`upload`, or the push connection's provider).
- **Transaction mode, order ID present:** `{source}|o|{order_id}|{line_id or sku_id}#{n}`.
  `line_id` comes from an optional line column (`line`, `line_id`, `line_no`, `line_item_id`).
- **Transaction mode, no order ID:** `{source}|f|{md5(canonical)}#{n}` where
  `canonical = sku_id|sale_time(UTC, µs)|channel|region|location|units|gross(4dp)|net(4dp)`.
- `n` = occurrence of that base key **within the uploaded file**. Two identical rows in one
  file stay two sales; uploading the same file again is a no-op.
- **Period-totals mode (opt-in upload flag `identity=period`):**
  `{source}|p|{sku_id}|{location}|{channel}|{date}`; no ordinal. Two rows for the same key in
  one file are both rejected as row errors (we do not guess which is right).

### 2.3 Replay / correction semantics
- Whole file = one transaction, preceded by `pg_advisory_xact_lock(hashtextextended('sanket:sales-import:'||tenant, 0))`,
  so concurrent uploads for a tenant serialise and a failed upload leaves nothing behind.
- Per row: key absent → insert. Key present, same content → `rows_unchanged`. Key present, content
  differs → update in place (sale_time may move partition), `metadata.revision += 1`,
  `metadata.corrected_by_upload = <upload_id>` → `rows_updated`. Key present on ≥2 rows (legacy
  duplicates) → not touched, counted, left to §2.5.
- Corrections are matchable only for order-keyed rows and period mode. A corrected row without an
  order ID in transaction mode has a different fingerprint and is inserted as new — documented in
  the upload UI help and API response (`identity_mode`, counters).
- Absent rows are never deleted by an import.
- `UploadResult` gains `rows_inserted`, `rows_unchanged`, `rows_updated`, `identity_mode`;
  `rows_imported = inserted + updated`.

### 2.4 Zero demand and availability (F07)
- `quantity == 0` is accepted as **observed zero demand**; negatives still rejected
  ("returns belong in the returns column"); non-numeric rejected.
- New optional columns: `in_stock` (`in_stock`, `instock`, `availability`, `stockout` inverted)
  → `historical_sales.in_stock`; `returns` (`returns`, `returnedqty`, `returnunits`) ≥ 0.
- Sales `location` comes from the existing warehouse/location aliases.
- Meaning downstream: explicit zero row = observed zero; `in_stock=false` = stockout (censored);
  no row = missing (Data Quality "gaps" counts only weeks with no rows).

### 2.5 Duplicates and repair (F12)
- **Confirmed duplicate** = ≥2 rows sharing a `record_key` (provable replay). Identical copies are
  auto-removable; groups whose copies differ are *conflicting* and only reported.
- Rows with no key and fully identical content are reported as *possible duplicates* (warning,
  no autofix, no gate).
- `apply_fix('dedupe_sales')`: preview returns `rows_affected`, `groups_removable`,
  `groups_conflicting`, `units_removed`, samples with `keep_id`/`remove_ids`, and
  `survivor_rule = "lowest id in text order; the copies are identical, so the choice does not
  change any total"`. Confirmed run deletes in the caller's transaction. No UUID aggregate.
- **Forecast gate:** `POST /forecasts/generate`, `POST /forecasts/backtest`, hybrid run submission
  and decision refresh return **409** with a message naming the duplicate count and the fix,
  while confirmed duplicates exist for the tenant/industry.

## 3. Weekly calendar, accuracy and eligibility (F02, F08)

### 3.1 Convention
**Weeks start Monday 00:00 UTC.** Every weekly bucket is `date_trunc('week', sale_time AT TIME ZONE 'UTC')`
(loader, accuracy, data quality, decisions, ROI, coverage) so the DB session time zone cannot shift
it. Naive import timestamps stay UTC. Limitation: sales timestamped 00:00–05:30 IST on a Monday
fall in the prior week; a workspace planning timezone is a follow-up.

### 3.2 Training window and future dates
- Default `end` = start of the current week (complete weeks only). Bounds are tz-aware UTC.
- Each series is reindexed to the **panel's last week** (latest week with any tenant sales), so a
  SKU whose sales stopped earlier carries explicit zero weeks rather than a short series.
- Future dates: `pd.date_range(last_week + 7d, periods=h, freq="W-MON")`.
- Run metadata: `calendar="W-MON-UTC"`, `history_end` (exclusive, = last_week + 7d),
  `first_forecast_week`, `omitted` counts. Export gets explicit "Week start (Mon, UTC)"/"Week end".

### 3.3 Explicit backtest
`POST /forecasts/backtest {cutoff: Monday, horizon}` → ML `/forecast` with `history_end=cutoff`
(loader `end=cutoff`, zero-shot only) → persisted run `metrics.mode="backtest"`. Leakage-free by
construction and asserted (`max(context ds) < cutoff`).

### 3.4 `/forecast/accuracy`
- Only runs with `metrics.calendar == "W-MON-UTC"` (legacy Sunday-dated runs excluded, counted).
- Only matured weeks (`week_start + 7d <= now`).
- **Production:** per SKU-week, the latest run with `completed_at <= week_start` and
  `history_end <= week_start`. **Backtest:** runs with `mode=backtest`, `history_end <= week_start`.
  Reported in separate sections; never merged.
- Actual = units with `week_start <= sale_time < week_start + 7d`. No rows: 0 if the tenant's feed
  has data at or after `week_end`, else excluded as `awaiting_actuals`.
- Response keeps `rows` (sku_id, model_name, mape, wape, n_obs, computed_at) and adds
  `sku_code`, `bias_pct`, `summary` (points, portfolio WAPE, bias), `excluded` counts by reason,
  `calendar`, and `backtest` section. The cache short-circuit is removed (nothing writes that table).

### 3.5 Eligibility (F08)
ML response adds `omitted: [{sku_id, reason, observations}]` (`no_sales_history`,
`insufficient_history`, `series_cap`, `not_in_model`) for every active SKU not forecast, plus
`history_end`, `first_forecast_week`, `calendar`. No eligible series → 422 naming the counts.
Analogue/new-product forecasting is out of scope; copy promising never-sold curves is corrected.

## 4. Catalogue (F06)
`app/services/fashion_sizes.py`: canonical `XS, S, M, L, XL, XXL, 3XL, 4XL, 5XL, 6XL, FREE`;
case/space-insensitive; `2XL→XXL`, `XXXL→3XL`, `XXXXL→4XL`, `XXXXXL→5XL`, `XXXXXXL→6XL`,
`FREE SIZE|FREESIZE|FS|ONE SIZE→FREE`. Original kept as `size_label` when it differs. Applied on
SKU create, PATCH (now validated), products/sales/inventory import (size column → attributes,
invalid → row error, variant SKUs never merged) and the size curve (grouped and ordered canonically).

## 5. Signals (F05)
- Migration `0023_trend_signal_partitions`: `sanket_ensure_monthly_partitions(parent, lookback=2,
  lookahead=3, anchor=current_date)` (SECURITY DEFINER, pinned search_path, idempotent) and
  `sanket_maintain_partitions()` extended with `trend_signals`. Runs at migration, app startup and
  the existing CronJob. No automatic retention deletion (documented).
- Pipeline records `last_run` per industry (samples, persisted, error).
- `/trends/score` adds `evidence {status: unavailable|insufficient|stale|available, sample_count,
  source_count, newest_sample_at, min_samples=3, stale_after_hours=48, last_ingest, message}`;
  `volatility` is `null` unless `available`. UI shows "insufficient evidence", never agreement from
  zero samples; forecast pages state when no signal adjustment was applied.

## 6. Inventory coverage (F09)
`GET /inventory/coverage`, independent of decisions:
- Demand basis: latest calendar-aware run completed ≤ 14 days ago containing the SKU (mean p50 of
  first 4 weeks) → else trailing 8 complete weeks of actuals if ≥ 4 weeks observed → else unknown.
- SKU-wide cover = pooled available / daily demand. Status: unknown (no basis, no stock, stock
  older than 30 days), critical (≤ lead), low (≤ 1.5 × lead), healthy.
- Location cover only when that location has ≥ 4 of the last 8 weeks of location-tagged sales;
  otherwise `null` with the reason, and the row is labelled with the pooled SKU-wide figure.
- No transfer suggestions. Inventory page uses this endpoint; the 20-unit rule is removed.

## 7. Money and claims (F03, F04, F10, F11)
- **F03:** sales analytics responses carry `currency`; mixed currencies → `currency: null`,
  `revenue_by_currency`, no cross-currency totals. New SKUs take currency from a row column, an
  upload `currency` field, or workspace `settings.currency`, else DB default with a response
  warning. Row currency ≠ existing SKU currency → row error. Frontend: `formatPrice(amount,
  sourceCurrency)` requires the source; conversion only with a user-entered rate stored with its
  date and shown as "manual rate · set <date>"; persisted state migrates away from the constant 83.
- **F04:** forecast page shows actual source/model, horizon, SKUs forecast, omitted SKUs and reasons,
  and "no external signals applied"; paginates every SKU; indicative estimates labelled; 422/503
  states explicit. Hard-coded model/insight maps removed; fashion overview hard-coded insight,
  health score and season removed; `active_models` presented as "supported approaches"; landing
  copy corrected.
- **F10:** ROI returns tiers `opportunity` (open), `estimated_at_approval` (accepted) and `observed`
  (realized savings `null` with reason until receipts/outcomes exist; forecast-vs-naive is a
  measured line). Per-currency values, no grand total across unlike measures (carrying cost is
  marked derived, not additive), "stockouts avoided" → "approved orders on alerted SKUs".
  `total_value_realized` removed; UI wording follows.
- **F11:** dashboard derives WhatsApp state from `/notifications/whatsapp`: disabled, preview only
  (provider not connected), no recipients, ready, status unavailable.

## 8. Suite isolation
`tests/conftest.py` sets `SIGNAL_PIPELINE_ENABLED`, `SHOPIFY_POLL_ENABLED` (and the digest worker)
to false before the app is imported — the suite was calling Google Trends, Reddit, FRED, etc.
`test_external_signals.py` resets the `cooldown` singleton around each test and gains a test that
an open cooldown suppresses calls. Nothing is skipped, weakened or retried.

## 9. Forecast evaluation
`backend/ml/benchmarks/rolling_origin.py` on the labelled synthetic fashion fixture
(audit CSVs, read-only): validation cutoffs 2026-04-13, 05-11, 06-08, 07-06 (windows end ≤ test
cutoff); test cutoff 2026-08-31; horizon 8. Leakage asserts per fold. Models on identical folds:
Chronos zero-shot (seeded), last value, 4-week mean, seasonal naive (52), Croston-SBA, ADIDA.
Routing (per-SKU best and intermittency rule) selected on validation folds only and scored once on
the test fold. Reports portfolio / per-SKU / per-cohort WAPE, bias, P10–P90 coverage (models with
intervals), omitted coverage and cross-cutoff spread. Production routing ships only if it wins on
validation **and** holds on test; otherwise the limitation is surfaced in product and report.

## 10. Verification
Six suites (frontend typecheck/lint/test/build, backend pytest, ML pytest); migrations on a fresh DB
and on a disposable restore of a read-only `pg_dump` of the audit DB; RLS/authorization neighbours;
Playwright journey (import → replay → forecast → backtest + actuals/accuracy → inventory →
decisions/scenario → export) with configurable `E2E_BASE_URL`, `VITE_PROXY_TARGET`,
`VITE_API_BASE_URL`, `VITE_WS_BASE_URL`; fresh screenshots; report in
`docs/audit/2026-10-26-fashion-remediation/REPORT.md`.

## 11. Out of scope / external prerequisites
Real Swecha data and accuracy, realised savings, live POS/ERP/Shopify connector sync, WhatsApp
delivery, payments, deployment, analogue new-product model, workspace planning timezone,
inter-store transfer suggestions, automatic trend-signal retention.
