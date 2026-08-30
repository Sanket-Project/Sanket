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


def _explanation_drivers(
    trend: TrendScore,
    *,
    alpha: float,
    median_shift_pct: float,
    max_named_drivers: int = 5,
) -> list[dict]:
    """Convert trend-score attribution into additive forecast percentages.

    The top named rows plus an optional ``other`` row always reconcile to the
    rounded median shift returned to the client.  Positive and negative rows
    are deliberately retained so planners can see offsetting evidence.
    """
    rows = [
        {
            "source": str(item.get("source", "unknown")),
            "kind": str(item.get("kind", "unknown")),
            "series_key": str(item.get("series_key", "unknown")),
            "contribution_pct": alpha * float(item.get("score_contribution", 0.0)),
            "signal_score": float(item.get("signal_score", 0.0)),
        }
        for item in trend.contributions
        if abs(float(item.get("score_contribution", 0.0))) > 1e-12
    ]
    rows.sort(key=lambda item: abs(item["contribution_pct"]), reverse=True)

    named = rows[:max_named_drivers]
    remainder = rows[max_named_drivers:]
    if remainder:
        named.append(
            {
                "source": "multiple",
                "kind": "other",
                "series_key": "other:signals",
                "contribution_pct": sum(item["contribution_pct"] for item in remainder),
                "signal_score": 0.0,
            }
        )

    for item in named:
        item["contribution_pct"] = round(item["contribution_pct"], 4)

    # QuantileAdjuster reports a rounded net shift. Reconcile any tiny rounding
    # difference into the largest driver so displayed percentages add exactly.
    if named:
        displayed_total = round(sum(item["contribution_pct"] for item in named), 4)
        delta = round(median_shift_pct - displayed_total, 4)
        named[0]["contribution_pct"] = round(named[0]["contribution_pct"] + delta, 4)

    return named


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
        explanation["drivers"] = _explanation_drivers(
            trend,
            alpha=params.alpha,
            median_shift_pct=explanation["median_shift_pct"],
        )
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
