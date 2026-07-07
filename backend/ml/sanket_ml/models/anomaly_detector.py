"""Sales anomaly detection using STL decomposition + Isolation Forest.

Detects demand shocks (spikes/dips) in weekly sales series that cannot be
explained by trend or seasonality.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import structlog

log = structlog.get_logger(__name__)


@dataclass
class AnomalyRow:
    ds: str
    y: float
    is_anomaly: bool
    anomaly_score: float   # higher = more anomalous (0-1 range, 1 = most anomalous)
    residual: float


class SalesAnomalyDetector:
    """STL + IsolationForest anomaly detector for weekly sales series."""

    def __init__(self, contamination: float = 0.05, seasonal_period: int = 52) -> None:
        self.contamination = contamination
        self.seasonal_period = seasonal_period

    def detect(self, series: pd.Series, freq: str = "W") -> list[AnomalyRow]:
        """
        series: pd.Series with DatetimeIndex and float values (weekly units sold).
        Returns list of AnomalyRow — all points, with is_anomaly flagged.
        """
        if len(series) < 2 * self.seasonal_period:
            # Not enough data for full STL; fall back to simple z-score
            return self._zscore_detect(series)

        try:
            from statsmodels.tsa.seasonal import STL
            stl = STL(series, period=self.seasonal_period, robust=True)
            result = stl.fit()
            residuals = result.resid.values
        except Exception as exc:
            log.warning("anomaly.stl.failed", error=str(exc))
            return self._zscore_detect(series)

        return self._isolation_forest(series, residuals)

    def _isolation_forest(self, series: pd.Series, residuals: np.ndarray) -> list[AnomalyRow]:
        try:
            from sklearn.ensemble import IsolationForest
            X = residuals.reshape(-1, 1)
            iso = IsolationForest(contamination=self.contamination, random_state=42)
            labels = iso.fit_predict(X)
            scores = iso.decision_function(X)
            # Normalise scores to [0, 1] where 1 = most anomalous
            norm_scores = 1 - (scores - scores.min()) / (scores.ptp() + 1e-9)

            rows: list[AnomalyRow] = []
            for i, (idx, val) in enumerate(series.items()):
                rows.append(AnomalyRow(
                    ds=str(idx)[:10] if hasattr(idx, "strftime") else str(idx),
                    y=float(val),
                    is_anomaly=bool(labels[i] == -1),
                    anomaly_score=round(float(norm_scores[i]), 4),
                    residual=round(float(residuals[i]), 4),
                ))
            return rows
        except Exception as exc:
            log.warning("anomaly.iforest.failed", error=str(exc))
            return self._zscore_detect(series)

    def _zscore_detect(self, series: pd.Series) -> list[AnomalyRow]:
        values = series.values.astype(float)
        mean, std = values.mean(), values.std()
        if std == 0:
            std = 1.0
        z_scores = (values - mean) / std
        threshold = 2.5
        rows: list[AnomalyRow] = []
        for i, (idx, val) in enumerate(series.items()):
            z = abs(float(z_scores[i]))
            score = min(1.0, z / (threshold * 2))
            rows.append(AnomalyRow(
                ds=str(idx)[:10] if hasattr(idx, "strftime") else str(idx),
                y=float(val),
                is_anomaly=z > threshold,
                anomaly_score=round(score, 4),
                residual=round(float(z_scores[i]), 4),
            ))
        return rows
