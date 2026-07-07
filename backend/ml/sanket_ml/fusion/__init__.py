"""Trend signal fusion layer.

Takes a historical-only `ForecastQuantiles` (p10/p50/p90) and adjusts it
using live external market signals — economic indicators, search momentum,
social buzz — producing trend-aware probabilistic forecasts with named
scenarios.

Public API:
    TrendScorer        — aggregates raw signals to a single (score, volatility) tuple
    QuantileAdjuster   — applies the score+volatility to a ForecastQuantiles
    HybridForecaster   — end-to-end fuse(history → quantiles, signals → adjusted quantiles)
    ScenarioEngine     — wraps quantiles into named Pessimistic/Base/Optimistic scenarios

These are pure-Python utilities. They take pre-computed forecasts and signals;
they don't talk to the database or trigger training.
"""
from __future__ import annotations

# TrendScorer is pure-Python (no heavy deps) — always available.
from sanket_ml.fusion.trend_scorer import SignalRecord, TrendScore, TrendScorer

__all__ = [
    "HybridForecaster",
    "HybridForecastOutput",
    "QuantileAdjuster",
    "Scenario",
    "ScenarioEngine",
    "SignalRecord",
    "TrendScore",
    "TrendScorer",
]


def __getattr__(name: str):  # noqa: N807
    """Lazy-load heavy fusion components only when explicitly requested.

    HybridForecaster / QuantileAdjuster / ScenarioEngine depend on pandas,
    numpy, and scikit-learn which are only installed in the ML training venv,
    not in the backend API venv.  Importing this package from the backend
    (which only needs TrendScorer) will therefore not fail.
    """
    _heavy = {
        "HybridForecaster": ("sanket_ml.fusion.hybrid_forecaster", "HybridForecaster"),
        "HybridForecastOutput": ("sanket_ml.fusion.hybrid_forecaster", "HybridForecastOutput"),
        "QuantileAdjuster": ("sanket_ml.fusion.quantile_adjuster", "QuantileAdjuster"),
        "Scenario": ("sanket_ml.fusion.scenario_engine", "Scenario"),
        "ScenarioEngine": ("sanket_ml.fusion.scenario_engine", "ScenarioEngine"),
    }
    if name in _heavy:
        module_path, attr = _heavy[name]
        import importlib
        mod = importlib.import_module(module_path)
        return getattr(mod, attr)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

