# Workspace-review Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve the 16 findings of the 2026-10-26 deep workspace review, with a regression per confirmed defect.

**Architecture:** Backend gains one shared readiness module (`planning_inputs.py`) used by coverage, decisions and the simulator, and explicit unknown-money handling in the pure engines. Frontend gains a per-identity QueryClient, one planning-invalidation helper, a small query-state primitive, an accessible mobile drawer and a route scroll manager.

**Tech Stack:** FastAPI, SQLAlchemy async, PostgreSQL 16 RLS, pytest + testcontainers; React 18, TanStack Query 5, React Router 6, Tailwind, Vitest + Testing Library.

**Spec:** `docs/superpowers/specs/2026-10-26-workspace-review-remediation-design.md`

## Global Constraints

- Tenant isolation stays in PostgreSQL RLS; app code uses `db.session(str(tenant_id))`, never `session_no_rls`, for tenant data.
- Never invent signals, stock, money, forecasts or accuracy; unknown is `None`/"Unavailable", not 0.
- Confidence score ≠ measured accuracy; copy must not equate them.
- Icons only from `frontend/src/components/ui/icons.tsx`.
- No new dependencies.
- No commits or pushes (user instruction) — every "commit" step is replaced by "leave uncommitted; record files in the resolution matrix".
- Preserve pre-existing uncommitted edits (backup: scratchpad `pre-existing.diff`).
- Freshness constants: forecast ≤ 14 days old; stock `as_of` ≤ 30 days; weekly calendar Monday 00:00 UTC.

Backend test command: `cd backend && uv run pytest <path> -q`. Frontend: `cd frontend && npx vitest run <path>`.

---

### Task 1: Recommendation expiry enforced server-side (finding 2)

**Files:**
- Modify: `backend/app/routers/decisions.py` (list filter, accept guard, `expired` flag)
- Test: `backend/tests/test_decision_expiry.py` (new)

**Interfaces:** Produces `decisions.is_expired(rec, now) -> bool`.

- [ ] **Step 1: Write the failing tests** — seed a tenant via `signed_in_workspace`, insert a SKU and three open recommendations (`expires_at` = now−30d, now+1d, and a boundary row), then:

```python
async def test_open_list_excludes_time_expired(client, ws):  # ws = (tenant, headers, ids)
    r = await client.get("/api/v1/decisions?status=open", headers=headers)
    ids = {d["id"] for d in r.json()["decisions"]}
    assert expired_id not in ids and live_id in ids

async def test_expired_filter_includes_time_expired_open_rows(...):
    r = await client.get("/api/v1/decisions?status=expired", headers=headers)
    assert expired_id in {d["id"] for d in r.json()["decisions"]}

async def test_accepting_expired_recommendation_is_rejected(...):
    r = await client.post(f"/api/v1/decisions/{expired_id}/accept", json={}, headers=headers)
    assert r.status_code == 409 and "expired" in r.json()["detail"].lower()
    # status unchanged in DB
    assert await db_session.scalar(text("SELECT status::text FROM recommendations WHERE id=:i"), {"i": expired_id}) == "open"

def test_boundary_is_expired():
    now = datetime(2026, 10, 26, tzinfo=UTC)
    assert is_expired(SimpleNamespace(expires_at=now), now)
    assert not is_expired(SimpleNamespace(expires_at=now + timedelta(seconds=1)), now)
```

- [ ] **Step 2:** Run `uv run pytest tests/test_decision_expiry.py -q` → FAIL (accept returns 200; list contains expired row; `is_expired` undefined).
- [ ] **Step 3: Implement**

```python
def is_expired(rec, now: datetime) -> bool:
    return rec.expires_at is not None and rec.expires_at <= now
```
List: for `status == "open"` add `or_(Recommendation.expires_at.is_(None), Recommendation.expires_at > now)`; for `status == "expired"` use `or_(status == expired, and_(status == open, expires_at <= now))`. Serialized items get `"expired": is_expired(r, now)` (and `status` reported as `"expired"` for time-expired open rows). Accept: after the open check, `if is_expired(rec, now): raise HTTPException(409, f"Recommendation expired at {rec.expires_at.isoformat()}. Recompute decisions to act on current inputs.")`.
- [ ] **Step 4:** Re-run → PASS. Re-run `docs/audit/.../deep/diagnostics.py` → note it patches `_load`; update the probe expectation in the matrix (`accepted: false`, HTTPException 409).
- [ ] **Step 5:** Leave uncommitted.

### Task 2: Shared planning-input readiness module (finding 6, part 1)

**Files:**
- Create: `backend/app/services/planning_inputs.py`
- Modify: `backend/app/services/coverage.py` (import constants/helpers; behaviour unchanged)
- Test: `backend/tests/test_planning_inputs.py` (new)

**Interfaces — Produces:**
```python
FORECAST_MAX_AGE_DAYS = 14
STALE_STOCK_DAYS = 30
def run_age_days(run, now) -> float | None
def is_run_fresh(run, now) -> bool
def stock_is_stale(as_of: datetime | None, now) -> bool
async def future_forecast_bands(session, tenant_id, run_id, now) -> dict[uuid.UUID, DemandBand]
```

- [ ] **Step 1: Failing tests** — pure tests for `is_run_fresh` (13d fresh, 15d stale, `completed_at None` stale, naive datetime treated as UTC), `stock_is_stale` (None stale, 31d stale, 29d fresh); DB test: a run whose results start 3 weeks before `NOW` yields bands whose first p50 is the current-week value (reuse `_sku`/`_forecast` patterns from `test_inventory_coverage.py` with distinct p50 per week).
- [ ] **Step 2:** Run → FAIL (module missing).
- [ ] **Step 3:** Implement; `future_forecast_bands` = `forecast_bands` query plus `ForecastResult.forecast_date >= current_week_start(now)`. Coverage imports `FORECAST_MAX_AGE_DAYS`, `STALE_STOCK_DAYS`, `is_run_fresh`, `stock_is_stale`.
- [ ] **Step 4:** Run new tests + `tests/test_inventory_coverage.py` → PASS.

### Task 3: Decisions use the readiness contract and unknown money (findings 3 and 6)

**Files:**
- Modify: `backend/app/services/decision_engine.py` (`SkuEconomics.cost_known/price_known`; `None` money)
- Modify: `backend/app/services/decision_builder.py` (fresh run, future bands, stock gating, `skipped`, `now` param)
- Modify: `backend/app/routers/decisions.py` (`_totals` skips `None`, adds `money_complete`; refresh returns `skipped`)
- Test: `backend/tests/test_decision_engine.py` (extend), `backend/tests/test_decision_readiness.py` (new)

**Interfaces — Produces:** `BuildResult.skipped: list[dict]` (`{"sku_code", "reason"}`); `build_decisions(..., now: datetime | None = None)`; `SkuEconomics(cost_known=True, price_known=True)`.

- [ ] **Step 1: Failing tests**

```python
def test_unknown_cost_yields_no_capital_figures():
    sku = SkuEconomics(sku_id="a", sku_code="A", on_hand_units=0, unit_cost=0.0, unit_price=100, cost_known=False)
    [d] = [x for x in decide(sku=sku, band=BAND, confidence=CONF) if x.kind == "purchase_order"]
    assert d.economics["capital_committed"] is None
    assert d.economics["revenue_protected"] is not None

def test_recorded_zero_cost_stays_zero():
    sku = SkuEconomics(..., unit_cost=0.0, cost_known=True)
    assert order(sku).economics["capital_committed"] == 0.0
```
DB (`test_decision_readiness.py`): (a) run completed 20 days before `NOW` ⇒ `build_decisions(now=NOW)` returns no decisions and reason mentions "older than 14 days"; (b) fresh run, SKU with no `inventory_levels` row ⇒ no decision for it and `skipped` contains its code with "no recorded stock"; (c) stock `as_of` 40 days old ⇒ skipped "stock last updated 40 days ago"; (d) results starting 3 weeks in the past ⇒ decision inputs use current-week p50 (`inputs.demand_p50_over_window` equals sum from current week).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement. Engine: money keys use helper `_money(value, known)` → `round(value,2) if known else None`; excess `capital_locked` reason only when `cost_known`; `carrying_cost` reason requires `cost_known and unit_cost > 0`; `_inputs_blob` emits `unit_cost: None` when unknown. Builder: `run` must satisfy `is_run_fresh(run, now)` else reason `"The latest forecast completed N days ago — older than 14 days. Generate a new forecast before recomputing decisions."`; bands via `future_forecast_bands`; load `InventoryLevel` rows per SKU (as_of) and skip missing/stale; set `cost_known=sku.unit_cost is not None`, `price_known=sku.unit_price is not None`; `lead_time_assumed` added to inputs. Persist: `unit_cost`/`unit_price` columns keep `0` only when known — store `None` when unknown if the column is nullable, else keep 0 but `inputs.unit_cost=None` is the source of truth (check model). `_totals`: sum only non-None; add `"money_complete": all(...)`.
- [ ] **Step 4:** Run engine + readiness + existing decision tests → PASS.

### Task 4: Simulator — readiness, unknown money, horizon cap (findings 3, 6, 7)

**Files:**
- Modify: `backend/app/services/scenario.py` (`None` money, portfolio `None` unless complete, `valuation_coverage`, horizon cap)
- Modify: `backend/app/routers/scenarios.py` (future bands, readiness block, cost/price known, cap)
- Test: `backend/tests/test_scenario_simulator.py` (extend)

**Interfaces — Produces:** response keys `readiness`, `valuation_coverage`, `config.requested_horizon_weeks`, `config.forecast_weeks_available`, `config.horizon_capped_reason`.

- [ ] **Step 1: Failing tests**

```python
def test_horizon_is_capped_to_forecast_weeks():
    out = compare(skus=[SKU], bands={"a": band12}, scenario=Scenario(), config=SimConfig(horizon_weeks=26))
    assert out["config"]["horizon_weeks"] == 12
    assert out["config"]["requested_horizon_weeks"] == 26
    assert "12 weeks" in out["config"]["horizon_capped_reason"]
    assert len(out["by_sku"][0]["weekly"]["demand"]) == 12

def test_unknown_cost_suppresses_margin_and_spend():
    sku = SkuEconomics(..., unit_cost=0.0, unit_price=100, cost_known=False)
    out = compare(...)
    assert out["baseline"]["gross_margin"] is None and out["impact"]["purchase_spend"] is None
    assert out["baseline"]["shipped_units"] > 0
    assert out["valuation_coverage"] == {"skus_with_cost": 0, "skus_with_price": 1, "skus_total": 1}
```
API test via `signed_in_workspace`: stale run (20d) ⇒ 200 with `readiness.forecast_stale is True` and `readiness.advisory is True`; SKU without stock ⇒ `readiness.skus_missing_stock == [code]`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement. `compare` computes `available = min(len(b.p50) for simulated bands)`; effective horizon `min(config.horizon_weeks, available)`; `apply_levers` no longer pads (raise if `horizon > len(band.p50)`). Money: `SkuOutcome` money fields `float | None`; portfolio money = `None` if any outcome's needed input unknown. Router builds readiness using `planning_inputs`.
- [ ] **Step 4:** Run `tests/test_scenario_simulator.py` → PASS; re-run `diagnostics.py` after updating it to call `compare` (records cap).

### Task 5: Sales timeseries distinguishes no-records from zero (finding 5, backend)

**Files:** Modify `backend/app/routers/sales_analytics.py`; Test `backend/tests/test_sales_timeseries_zero.py` (new).

- [ ] **Step 1: Failing test** — tenant with sales only in weeks W−4 and W−2 (none in W−3), request `granularity=week&lookback_days=84`: buckets before W−4 have `units_sold is None`, W−3 has `0`, response has `first_sale_at` and `complete_through` (last complete week start).
- [ ] **Step 2:** FAIL. **Step 3:** query `min(sale_time)` for the tenant/industry; buckets before its bucket get `None` units/revenue; add `"first_sale_at"`, `"current_bucket_partial": True`, `"units_basis": "gross_units_sold_returns_not_netted"`. **Step 4:** PASS + `tests/test_sales_currency.py`.

### Task 6: Coverage excess status (initial-report opportunity)

**Files:** Modify `backend/app/services/coverage.py`; Test `backend/tests/test_inventory_coverage.py` (extend).

- [ ] **Step 1: Failing test** — 1000 units, 4 units/week trailing, lead 14 ⇒ cover 1750 days > 2×(14+28) ⇒ `sku_wide.status == "excess"`, reason mentions "pause reorders".
- [ ] **Step 2:** FAIL. **Step 3:** `_status(cover, lead, review_days)` returns `"excess"` when `cover > 2 * (lead + review_days)`; `review_days` from `load_policy(tenant.settings).review_period_days` (default 28); policy block adds `excess_multiplier: 2`. **Step 4:** PASS all coverage tests.

### Task 7: Backend warnings (finding 16)

**Files:** `backend/tests/test_billing.py` (AsyncMock contract), others as triaged.
- [ ] Run `uv run pytest -q -W default 2>&1 | grep -i warning | sort | uniq -c | sort -rn | head -30` to classify; fix the unawaited `AsyncMock` (use `MagicMock` for sync attributes like `session.add`) and any warnings owned by this repo; leave third-party deprecations listed in the matrix. Verify count drops.

### Task 8: Per-identity QueryClient (finding 1)

**Files:**
- Create: `frontend/src/components/auth/IdentityQueryProvider.tsx`
- Modify: `frontend/src/App.tsx` (replace module-level client)
- Test: `frontend/src/components/auth/IdentityQueryProvider.test.tsx`

**Interfaces — Produces:** `IdentityQueryProvider({children})`, `createAppQueryClient(): QueryClient`.

- [ ] **Step 1: Failing test**

```tsx
it("does not serve account A's cached data to account B in the same industry", async () => {
  useAuthStore.setState({ isAuthenticated: true, tenantId: "A", userId: "ua", industry: "fashion" });
  const fetcher = vi.fn().mockResolvedValueOnce(["A-private-row"]).mockResolvedValueOnce([]);
  render(<IdentityQueryProvider><Probe fetcher={fetcher} /></IdentityQueryProvider>);
  expect(await screen.findByText("A-private-row")).toBeInTheDocument();
  act(() => useAuthStore.setState({ tenantId: "B", userId: "ub" }));
  await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(2));
  expect(screen.queryByText("A-private-row")).not.toBeInTheDocument();
});
it("discards an in-flight response from the previous identity", ...); // deferred promise resolved after switch
it("clears on logout", ...);
```
`Probe` uses `useQuery({ queryKey: ["decisions","fashion","open"], queryFn: fetcher, staleTime: 30_000 })`.
- [ ] **Step 2:** FAIL. **Step 3:** provider keeps `useState` of `{key, client}`; on store key change: `prev.client.cancelQueries(); prev.client.clear();` then create new; render `<QueryClientProvider key={key} client={client}>`. **Step 4:** PASS; update `cache-probe.mjs` companion note.

### Task 9: Planning invalidation graph (finding 9)

**Files:**
- Create: `frontend/src/api/planningKeys.ts` (`PLANNING_KEYS`, `invalidatePlanningData(qc)`)
- Modify: `PlanningBriefDashboard.tsx`, `Inventory.tsx`, `Decisions.tsx`, `Integrations.tsx` (catalog key unification + upload uses helper)
- Test: `frontend/src/api/planningKeys.test.ts`, extend `frontend/src/pages/Inventory.test.tsx`

- [ ] **Step 1: Failing tests** — `invalidatePlanningData` invalidates every key prefix in `PLANNING_KEYS` (spy on `qc.invalidateQueries`); Inventory: after a successful import, the coverage API mock is called again and the row shows the new cover.
- [ ] **Step 2:** FAIL. **Step 3:** implement; keys: `inventory-levels, inventory-coverage, decisions, dashboard-forecast, dashboard-history, forecast-confidence, data-quality, roi-summary, ["integration","catalog"], cost-analysis, forecasts`. **Step 4:** PASS.

### Task 10: Explicit query states (finding 8)

**Files:**
- Create: `frontend/src/components/ui/QueryState.tsx` (`queryStatus(q)`, `<QueryErrorNotice>`)
- Modify: Inventory, Decisions, PlanningBriefDashboard
- Test: `frontend/src/components/ui/QueryState.test.tsx`, Inventory/Decisions tests

**Interfaces — Produces:** `queryStatus(q: {isPending,isError,data,dataUpdatedAt}) -> "loading"|"error"|"stale"|"empty"|"ready"`.

- [ ] **Step 1: Failing tests** — Inventory with levels API rejecting renders `role=alert` "Stock could not be loaded" and not "No stock data yet"; Decisions with list rejecting does not render the "no open decisions" empty state; Dashboard with decisions rejecting shows "Unavailable" for Orders due and never "No open order decision currently requires approval"; coverage rejecting shows "Cover unavailable" rather than "No action".
- [ ] **Step 2:** FAIL. **Step 3:** implement. **Step 4:** PASS.

### Task 11: Dashboard weekly alignment, uncertainty label, composition (findings 4, 13, 14)

**Files:** `PlanningBriefDashboard.tsx`, `frontend/src/api/salesAnalytics.ts` (types), test `frontend/src/components/dashboard/PlanningBriefDashboard.test.tsx` (new)

- [ ] **Step 1: Failing tests** — `salesAnalyticsApi.timeseries` called with `("week", 84)`; the partial current bucket is not passed to the chart; label "units / week"; text "Sum of per-SKU P10–P90 ranges"; "4 low-confidence SKUs" link to `/workspace/forecasts`; "12 SKUs use an assumed lead time"; "Confidence is a data-quality heuristic, not measured accuracy".
- [ ] **Step 2:** FAIL. **Step 3:** implement (counts from `confidence.data.skus` band `low|insufficient`, data-quality `critical` issues, coverage `lead_time_assumed`). **Step 4:** PASS.

### Task 12: ForecastChart zeros + accurate summary (findings 5, 16)

**Files:** `ForecastChart.tsx`, test `frontend/src/components/charts/ForecastChart.test.tsx` (new)
- [ ] **Step 1:** Failing tests: history `[{actual:3},{actual:0},{actual:null}]` ⇒ zero kept (exposed via summary "including 1 week with zero sales"), null gap counted as "no records"; negative excluded with note; summary with p50 `[5, 40, 2]` says "lowest 2, highest 40".
- [ ] **Step 2–4:** implement `actual: number | null`; filter `actual == null || actual >= 0`.

### Task 13: Inventory provenance, lead-time badge, excess UI (findings 14, 16, opportunity)

**Files:** `Inventory.tsx`, `frontend/src/api/inventory.ts` (types: `excess`, `as_of`), `Inventory.test.tsx`
- [ ] Failing tests: row with `source: "csv"` shows "CSV import · as of 25 Oct" (no "Real"); `lead_time_assumed` row shows "Lead time assumed (14-day default)"; excess row shows "Excess" badge and "Pause reorders, review inbound, consider transfer or markdown". Implement; PASS.

### Task 14: Simulator UI — advisory, unavailable money, cap, reflow (findings 3, 6, 7, 12)

**Files:** `WhatIfScenario.tsx`, `frontend/src/api/scenarios.ts` (types), test `frontend/src/pages/WhatIfScenario.test.tsx` (new)
- [ ] Failing tests: null `impact.gross_margin` ⇒ "Unavailable" + "12 of 12 SKUs missing unit cost"; `readiness.advisory` ⇒ "Advisory" badge listing reasons; `horizon_capped_reason` shown; slider `max` equals `forecast_weeks_available`; layout classes `min-w-0` on grid children (assert class). Implement; PASS. Browser check at 320/390/768 in Task 18.

### Task 15: Accessible mobile drawer + search copy/contrast (findings 10, 11, 16)

**Files:** `Sidebar.tsx`, `AppShell.tsx`, `TopBar.tsx` (opener ref), test `frontend/src/components/layout/Sidebar.test.tsx` (new)
- [ ] Failing tests (matchMedia mocked to mobile): opening moves focus into the drawer's search; Tab from last focusable wraps to first; main column has `inert`; Escape closes and focus returns to the opener button; closed drawer has `inert`; placeholder "Find a page…"; shortcut shows "Ctrl K" when `navigator.platform` is "Win32". Implement with a `useMediaQuery("(min-width:1024px)")` hook; mobile classes use `text-content`, `placeholder:text-content-subtle`, `border-line`, `bg-surface-2` with `lg:` overrides for the dark rail. PASS.

### Task 16: Route scroll manager (finding 15)

**Files:** Create `frontend/src/components/layout/ScrollManager.tsx`; mount in `AppShell.tsx`; test `ScrollManager.test.tsx`.
- [ ] Failing tests with `MemoryRouter`: PUSH to new path sets `#main-content.scrollTop = 0`; POP restores the saved value for that location key; same-path search change does not reset. Implement with `useLocation` + `useNavigationType`. PASS.

### Task 17: Integrations grouping + lint warnings (finding 16)

**Files:** `Integrations.tsx`, `Integrations.test.tsx`, files listed in lint baseline.
- [ ] Failing test: healthy connected CSV upload appears under "Connected sources", not "Needs attention"; an `error` connector appears under "Needs attention". Implement. Then fix each of the 28 lint warnings (hook deps first via `useCallback`/memoised arrays, then `any` → precise types). `npm run lint` → 0 warnings.

### Task 18: Verification, evidence, matrix

- [ ] `cd frontend && npm run typecheck && npm run lint && npm test`; `cd backend && uv run pytest` — record actual counts.
- [ ] Re-run probes (`cache-probe` replaced by provider test; `diagnostics.py` updated) and save outputs under `docs/audit/2026-10-26-workspace-review/remediation/`.
- [ ] Browser (in-app Browser pane; gstack `/browse` not installed): dashboard, inventory, decisions, scenarios at 320/390/768/desktop; keyboard drawer journey; screenshots saved; scroll behaviour.
- [ ] Write `docs/audit/2026-10-26-workspace-review/remediation/RESOLUTION.md` (ID, root cause, files, regression, result, evidence, status).
- [ ] `superpowers:requesting-code-review` over the diff; address findings; `superpowers:verification-before-completion`.
