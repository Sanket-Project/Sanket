# Location-level forecasting, allocation and transfers — design

Date: 2026-10-26 · Status: approved in chat (2026-10-26) · Path: architectural

Decisions taken with the user:

- **Network shape:** a central warehouse (DC) supplies the branches. Suppliers
  ship to the DC; the DC allocates to stores. Store↔store transfers are the
  secondary lever.
- **Execution:** advisory only. Allocations and transfers are recommendations
  in the existing ledger (accept / dismiss); the user executes them in their
  own ERP/WMS. No write-back to connectors.
- **Access:** head-office users see every location in v1. Branch-scoped logins
  are a later phase (§9), not built here.
- **First vertical:** Apparel & Fashion. The engine is industry-agnostic, but
  validation, fixtures and defaults target fashion first.
- **Forecast method:** top-down share split (method A) in v1. The schema and
  backtest are built so middle-out + MinT reconciliation (method C) can be added
  later, but only once evidence shows it is better (§4.5).

## 1. Problem

A tenant such as "company A" has one DC and N branches, all sharing a catalogue
of ~25,000 SKUs. Its sales export already records which branch sold what.
SANKET today:

- forecasts per SKU only — the ML loader groups by `sku_id` and ignores
  location (`backend/ml/sanket_ml/data/loader.py:87`), and `ForecastResult` has
  no location column;
- recommends purchases on stock pooled across every location
  (`decision_builder.py:386`), which is correct for DC purchasing;
- computes per-location cover in `coverage.py`, but makes no allocation or
  transfer decisions (its own docstring: "No transfer suggestions are made");
- caps a forecast run at 50 SKUs (`hybrid_forecast.py:175`) and zero-shot
  inference at 500 series (`zero_shot_max_series`). Both are far below one
  multi-branch tenant (~25k SKU series; ~150k SKU×location series);
- stores `location` as free text on `historical_sales` and `inventory_levels`,
  with no location entity, location kind, or lead time between locations;
- has an unused two-echelon safety-stock optimiser
  (`backend/ml/sanket_ml/optimization/multi_echelon.py`) that nothing calls.

Goal: give company A a forecast per (SKU, branch) that is consistent with its
SKU forecast, plus advisory DC→branch allocations and branch↔branch transfers.
Every number must trace back to its inputs, and every gap must be reported
rather than filled in.

## 2. Phases

| Phase | Scope | Ships when |
|---|---|---|
| 0 | Forecast at tenant scale: remove the 50-SKU cap; batch ML calls past the 500-series cap | 25k-SKU run completes within the budget the benchmark harness sets (own plan) |
| 1 | `locations` entity + Network setup | Imports register locations; the network can be confirmed |
| 2 | Location forecasts + location accuracy | Swecha holdout shows location MASE; p50 sum invariant holds |
| 3 | DC→branch allocation decisions | Synthetic DC fixture passes the allocation invariants |
| 4 | Branch↔branch transfer decisions | Transfer invariants pass; coverage's transfer hint is backed by a real decision |
| 5 | Branch-scoped user access | Separate spec — outlined only (§9) |
| Gated | Method C reconciliation; multi-echelon safety stock in `purchase_order` | Each needs its own backtest win (§4.5, §5.1) |

Phases 1–4 depend on Phase 0 for tenants larger than the current caps. They can
be built and tested against the Swecha data (12 SKUs, 2 branches) before Phase 0
lands.

## 3. Locations (Phase 1)

### 3.1 Table `locations`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `tenant_id` | UUID FK tenants, cascade | RLS tenant policy, same pattern as `inventory_levels` |
| `code` | text | `lower(trim(raw))` — the same key `coverage.py` uses (`loc_key`) |
| `name` | text | Display name; first raw spelling seen |
| `kind` | enum `warehouse \| store \| unconfirmed` | Non-native enum, like `DecisionKind` |
| `parent_location_id` | UUID FK locations, nullable | The DC that supplies a store |
| `lead_time_days_from_parent` | smallint, nullable | DC→store replenishment lead time |
| `is_active` | bool, default true | |
| `attributes` | JSONB | Reserved (clusters, capacity) — unused in v1 |

Unique `(tenant_id, code)`. A store's parent must have `kind = warehouse` and
the same tenant (checked in the service layer). There is no multi-level
network: a warehouse has no parent.

### 3.2 Linking existing rows

`historical_sales.location` and `inventory_levels.location` stay as text and
resolve to a `locations` row by `code`. `historical_sales` is partitioned and
has no FKs by design, so it is not migrated to an FK.

Imports (`file_import.py`, the Shopify and WooCommerce sync) upsert any unseen
code as `kind = unconfirmed`. Nothing is inferred from a name ("…Warehouse" is
not assumed to be a DC).

The inventory placeholder `location = 'default'` counts as unassigned, not as a
location.

### 3.3 Readiness rules

- **Location forecasts (Phase 2)** need only resolved location codes on sales.
  Kinds are not required.
- **Allocation (Phase 3)** needs a confirmed network: at least one `warehouse`,
  and every active store with a parent and a `lead_time_days_from_parent`. Until
  then the allocation surface shows the missing items; it never assumes them.
- **Transfers (Phase 4)** need at least two active `store` locations with
  confirmed kinds.
- **Unassigned share:** units on sales whose location is NULL or `default`,
  divided by all units in the share window (§4.1). Above **5%**, every location
  figure for that tenant is flagged `degraded` with the percentage. The figures
  are still computed, but are never presented as complete.

### 3.4 API

- `GET /locations` — list, with kind, parent, lead time, last sale and last
  stock dates.
- `PATCH /locations/{id}` — set kind, name, parent, lead time and is_active.
  Admin/owner roles only.
- Network readiness is exposed on the same response (`network_ready`, plus the
  list of missing items).

## 4. Location forecasts (Phase 2)

Runs as a post-step of `execute_hybrid_run`, after the SKU `ForecastResult`
rows are persisted, in the same run. Run `metrics` gain `location_series`,
`location_excluded`, `unassigned_share` and `degraded`.

### 4.1 Shares

For each (SKU, location) with sales:

- **Window:** the last **12 complete weeks** (`CALENDAR` week buckets), each
  week weighted with an exponential decay of **4-week half-life**.
- **Out-of-stock weeks** (`in_stock = false` at that location) are dropped from
  both numerator and denominator. Lost sales must not shrink a share. Unknown
  `in_stock` (NULL) is kept.
- `s_sku(l)` = weighted units at l ÷ weighted units of the SKU *including*
  unassigned units. The SKU's unassigned share is `u = 1 − Σ_l s_sku(l)`.
- **Shrinkage for sparse SKUs:**
  `s(l) = (n·s_sku(l) + k·s_cat(l)) / (n + k)`, where `n` = effective weighted
  weeks with SKU sales, `k = 4`, and `s_cat(l)` is the same computation over the
  SKU's category. Shares are renormalised to sum to `1 − u`.
  `share_basis = sku_history | blended | category_prior`.
- **New SKU** (no sales in the window): `s = s_cat`, basis `category_prior`.
- **Location with no sales of the category in the window:** excluded, with the
  reason "no sales history at this location". There is no "like store" cloning
  in v1.

### 4.2 Quantiles

Given SKU weekly `p10, p50, p90`:

- `p50_l = s · p50`. **Invariant:** Σ_l p50_l = (1 − u) · p50 (to rounding).
  Unassigned demand is not spread across branches; it is reported via
  `unassigned_share` (and is exactly p50 when `u = 0`).
- `σ = (p90 − p10) / (2 · 1.2816)`;
  `var_l = s² σ² + s(1 − s) · p50` (multinomial thinning);
  `p10_l = max(0, p50_l − 1.2816 √var_l)`, `p90_l = p50_l + 1.2816 √var_l`.
  Location quantiles intentionally do not sum to the SKU quantiles.

### 4.3 Table `location_forecast_results`

Partitioned by `forecast_date` (RANGE), mirroring `forecast_results`. No FKs,
RLS tenant policy.

`id, tenant_id, run_id, sku_id, location_id, forecast_date, p10, p50, p90,
share, share_basis, method, created_at`; `method = 'share_split_v1'`.

It is a separate table because every current reader (`decision_builder`,
`coverage`, `forecast_accuracy`, routers) aggregates `forecast_results` by
`sku_id`; location rows mixed in would be double counted. The SKU forecast stays
authoritative.

### 4.4 Consumers

`coverage.py` location cover switches its demand basis to the fresh location
forecast when one exists. Otherwise it falls back to the location's trailing
actuals, as today. The pooled fallback stays forbidden.

### 4.5 Accuracy and the gate for method C

`forecast_accuracy` adds per-(SKU, location) MASE against a seasonal-naive
forecast at that location. It is reported beside SKU-level MASE and weighted by
location units.

Method C (middle-out + MinT-shrink reconciliation) may be built only after an
offline backtest on the benchmark harness shows:

- location-weighted MASE improves by **≥ 5%** over `share_split_v1`, and
- SKU-level MASE degrades by **≤ 1%**,

on at least the Swecha holdout plus one larger multi-location dataset. It would
write the same table with `method = 'middle_out_mint'`.

## 5. DC→branch allocation (Phase 3)

### 5.1 Purchasing is unchanged

`purchase_order` keeps its pooled computation: SKU forecast against total
position across all locations, which is the DC echelon's view. Replacing its
safety-stock term with `MultiEchelonOptimizer` is gated on a backtest showing
lower total safety stock at equal or better simulated service level. It is not
part of v1.

### 5.2 Algorithm

Allocation is computed per SKU, per DC, on each decision refresh, for stores
whose parent is that DC:

- **Window** `w_l = lead_time_days_from_parent + policy.review_period_days`.
- **Location band:** a `DemandBand` built from `location_forecast_results`, so
  `_window_sum` and `_pooled_sigma` are reused unchanged.
- `target_l = Σ p50_l over w_l + z · σ_l(w_l)`, where z comes from
  `policy.service_level`.
- `position_l = available + inbound` at l; `need_l = max(0, target_l − position_l)`.
- `supply = DC available − DC own demand over its review period`, where DC own
  demand is the DC's location p50 if the DC has sales (e.g. online fulfilment);
  floored at 0.
- **If Σ need ≤ supply:** `alloc_l = need_l`.
- **If Σ need > supply — equal-cover water-filling:** choose the level T (in
  days) such that `alloc_l = clamp(T · d_l − position_l, 0, need_l)` and
  Σ alloc = supply, where `d_l` = daily p50 rate. A store with `d_l = 0`
  receives nothing.
- **Rounding:** to `Sku.moq` (the pack size) by largest remainder.
  **Invariant:** Σ alloc ≤ supply. Lines below `policy.min_allocation_units`
  (default 1) are dropped.
- **Exclusions, each with a reason on the decision surface:** stale stock at the
  DC or the store (`planning_inputs.stock_is_stale`); no location forecast;
  location `degraded`.

Fashion sizes need no special handling: each size is its own SKU, so each
store's size curve comes from its own shares. Keeping a style's full size run
together at a store is out of scope.

### 5.3 Ledger

- `DecisionKind.allocation`.
- `recommendations` gains nullable `location_id` (destination) and
  `source_location_id` (origin), plus the index
  `(tenant_id, kind, source_location_id)`.
- `inputs` freezes the shares, location band, positions, supply and the T level.
- `baseline_units` = "replace last period's sales": units the store sold in the
  last review period, capped by the same supply. The ROI delta stays traceable.
- Money fields follow the existing `_money(value, known)` rule.

## 6. Branch↔branch transfers (Phase 4)

A transfer is suggested only when allocation cannot fix a shortage in time.

**Receiver R qualifies when all of these hold:**

1. the deficit is positive, where deficit =
   `Σ p50_R over w_R − (position_R + alloc_R)`;
2. projected cover at R is shorter than R's `lead_time_days_from_parent`;
3. `policy.transfer_lead_time_days < lead_time_days_from_parent` of R.
   Otherwise the next DC delivery arrives just as fast.

**Donor D qualifies when all of these hold:**

1. excess is positive, where excess = `position_D − Σ p90_D over w_D`. The donor
   keeps enough for its own p90 demand, so it is never put at risk;
2. D has fresh stock data;
3. D is not an allocation or transfer receiver of the same SKU in this cycle
   (no chains).

**Matching:** greedy. Receivers are taken in ascending order of cover; donors in
descending order of excess.

- `qty = min(deficit, excess)`, rounded down to `moq`. A transfer is suggested
  only when `qty ≥ policy.min_transfer_units` (default 2).
- **Value** = `qty × (unit_price − unit_cost) − qty ×
  policy.transfer_cost_per_unit`.
- **If all money inputs are known:** the transfer is suggested only when
  value > 0.
- **If any money input is unknown:** the transfer is still suggested, but the
  money fields are null and it is labelled "transfer cost not known".

The result is a `DecisionKind.transfer` with `source_location_id = D` and
`location_id = R`. `coverage.py`'s `EXCESS_ACTION` hint now points at real
transfer decisions when they exist.

New tenant policy keys (via `load_policy`, with defaults):
`transfer_lead_time_days` (2), `min_transfer_units` (2),
`transfer_cost_per_unit` (unset), `min_allocation_units` (1). A per-route lanes
table is out of scope.

## 7. UI

- **Settings → Network:** a list of locations with kind, parent and lead time
  editors, a readiness checklist, and the unassigned-share warning.
- **Inventory and Forecasts:** a location filter and column. Location cover
  shows its basis (forecast or trailing actuals) and the `degraded` badge.
- **Decisions:** allocation and transfer cards grouped by route
  ("Warehouse → Alwal · 14 lines · 86 units"), each line expandable to its
  inputs. Accept and dismiss work as they do for purchase orders.
- Icons come only from the project icon module (Iconly + lucide split), per
  AGENTS.md.

## 8. Failure behaviour

Every case below either shows a reason or flags a degraded state; none produces
a number made up to fill a gap.

| Condition | Behaviour |
|---|---|
| No sales carry a location | Location features off; Network page explains which column to import |
| Unassigned share > 5% | All location figures flagged `degraded` with the share |
| No confirmed DC / missing parent or lead time | No allocation; the readiness checklist lists what is missing |
| Stale stock at a location | That location is excluded from allocation and transfers, with the reason |
| No location forecast (no fresh run) | No allocation/transfer for that SKU; coverage falls back to trailing actuals |
| Location has no history | Excluded from shares, with the reason |
| Unknown cost or price | Money fields null; units still shown |

## 9. Phase 5 outline — branch-scoped access (separate spec)

Introduce user→location assignments. Store-scoped users see only their
locations' rows, and only decisions where their location is the destination or
origin. Whether this is enforced as an app-level filter or a second RLS
predicate is decided in that spec. It must not weaken the tenant RLS boundary.

## 10. Testing

- **Unit — shares:** decay weights; out-of-stock weeks dropped; shrinkage
  limits (n→0 gives the category share, n≫k gives the SKU share);
  renormalisation; new-SKU prior; exclusion reasons.
- **Unit — quantiles:** Σ p50_l = (1 − u) · p50 (property test); p10_l ≥ 0; a single
  location with s = 1 reproduces the SKU quantiles.
- **Unit — allocation:** surplus case ships exact needs; shortage case equalises
  cover; Σ alloc ≤ supply after rounding (property test); `d_l = 0` gets 0;
  stale exclusions.
- **Unit — transfers:** donor never ends below its p90 target; no SKU has a
  location as both donor and receiver; the lead-time rule; unknown cost leads to
  null money.
- **RLS:** cross-tenant reads/writes denied on `locations` and
  `location_forecast_results`, via the existing tenant-isolation test pattern.
  App code uses `sanket_app`, never a superuser.
- **Integration:**
  - Swecha data (Boduppal, Alwal), training files → holdout: location MASE vs
    location seasonal-naive, recorded in the run metrics.
  - A synthetic fixture with 1 DC and 6 stores (in the test data, not the demo
    seed) for end-to-end allocation and transfers.
- **Performance:** a benchmark of the share split + allocation at 25k SKUs × 6
  locations, added to `backend/benchmarks/`.
- **Migrations:** Alembic, run with `MIGRATION_DATABASE_URL` (postgres
  superuser); creates the partitions for `location_forecast_results` the same
  way `forecast_results` does.

## 11. Out of scope

Write-back to ERP/POS; a lanes table with per-route lead times or costs;
multi-level networks (DC→regional DC→store); pharma batch- or expiry-aware
transfers; end-of-season consolidation; "like store" cloning for new branches;
style-level size-run integrity; branch-scoped access (Phase 5); method C and
multi-echelon safety stock (gated).
