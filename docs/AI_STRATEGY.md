# SANKET — AI & Forecasting Strategy

**Author:** Chief AI Officer
**Date:** 2026-06-15
**Deliverables:** architecture, implementation, benchmarks, ROI impact, roadmap,
and the competitive moat — grounded in the actual ML codebase.

> **Honesty note.** SANKET's ML stack is **far more mature than a greenfield**, so
> this is mostly "sharpen and close gaps," not "build." Where I say something
> exists I have read the code. The benchmark numbers in §3 are **real** (run
> offline on synthetic demand to validate the *measurement framework and the
> naive comparison*) — they are explicitly **not** a claim about production
> accuracy, which requires running the full model zoo on real tenant data. ROI in
> §6 is a transparent **model with stated assumptions**, not a measured figure.

---

## 1. Current-state architecture (what already exists)

This is a serious forecasting platform. Verified in `backend/ml/sanket_ml/`:

- **Model zoo (11 models)** across four families: statistical (`seasonal_naive`,
  `croston`, `ets`, `adida`), gradient-boost (`lightgbm`), deep (`tft`, `deepar`,
  `nhits`), foundation (`chronos`, `timesfm`, `moirai`, `lag_llama`) —
  [`registry.py`](../backend/ml/sanket_ml/registry.py), with per-industry default
  stacks.
- **Stacked ensemble** that learns convex weights by **minimizing pinball loss**
  on a validation set via SLSQP — [`models/ensemble.py`](../backend/ml/sanket_ml/models/ensemble.py).
  This is a genuine probabilistic stacker, not a mean blend.
- **Walk-forward backtesting** with a full metric suite (WAPE/MAPE/sMAPE/RMSE,
  pinball at p10/p50/p90, interval coverage) — [`training/backtest.py`](../backend/ml/sanket_ml/training/backtest.py).
- **Drift monitoring** with PSI, KL, KS, and Wasserstein plus severity banding and
  prediction drift — [`monitoring/drift.py`](../backend/ml/sanket_ml/monitoring/drift.py).
- **Serving** with a Chronos zero-shot cold-start fallback, admission-control
  throttling, and persisted runs — [`inference/`](../backend/ml/sanket_ml/inference/).
- **Intelligence layer**: trend fusion (`fusion/trend_scorer.py`,
  `fusion/hybrid_forecaster.py`, `fusion/scenario_engine.py`), shortage detection
  (`alerts/shortage_detector.py`), causal inference + uplift (`causal/`), and
  supply-chain optimization (`optimization/`: EOQ, multi-echelon, replenishment,
  markdown, RL replenishment).
- **Demand-censoring correction** (`data/censoring.py`) — unconstrains stockout-
  driven zeros so models learn true demand, applied consistently in training and
  serving. This is a sophisticated capability most competitors lack.

The lifecycle diagram is in the chat. **The honest gaps** are: the backtest didn't
report a naive-skill score (fixed this pass), the **retrain loop isn't closed**
(drift detects but doesn't trigger retraining), **model governance** (versioned
artifacts, model cards, promotion gates) is thin, **interval calibration** drifts
(see §3), and **ERP integrations beyond Shopify are absent**.

---

## 2. What I implemented this pass

Focused, verifiable forecasting-science work that directly serves "benchmark all
models / compare against naive baselines / improve accuracy":

1. **MASE + skill-vs-naive scoreboard** in the production backtest
   ([`training/backtest.py`](../backend/ml/sanket_ml/training/backtest.py)):
   `evaluate()` now reports MASE, and a new `scoreboard()` aggregates across folds
   and computes `skill_vs_naive` (baseline WAPE / model WAPE) + `beats_naive`.
   **A model is now provably "worth its complexity" only if it beats naive on this
   table** — the single most important guardrail a forecasting platform can have.
2. **Fixed a real MASE bug** in both `backtest.py` and
   [`monitoring/metrics.py`](../backend/ml/sanket_ml/monitoring/metrics.py): the
   scale used `np.diff(y, n=season)` — the *season-th order derivative*, not the
   *lag-season seasonal difference*. The corrected scale is `mean|y_t − y_{t−s}|`.
   The old code silently produced meaningless MASE values.
3. **Offline, dependency-free benchmark harness**
   ([`backend/ml/benchmarks/`](../backend/ml/benchmarks/)): synthetic-but-realistic
   demand archetypes (seasonal, trending, intermittent, promo-spiky) + numpy-only
   baselines run through the **real** `walk_forward_backtest`. Runs with no live DB
   and no torch/statsforecast — so the accuracy framework is now reproducible and
   CI-able. Tests in [`tests/test_backtest_skill.py`](../backend/ml/tests/test_backtest_skill.py) (5 passing).

---

## 3. Benchmarks (real, offline)

`python -m benchmarks.run_offline --series 40 --weeks 156 --horizon 13 --folds 4`
(40 series × 156 weeks, 4 walk-forward folds):

| model | WAPE | MASE | coverage₈₀ | skill_vs_naive | beats naive |
|-------|------|------|-----------|----------------|-------------|
| seasonal_naive | **22.57** | **0.331** | 0.951 | 1.00 (baseline) | — |
| naive | 25.41 | 0.372 | 0.930 | 0.888 | no |
| drift | 25.98 | 0.380 | 0.926 | 0.869 | no |
| moving_average | 26.79 | 0.393 | 0.928 | 0.842 | no |

**What this proves (and what it doesn't):**
- The measurement framework and the naive comparison work end-to-end. On seasonal
  demand, **seasonal-naive beats plain-naive by ~11%** — the expected result, and a
  sanity check that the scoreboard is correct.
- **Calibration finding (real):** coverage is **0.93–0.95 against an 80% nominal**
  interval → the bands are **over-wide**. This is a concrete, fixable accuracy
  opportunity (conformal calibration — §4).
- **MAPE is unusable on intermittent demand** (it blew up to ~1e11 because of
  near-zero denominators) — which is *why* WAPE/MASE are the headline metrics. Real
  insight, not a bug.
- These are *baselines on synthetic data*. The whole point is that any "smart"
  model (LightGBM/TFT/Chronos/ensemble) must now clear `skill_vs_naive > 1` on real
  tenant data via `python -m scripts.benchmark <tenant_id> <industry>` before it
  ships. **No fabricated accuracy claims.**

---

## 4. Forecasting & MLOps roadmap

### Forecasting accuracy
- **Conformal interval calibration (P0).** The coverage finding above is a quick,
  high-value win: wrap forecasts in split-conformal prediction so p10/p90 hit
  nominal coverage per series. Improves decision quality (safety stock, service
  levels) immediately.
- **Per-series model selection via the meta-learner** (`models/meta_learner.py`
  exists) — route intermittent SKUs to Croston/ADIDA, seasonal to the ensemble,
  cold-start to Chronos — gated by the new skill-vs-naive score.
- **Hierarchical reconciliation** (SKU → category → region coherence) — a known gap
  that enterprises with planning hierarchies require.

### MLOps
- **Close the retrain loop (P0/P1).** Drift detection exists; wire
  `monitoring/drift` → a retrain trigger (the diagram's accented box) → backtest
  gate → promotion. **Champion-challenger**: a new model is promoted only if it
  beats the incumbent *and* naive on the holdout.
- **Model governance (P1).** Turn the registry into a governed artifact store:
  immutable versioned artifacts, **model cards** (training data window, metrics,
  intended use, owner), approval gates, and lineage — feeds the SOC2/Part 11 story
  in [`SECURITY_AND_COMPLIANCE_REVIEW.md`](SECURITY_AND_COMPLIANCE_REVIEW.md).
- **Decision-regret monitoring (differentiator, §7).**

---

## 5. Integrations: ERP connector framework (greenfield)

Only Shopify exists (`app/services/integrations/`). SAP, Oracle, NetSuite, and
Microsoft Dynamics are **absent** and are the largest greenfield item.

**Design:** a single `ErpConnector` abstraction (auth, incremental sales/inventory
pull, master-data sync, webhook/delta ingestion) with per-system adapters, reusing
the existing poller + replay-protection + idempotency machinery:

- **SAP** — OData/S4HANA APIs (or IDoc/BAPI via middleware); sales orders + stock.
- **Oracle** — Fusion SCM / NetSuite REST (SuiteQL).
- **NetSuite** — SuiteTalk REST + SuiteQL.
- **Dynamics 365** — Dataverse / Supply Chain Management OData.

All four normalize into the existing `historical_sales` / `inventory_levels`
schema, so the entire forecasting stack works unchanged. Sequence by deal demand;
each connector is ~2–4 weeks. This is integration engineering, not research.

---

## 6. ROI impact (transparent model)

Demand-forecasting ROI is dominated by **inventory carrying cost** and **lost
sales from stockouts**. A defensible model:

```
annual_savings ≈ inventory_value × carrying_rate × inventory_reduction
               + revenue × stockout_rate × margin × stockout_reduction
```

Illustrative mid-market retailer — **assumptions stated, not measured:**
`inventory_value = $20M`, `carrying_rate = 25%`, `revenue = $100M`, `margin = 30%`,
baseline `stockout_rate = 5%`.

- A forecast-accuracy gain that enables a **10% inventory reduction** →
  `$20M × 0.25 × 0.10 = $500K/yr`.
- A **20% stockout reduction** → `$100M × 0.05 × 0.30 × 0.20 = $600K/yr`.
- **≈ $1.1M/yr** per such tenant, before markdown/expediting savings.

The mechanism that converts accuracy → dollars is **better-calibrated quantiles**
(§4 conformal work) feeding the **newsvendor/EOQ optimizers that already exist**
(`optimization/`). The honest framing for buyers: *we will prove the inventory and
service-level deltas on your data during a backtest pilot* — the platform is built
to measure exactly that (§2–3).

---

## 7. Competitive moat — features rivals don't have

The defensible differentiators are the **combinations already in the codebase**,
plus three net-new:

**Already a moat (sharpen + market):**
1. **Censored-demand correction** (`data/censoring.py`) — forecasting *true* demand
   through stockouts, applied identically in train and serve. Most tools forecast
   sales (censored) and quietly under-order the next cycle.
2. **Causal + uplift-aware forecasting** (`causal/`) — promo/price uplift modeled
   causally (DoWhy), not as a correlational feature.
3. **Decision-grade probabilistic output → optimization** — full p10/p50/p90 piped
   into newsvendor/multi-echelon/markdown optimizers (`optimization/`), not point
   forecasts thrown over the wall.
4. **Multi-industry transfer** — one platform tuned across fashion/electronics/
   pharma/agro/hardware with industry stacks and a foundation-model cold start.

**Net-new (propose to build):**
5. **Skill-gated auto-promotion** — *no model reaches production unless it beats
   naive on the customer's own data* (built this pass; productionize as a gate).
   A trust feature competitors can't easily claim.
6. **Decision-regret monitoring** — track realized cost of forecast error vs the
   ex-post optimal order, per SKU, and surface it. Moves the conversation from
   "MAPE" to "dollars left on the table."
7. **Conformal service-level guarantees** — per-SKU calibrated intervals that let a
   planner *dial a service level* and trust the resulting safety stock.

---

## 8. Sequenced roadmap

| Phase | Items | Outcome |
|-------|-------|---------|
| **P0 (0–4 wk)** | Conformal calibration; skill-gated promotion; close drift→retrain trigger | Better calibration + a trust guardrail, both measurable |
| **P1 (1–3 mo)** | Champion-challenger; model governance + cards; meta-learner routing; hierarchical reconciliation | Governed, self-improving model ops |
| **P2 (2–4 mo)** | SAP + NetSuite connectors (deal-driven); decision-regret monitoring | Enterprise data reach + dollar-framed value |
| **P3 (4–6 mo)** | Oracle + Dynamics; conformal service-level UX | Full ERP coverage + planner-facing moat |

---

## 9. How to reproduce

```bash
cd backend/ml
python -m benchmarks.run_offline --series 40 --weeks 156 --horizon 13 --folds 4
python -m pytest tests/test_backtest_skill.py -q
# Full zoo on real data (needs deps + a seeded tenant):
python -m scripts.benchmark <tenant_id> <industry>
```
