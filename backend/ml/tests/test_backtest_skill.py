"""Tests for MASE and the skill-vs-naive scoreboard added to the backtest."""

from __future__ import annotations

import numpy as np

from sanket_ml.models.base import ForecastQuantiles
from sanket_ml.training.backtest import BacktestMetrics, evaluate, scoreboard


def _fc(values, model_name="m"):
    arr = np.asarray(values, dtype="float32")
    n = len(arr)
    return ForecastQuantiles(
        unique_id=[str(i) for i in range(n)],
        ds=list(range(n)),
        p10=arr - 1,
        p50=arr,
        p90=arr + 1,
        model_name=model_name,
    )


def test_mase_self_scaled_lag_difference():
    # y = 0..9 (size 10 < default season 52 -> lag-1). |y_t - y_{t-1}| = 1 -> scale 1.
    yt = np.arange(10, dtype="float64")
    m = evaluate(yt, _fc(yt + 2.0))  # constant error of 2 -> MAE 2 -> MASE 2.0
    assert abs(m.mase - 2.0) < 1e-9


def test_mase_with_supplied_naive_scale():
    yt = np.arange(10, dtype="float64")
    m = evaluate(yt, _fc(yt + 2.0), naive_scale=4.0)  # MAE 2 / 4 -> 0.5
    assert abs(m.mase - 0.5) < 1e-9


def test_perfect_forecast_has_zero_error():
    yt = np.arange(10, dtype="float64")
    m = evaluate(yt, _fc(yt))
    assert m.wape == 0.0 and m.mase == 0.0


def _metric(model, wape):
    return BacktestMetrics(
        model_name=model, fold=1, mape=0, smape=0, wape=wape, rmse=0,
        pinball_p10=0, pinball_p50=0, pinball_p90=0, coverage_80=0, n_obs=10, mase=0,
    )


def test_scoreboard_skill_vs_naive():
    results = [
        _metric("seasonal_naive", 30.0),
        _metric("good_model", 20.0),
        _metric("bad_model", 45.0),
    ]
    board = scoreboard(results, baseline_model="seasonal_naive")
    by = {r["model"]: r for _, r in board.iterrows()}

    # good_model cuts WAPE from 30 -> 20: skill = 30/20 = 1.5, beats naive.
    assert abs(by["good_model"]["skill_vs_naive"] - 1.5) < 1e-9
    assert bool(by["good_model"]["beats_naive"]) is True
    # bad_model is worse than naive.
    assert by["bad_model"]["skill_vs_naive"] < 1.0
    assert bool(by["bad_model"]["beats_naive"]) is False
    # sorted by WAPE ascending -> good_model first.
    assert board.iloc[0]["model"] == "good_model"


def test_scoreboard_missing_baseline_is_graceful():
    board = scoreboard([_metric("only_model", 10.0)], baseline_model="seasonal_naive")
    assert np.isnan(board.iloc[0]["skill_vs_naive"])  # baseline absent -> NaN, no crash
