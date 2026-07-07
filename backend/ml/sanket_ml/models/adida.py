"""ADIDA — Aggregate-Disaggregate Intermittent Demand Approach.

For slow-moving / intermittent SKUs (zero fraction > 50%), aggregates the
series to non-zero periods, applies exponential smoothing, then disaggregates
back. Falls back to Croston's method when statsforecast is unavailable.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import structlog

log = structlog.get_logger(__name__)

INTERMITTENCY_THRESHOLD = 0.50   # zero-fraction above this → use ADIDA


@dataclass
class ADIDAForecast:
    sku_id: str
    p10: list[float]
    p50: list[float]
    p90: list[float]
    is_intermittent: bool
    zero_fraction: float


class ADIDAForecaster:
    """ADIDA intermittent demand forecaster."""

    def __init__(self, horizon: int = 26, alpha: float = 0.3) -> None:
        self.horizon = horizon
        self.alpha = alpha

    def forecast(self, sku_id: str, series: pd.Series) -> ADIDAForecast:
        values = series.dropna().values.astype(float)
        zero_frac = float((values == 0).mean()) if len(values) > 0 else 1.0
        is_intermittent = zero_frac > INTERMITTENCY_THRESHOLD

        if is_intermittent:
            p50 = self._adida_point(values)
        else:
            p50 = self._exp_smooth(values)

        # Approximate prediction intervals using Poisson assumption for low-count demand
        mu = max(p50, 0.01)
        sigma = max(np.sqrt(mu), 0.5)
        p10 = [max(0.0, round(mu - 1.28 * sigma, 2))] * self.horizon
        p90 = [round(mu + 1.28 * sigma, 2)] * self.horizon
        p50_list = [round(mu, 2)] * self.horizon

        return ADIDAForecast(
            sku_id=sku_id,
            p10=p10,
            p50=p50_list,
            p90=p90,
            is_intermittent=is_intermittent,
            zero_fraction=round(zero_frac, 4),
        )

    def _adida_point(self, values: np.ndarray) -> float:
        """Aggregate non-zero periods, smooth, disaggregate."""
        non_zero = values[values > 0]
        if len(non_zero) == 0:
            return 0.0
        # Demand size estimate via exponential smoothing on non-zero demand
        size_est = self._exp_smooth_values(non_zero)
        # Demand interval estimate via exponential smoothing on inter-arrival times
        arrivals = np.where(values > 0)[0]
        if len(arrivals) < 2:
            interval_est = len(values)
        else:
            intervals = np.diff(arrivals).astype(float)
            interval_est = self._exp_smooth_values(intervals)
        return size_est / max(interval_est, 1.0)

    def _exp_smooth_values(self, values: np.ndarray) -> float:
        level = float(values[0])
        for v in values[1:]:
            level = self.alpha * float(v) + (1 - self.alpha) * level
        return level

    def _exp_smooth(self, values: np.ndarray) -> float:
        if len(values) == 0:
            return 0.0
        return self._exp_smooth_values(values)
