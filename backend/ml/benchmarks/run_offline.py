"""Offline forecasting benchmark — runs the REAL backtest, no DB, no heavy deps.

Generates a synthetic demand panel, runs each baseline forecaster through the
production ``walk_forward_backtest`` + ``evaluate``, and prints the
``scoreboard`` — including ``skill_vs_naive`` (WAPE relative to the seasonal-
naive baseline). A model is only worth its complexity if it beats naive here.

Usage:
    cd backend/ml
    python -m benchmarks.run_offline --series 40 --weeks 156 --horizon 13 --folds 4

Optionally include the real LightGBM model when its deps are installed:
    python -m benchmarks.run_offline --with-lightgbm

This benchmarks the *measurement framework and naive comparison* on synthetic
data — it is not a claim about production accuracy. Run the full model zoo on
real tenant data with ``python -m scripts.benchmark <tenant_id> <industry>``.
"""

from __future__ import annotations

import argparse

import pandas as pd

from benchmarks.baselines import ALL_BASELINES
from benchmarks.synthetic import make_demand_panel
from sanket_ml.training.backtest import scoreboard, walk_forward_backtest

pd.set_option("display.width", 160)
pd.set_option("display.max_columns", 20)


def _factory(cls, freq: str, season: int):
    def _make():
        return cls(freq=freq, season_length=season)
    return _make


def run(series: int, weeks: int, horizon: int, folds: int, season: int, seed: int,
        with_lightgbm: bool, csv: str | None) -> int:
    panel = make_demand_panel(n_series=series, weeks=weeks, season=season, seed=seed)
    n_obs = len(panel)
    n_uid = panel["unique_id"].nunique()
    print(f"\nSynthetic panel: {n_uid} series x {weeks} weeks = {n_obs:,} rows")
    print(f"Backtest: {folds} walk-forward folds, horizon = {horizon} weeks\n")

    all_results = []
    factories: dict[str, object] = {
        name: _factory(cls, "W", season) for name, cls in ALL_BASELINES.items()
    }

    if with_lightgbm:
        try:
            from sanket_ml.registry import get as registry_get

            spec = registry_get("lightgbm")
            factories["lightgbm"] = lambda: spec.factory(horizon=horizon, freq="W")
            print("Including registered model: lightgbm")
        except Exception as exc:
            print(f"(lightgbm unavailable — skipping: {exc})")

    for name, factory in factories.items():
        try:
            res = walk_forward_backtest(
                panel, factory, horizon=horizon, n_splits=folds, freq="W"
            )
            all_results.extend(res)
        except Exception as exc:
            print(f"  model {name} failed: {exc}")

    board = scoreboard(all_results, baseline_model="seasonal_naive")
    if board.empty:
        print("No results — check horizon/folds vs panel length.")
        return 1

    show = board.copy()
    for c in ("wape", "mape", "mase", "rmse", "pinball_p50", "coverage_80", "skill_vs_naive"):
        if c in show:
            show[c] = show[c].round(3)
    print("Scoreboard (sorted by WAPE; skill_vs_naive > 1 beats seasonal-naive):\n")
    print(show.to_string(index=False))
    print()

    if csv:
        board.to_csv(csv, index=False)
        print(f"Wrote {csv}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", type=int, default=40)
    ap.add_argument("--weeks", type=int, default=156)
    ap.add_argument("--horizon", type=int, default=13)
    ap.add_argument("--folds", type=int, default=4)
    ap.add_argument("--season", type=int, default=52)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--with-lightgbm", action="store_true")
    ap.add_argument("--csv", type=str, default=None)
    a = ap.parse_args()
    raise SystemExit(
        run(a.series, a.weeks, a.horizon, a.folds, a.season, a.seed, a.with_lightgbm, a.csv)
    )
