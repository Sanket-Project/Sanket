"""Dependency-free baseline forecasters (numpy/pandas only).

The registered ``seasonal_naive`` model depends on ``statsforecast``; these
baselines depend on nothing beyond numpy/pandas so a benchmark — and the
"is the fancy model better than naive?" question — can always be answered, even
in a minimal install. They implement the real ``BaseForecaster`` interface, so
they flow through the production ``walk_forward_backtest`` unchanged.

Point methods:
  * naive          — repeat the last observed value.
  * seasonal_naive — repeat the last full season (period = season_length).
  * moving_average — repeat the mean of the last ``window`` observations.
  * drift          — extrapolate the average period-over-period change.

Intervals are a random-walk band: p50 ± z·σ·√t, where σ is the in-sample
one-step residual std and z≈1.2816 (≈80% interval → p10/p90).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from pandas.tseries.frequencies import to_offset

from sanket_ml.models.base import BaseForecaster, ForecastQuantiles

_Z80 = 1.2816  # standard-normal quantile for the 10th/90th percentile band


class _PanelBaseline(BaseForecaster):
    """Shared fit/predict; subclasses define the point forecast only."""

    name = "baseline"

    def __init__(self, freq: str = "W", season_length: int = 52, window: int = 4, **kw: Any) -> None:
        super().__init__(freq=freq, season_length=season_length, window=window, **kw)
        self._freq = freq
        self._season = season_length
        self._window = window
        self._series: dict[str, np.ndarray] = {}
        self._last_ds: dict[str, pd.Timestamp] = {}
        self._sigma: dict[str, float] = {}

    def fit(self, train: pd.DataFrame, static_features: pd.DataFrame | None = None) -> _PanelBaseline:
        df = train[["unique_id", "ds", "y"]].copy()
        df["ds"] = pd.to_datetime(df["ds"])
        df["unique_id"] = df["unique_id"].astype(str)
        for uid, g in df.sort_values("ds").groupby("unique_id"):
            y = g["y"].to_numpy(dtype="float64")
            self._series[uid] = y
            self._last_ds[uid] = g["ds"].iloc[-1]
            self._sigma[uid] = max(float(np.std(np.diff(y))) if y.size > 1 else 1.0, 1e-6)
        self._fitted = True
        return self

    def _point(self, y: np.ndarray, horizon: int) -> np.ndarray:  # pragma: no cover - abstract
        raise NotImplementedError

    def predict(
        self,
        horizon: int,
        future_exog: pd.DataFrame | None = None,
        level: tuple[int, ...] = (10, 50, 90),
    ) -> ForecastQuantiles:
        self._require_fitted()
        off = to_offset(self._freq)
        uids: list[str] = []
        dss: list[pd.Timestamp] = []
        p10: list[float] = []
        p50: list[float] = []
        p90: list[float] = []
        for uid, y in self._series.items():
            pt = np.clip(self._point(y, horizon), 0.0, None)
            future = pd.date_range(self._last_ds[uid] + off, periods=horizon, freq=self._freq)
            sigma = self._sigma[uid]
            for t in range(horizon):
                m = float(pt[t])
                spread = _Z80 * sigma * np.sqrt(t + 1)
                uids.append(uid)
                dss.append(future[t])
                p50.append(m)
                p10.append(max(m - spread, 0.0))
                p90.append(max(m + spread, m))
        return ForecastQuantiles(
            unique_id=uids,
            ds=dss,
            p10=np.asarray(p10, dtype="float32"),
            p50=np.asarray(p50, dtype="float32"),
            p90=np.asarray(p90, dtype="float32"),
            model_name=self.name,
        )


class NaiveForecaster(_PanelBaseline):
    name = "naive"

    def _point(self, y: np.ndarray, horizon: int) -> np.ndarray:
        return np.full(horizon, y[-1] if y.size else 0.0, dtype="float64")


class SeasonalNaiveForecaster(_PanelBaseline):
    name = "seasonal_naive"

    def _point(self, y: np.ndarray, horizon: int) -> np.ndarray:
        if y.size >= self._season:
            base = y[-self._season :]
            return base[np.arange(horizon) % self._season]
        return np.full(horizon, y[-1] if y.size else 0.0, dtype="float64")


class MovingAverageForecaster(_PanelBaseline):
    name = "moving_average"

    def _point(self, y: np.ndarray, horizon: int) -> np.ndarray:
        w = min(self._window, y.size) or 1
        return np.full(horizon, float(np.mean(y[-w:])) if y.size else 0.0, dtype="float64")


class DriftForecaster(_PanelBaseline):
    name = "drift"

    def _point(self, y: np.ndarray, horizon: int) -> np.ndarray:
        if y.size < 2:
            return np.full(horizon, y[-1] if y.size else 0.0, dtype="float64")
        slope = (y[-1] - y[0]) / (y.size - 1)
        return y[-1] + slope * np.arange(1, horizon + 1)


ALL_BASELINES: dict[str, type[_PanelBaseline]] = {
    "naive": NaiveForecaster,
    "seasonal_naive": SeasonalNaiveForecaster,
    "moving_average": MovingAverageForecaster,
    "drift": DriftForecaster,
}
