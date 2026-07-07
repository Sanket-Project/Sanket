"""Adjust historical P10/P50/P90 quantiles using a trend score + volatility.

Core formula:
    P50' = P50 × (1 + α × trend_score)
    P10' = P10 × (1 + β × (trend_score − vol_expand))
    P90' = P90 × (1 + β × (trend_score + vol_expand))

Where:
    α   = trend sensitivity for the median (per-industry, default 0.15)
    β   = trend sensitivity for the band edges (≥ α, default 0.20)
    vol_expand = volatility × volatility_expansion_factor
                 (widens band when sources disagree)

Constraints:
    P10' ≤ P50' ≤ P90' is enforced post-adjustment.
    All values clipped to ≥ 0 since demand cannot be negative.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from sanket_ml.models.base import ForecastQuantiles

# Per-industry default sensitivities. The fashion median is the most responsive
# because trend-driven demand shifts are largest there; pharma is conservative
# because clinical demand changes slowly even under economic stress.
DEFAULT_INDUSTRY_PARAMS: dict[str, dict[str, float]] = {
    "fashion":     {"alpha": 0.22, "beta": 0.30, "vol_expand": 0.45},
    "electronics": {"alpha": 0.15, "beta": 0.22, "vol_expand": 0.35},
    "pharma":      {"alpha": 0.08, "beta": 0.15, "vol_expand": 0.25},
}


@dataclass(slots=True)
class AdjustmentParams:
    alpha: float
    beta: float
    vol_expand_factor: float

    @classmethod
    def for_industry(cls, industry: str) -> AdjustmentParams:
        p = DEFAULT_INDUSTRY_PARAMS.get(industry, DEFAULT_INDUSTRY_PARAMS["electronics"])
        return cls(
            alpha=p["alpha"],
            beta=p["beta"],
            vol_expand_factor=p["vol_expand"],
        )


class QuantileAdjuster:
    def __init__(self, params: AdjustmentParams | None = None):
        self.params = params

    def adjust(
        self,
        baseline: ForecastQuantiles,
        trend_score: float,
        signal_volatility: float,
        industry: str | None = None,
    ) -> ForecastQuantiles:
        p = self.params or (
            AdjustmentParams.for_industry(industry) if industry
            else AdjustmentParams(alpha=0.15, beta=0.20, vol_expand_factor=0.35)
        )

        # Clamp inputs
        ts = max(-1.0, min(1.0, float(trend_score)))
        vol = max(0.0, min(1.0, float(signal_volatility)))
        vol_expand = vol * p.vol_expand_factor

        p50 = baseline.p50.astype(float) * (1.0 + p.alpha * ts)
        p10 = baseline.p10.astype(float) * (1.0 + p.beta * (ts - vol_expand))
        p90 = baseline.p90.astype(float) * (1.0 + p.beta * (ts + vol_expand))

        # Enforce ordering + non-negativity
        p10 = np.clip(p10, a_min=0.0, a_max=None)
        p50 = np.clip(p50, a_min=0.0, a_max=None)
        p90 = np.clip(p90, a_min=0.0, a_max=None)
        p10 = np.minimum(p10, p50)
        p90 = np.maximum(p90, p50)

        return ForecastQuantiles(
            unique_id=list(baseline.unique_id),
            ds=list(baseline.ds),
            p10=p10,
            p50=p50,
            p90=p90,
            model_name=f"{baseline.model_name}+trend_fusion",
        )

    @staticmethod
    def explain(
        baseline: ForecastQuantiles,
        adjusted: ForecastQuantiles,
    ) -> dict:
        """Return summary statistics on how the adjustment changed the bands."""
        b50 = baseline.p50.mean()
        a50 = adjusted.p50.mean()
        median_shift_pct = float((a50 - b50) / max(b50, 1e-9))
        baseline_band = float((baseline.p90 - baseline.p10).mean())
        adjusted_band = float((adjusted.p90 - adjusted.p10).mean())
        band_change_pct = float((adjusted_band - baseline_band) / max(baseline_band, 1e-9))
        return {
            "median_shift_pct": round(median_shift_pct, 4),
            "band_change_pct": round(band_change_pct, 4),
            "baseline_band_mean": round(baseline_band, 4),
            "adjusted_band_mean": round(adjusted_band, 4),
        }
