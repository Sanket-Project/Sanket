# Workspace-review remediation — design

Date: 2026-10-26 · Status: approved in chat (2026-10-26) · Source findings:
`docs/audit/2026-10-26-workspace-review/deep/REPORT.md` (findings 1–16) and
`docs/audit/2026-10-26-workspace-review/REPORT.md` (opportunities).

Decisions taken with the user: per-identity QueryClient; strict decisions with an
advisory simulator; simulator horizon capped to the forecast; coverage reuses the
decision engine's excess-stock rule. Spec intentionally left uncommitted (user
instruction: no commits).

## A. Identity isolation (finding 1)

- `IdentityQueryProvider` (frontend/src/components/auth) derives
  `identityKey = tenantId:userId` (or `anon`) from the auth store and owns one
  `QueryClient` per key. On a key change it `cancelQueries()` + `clear()`s the
  previous client before discarding it. Logout ⇒ key `anon` ⇒ cleared.
- No query key changes are needed; isolation is by client, so a future key
  cannot forget the tenant.
- Regression: two accounts, same industry, same key — B's fetch runs and A's data
  is never rendered; in-flight A request resolving after the switch does not
  reach B.

## B. Server-side planning correctness

### Expiry (finding 2)
- `GET /decisions?status=open` excludes `expires_at <= now`; `status=expired`
  also returns open rows whose `expires_at <= now`. Response items carry
  `expired: bool` derived server-side.
- `POST /decisions/{id}/accept` on an open row with `expires_at <= now` → 409
  `"Recommendation expired at <ts>. Recompute decisions to act on current inputs."`.
  Boundary is inclusive (`== now` is expired).
- DB regressions against a real tenant (RLS session).

### Shared readiness contract (finding 6)
- New `app/services/planning_inputs.py`: `FORECAST_MAX_AGE_DAYS=14`,
  `STALE_STOCK_DAYS=30`, `run_age_days(run, now)`, `is_run_fresh(run, now)`,
  `stock_is_stale(level, now)`, and `future_forecast_bands(session, tenant, run,
  now)` returning bands only from the current UTC Monday forward.
- `coverage.py` imports these (behaviour unchanged).
- Decisions (`build_decisions`): stale/absent run ⇒ empty result with reason;
  bands are future-only; SKUs with no stock row or stock older than 30 days are
  skipped and reported in `BuildResult.skipped` (`sku_code`, reason); never
  treated as zero on hand.
- Simulator: runs on the latest run with future-only bands, and returns
  `readiness = {forecast_run_id, forecast_completed_at, forecast_age_days,
  forecast_stale, skus_missing_stock, skus_stale_stock, skus_lead_time_assumed,
  skus_missing_cost, skus_missing_price, advisory}`. `advisory` is true when any
  input is stale/missing/assumed. UI shows an "Advisory" badge listing reasons.

### Unknown money (finding 3)
- `SkuEconomics` gains `cost_known: bool = True`, `price_known: bool = True`.
  Builders set them from `Sku.unit_cost is not None` / `unit_price is not None`
  (a recorded 0 stays a known 0).
- Decision engine: money derived from an unknown input is `None`
  (`capital_committed`, `baseline_capital`, `working_capital_released`,
  `holding_cost_over_window`, `capital_locked`, `annual_holding_cost`,
  `capital_delta` need cost; `revenue_protected` needs price). The
  excess-stock capital reason is omitted when cost is unknown. `_totals` sums
  only known values and reports `*_complete` flags.
- Simulator: per-SKU money is `None` when the input is unknown; portfolio money
  totals and impacts are `None` unless every simulated SKU is valued;
  `valuation_coverage = {skus_with_cost, skus_with_price, skus_total}`.
- UI: "Unavailable" with "N of M SKUs missing unit cost/price" and a Data
  Quality link; quantities remain.

### Horizon (finding 7)
- Simulation horizon = `min(requested, forecast weeks available)`; response adds
  `requested_horizon_weeks` and `horizon_capped_reason`. No extrapolated weeks.
  The UI slider max follows `config.forecast_weeks_available` when known.

## C. Charts, states, invalidation

- Weekly alignment (4): dashboard history uses `timeseries("week", 84)`; the
  current partial week is excluded; y-axis/label "units / week".
- Zeros (5): `ForecastChart` keeps finite values `>= 0`; `timeseries` returns
  `first_sale_at` and leaves buckets before the tenant's first recorded sale as
  `null` (no records), zero-filling only after it. `units_sold` is gross units;
  returns are not netted (documented in the chart caption). Negative values are
  excluded and disclosed.
- States (8): `QueryState` helper (`loading | error | empty | ready`, with
  `stale` when showing a last-good value after an error, plus `updatedAt`).
  Applied to dashboard summary/readiness, Inventory, Decisions. A failed query
  never renders a numeric 0 or "No action".
- Invalidation (9): `invalidatePlanningData(qc)` in `frontend/src/api/planningKeys.ts`
  invalidates levels, coverage, decisions, dashboard forecast/history,
  confidence, data quality, ROI and the integration catalog. Used by dashboard
  Refresh, Inventory Refresh/import, integration uploads, decision
  accept/dismiss/refresh. Catalog key unified to `["integration","catalog"]`.
- Uncertainty (13): dashboard label "Sum of per-SKU P10–P90 ranges — not a
  calibrated portfolio interval". No calibration claim.
- Composition (14): dashboard shows low-confidence SKU count (→ Forecasts),
  critical data-quality blockers (→ Data Quality) and lead-time-assumed count;
  Inventory/Decisions rows show "Lead time assumed (14-day default)". Copy states
  confidence ≠ measured accuracy.
- Excess (opportunity): coverage status `excess` when cover days exceed
  2 × (lead time + review period) — the decision engine's existing
  position > 2 × order-up-to rule expressed in days. Next action text: pause
  reorders, review inbound, consider transfer or markdown.

## D. Navigation, accessibility, polish

- Search contrast (10): mobile uses semantic tokens; teal-on-dark only at `lg:`.
- Drawer (11): on open focus moves to search; Tab/Shift+Tab trapped; main column
  `inert`; Escape closes and returns focus to the opener; closed mobile drawer is
  `inert` + `aria-hidden` (desktop unaffected). No dependency.
- Scenario reflow (12): `min-w-0` on grid children; one column below `lg`;
  wrapping labels; tables scroll inside their own container. Verified at 320,
  390, 768 px.
- Scroll (15): `ScrollManager` resets `#main-content` to top on PUSH/REPLACE
  pathname changes; on POP restores the saved position for that location key.
- Polish (16): "Find a page", Ctrl+K on non-Apple platforms; Integrations
  "Needs attention" (error/requested) vs "Connected"; inventory provenance label
  from `source` + as-of date; chart summaries use real min/max; 28 lint warnings
  fixed; billing AsyncMock warnings fixed, other backend warnings triaged.

## Testing

RED→GREEN per finding; audit probes re-run; full typecheck, lint, vitest,
pytest; browser journeys at 320/390/768/desktop with keyboard checks.
Evidence and the resolution matrix live in
`docs/audit/2026-10-26-workspace-review/remediation/`.
