from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from sanket_ml.fusion.hybrid_forecaster import HybridForecaster
from sanket_ml.fusion.trend_scorer import SignalRecord, TrendScorer
from sanket_ml.models.base import ForecastQuantiles


def _signal(kind: str, key: str, score: float, confidence: float = 1.0) -> SignalRecord:
    return SignalRecord(
        source=key.split(":", 1)[0],
        kind=kind,
        series_key=key,
        industry="fashion",
        normalized_score=score,
        confidence=confidence,
        captured_at=datetime(2026, 8, 27, tzinfo=UTC),
    )


def test_trend_contributions_reconcile_to_aggregate_score() -> None:
    signals = [
        _signal("social_buzz", "reddit:r/streetwear", 0.8),
        _signal("search_interest", "google:streetwear", 0.4),
        _signal("economic_indicator", "weather:mumbai:temp_deviation", -0.2),
    ]

    result = TrendScorer().score("fashion", signals)

    contribution_total = sum(row["score_contribution"] for row in result.contributions)
    assert contribution_total == pytest.approx(result.score, abs=1e-4)


def test_forecast_driver_percentages_add_to_reported_median_shift() -> None:
    dates = list(pd.date_range("2026-09-01", periods=2, freq="W"))
    baseline = ForecastQuantiles(
        unique_id=["sku-1", "sku-1"],
        ds=dates,
        p10=np.array([90.0, 90.0]),
        p50=np.array([100.0, 100.0]),
        p90=np.array([110.0, 110.0]),
        model_name="test",
    )
    signals = [
        _signal("social_buzz", "reddit:r/streetwear", 0.8),
        _signal("search_interest", "google:streetwear", 0.4),
        _signal("news_sentiment", "rss:fashion-news", -0.25),
        _signal("economic_indicator", "weather:mumbai:temp_deviation", 0.2),
    ]

    result = HybridForecaster().fuse("fashion", baseline, signals)

    driver_total = sum(row["contribution_pct"] for row in result.explanation["drivers"])
    assert driver_total == pytest.approx(result.explanation["median_shift_pct"], abs=1e-8)
    assert any(row["contribution_pct"] > 0 for row in result.explanation["drivers"])
    assert any(row["contribution_pct"] < 0 for row in result.explanation["drivers"])
