"""End-to-end hybrid forecaster.

Combines:
    - a `ForecastQuantiles` produced by the existing historical ML stack
      (LightGBM / TFT / Chronos / Stacked ensemble — Phase 2)
    - a list of `SignalRecord` from the trend ingestion pipeline (Phase 6)

Produces:
    - adjusted `ForecastQuantiles` (the same shape downstream consumers expect)
    - a `TrendScore` snapshot used for the adjustment
    - named scenarios (Pessimistic/Base/Optimistic) for the dashboard
    - an explanation dict (median shift %, band widening %)

This class deliberately does NOT train or call any model — it operates on
pre-computed quantiles. That keeps inference fast (< 50 ms) and decoupled
from the heavy ML stack.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from sanket_ml.fusion.quantile_adjuster import AdjustmentParams, QuantileAdjuster
from sanket_ml.fusion.scenario_engine import Scenario, ScenarioEngine
from sanket_ml.fusion.trend_scorer import SignalRecord, TrendScore, TrendScorer
from sanket_ml.models.base import ForecastQuantiles


@dataclass(slots=True)
class HybridForecastOutput:
    industry: str
    baseline: ForecastQuantiles
    adjusted: ForecastQuantiles
    trend: TrendScore
    scenarios: dict[str, Scenario]
    params: AdjustmentParams
    explanation: dict
    generated_at: datetime


class HybridForecaster:
    def __init__(
        self,
        scorer: TrendScorer | None = None,
        adjuster: QuantileAdjuster | None = None,
    ):
        self.scorer = scorer or TrendScorer()
        self.adjuster = adjuster or QuantileAdjuster()

    def fuse(
        self,
        industry: str,
        baseline: ForecastQuantiles,
        signals: Iterable[SignalRecord],
        as_of: datetime | None = None,
        horizon_days: int = 90,
    ) -> HybridForecastOutput:
        trend = self.scorer.score(
            industry=industry,
            signals=signals,
            as_of=as_of,
            horizon_days=horizon_days,
        )
        params = AdjustmentParams.for_industry(industry)
        # Bind params for this single call (don't mutate self.adjuster.params
        # because the adjuster instance is shared across requests).
        adjuster = QuantileAdjuster(params=params)
        adjusted = adjuster.adjust(
            baseline=baseline,
            trend_score=trend.score,
            signal_volatility=trend.volatility,
            industry=industry,
        )
        scenarios = ScenarioEngine.build(adjusted, trend, industry)
        explanation = QuantileAdjuster.explain(baseline, adjusted)
        return HybridForecastOutput(
            industry=industry,
            baseline=baseline,
            adjusted=adjusted,
            trend=trend,
            scenarios=scenarios,
            params=params,
            explanation=explanation,
            generated_at=datetime.utcnow(),
        )
