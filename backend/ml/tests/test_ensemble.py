from __future__ import annotations

import numpy as np
import pandas as pd

from sanket_ml.models.base import ForecastQuantiles
from sanket_ml.models.ensemble import StackedEnsemble, pinball_loss, weighted_average


def _fc(name: str, p50: list[float]) -> ForecastQuantiles:
    n = len(p50)
    p50_arr = np.array(p50, dtype="float32")
    return ForecastQuantiles(
        unique_id=["S"] * n,
        ds=list(pd.date_range("2024-06-01", periods=n, freq="W")),
        p10=p50_arr * 0.8,
        p50=p50_arr,
        p90=p50_arr * 1.2,
        model_name=name,
    )


def test_pinball_loss_zero_at_perfect_forecast() -> None:
    y = np.array([10.0, 20.0, 30.0])
    assert pinball_loss(y, y, 0.5) == 0.0


def test_weighted_average_recovers_single_model() -> None:
    a = _fc("a", [10, 20, 30])
    out = weighted_average([a], [1.0])
    assert np.allclose(out.p50, [10, 20, 30])


def test_stacked_ensemble_picks_better_model() -> None:
    truth = pd.DataFrame(
        {
            "unique_id": ["S"] * 4,
            "ds": pd.date_range("2024-06-01", periods=4, freq="W"),
            "y": [10.0, 20.0, 30.0, 40.0],
        }
    )
    accurate = _fc("accurate", [10, 20, 30, 40])
    awful = _fc("awful", [1000, 1000, 1000, 1000])
    ens = StackedEnsemble().fit(truth, [accurate, awful])
    assert ens.weights["accurate"] > 0.9
    assert ens.weights["awful"] < 0.1


def test_stacked_ensemble_predict_returns_combined() -> None:
    truth = pd.DataFrame(
        {
            "unique_id": ["S"] * 3,
            "ds": pd.date_range("2024-06-01", periods=3, freq="W"),
            "y": [10.0, 20.0, 30.0],
        }
    )
    a = _fc("a", [10, 20, 30])
    b = _fc("b", [15, 25, 35])
    ens = StackedEnsemble().fit(truth, [a, b])
    out = ens.predict([a, b])
    assert len(out.p50) == 3
    assert out.model_name == "ensemble_weighted"
