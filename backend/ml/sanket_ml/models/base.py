from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True, slots=True)
class ForecastQuantiles:
    """Probabilistic forecast output."""
    unique_id: list[str]
    ds: list[pd.Timestamp]
    p10: np.ndarray
    p50: np.ndarray
    p90: np.ndarray
    model_name: str

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "unique_id": self.unique_id,
                "ds": self.ds,
                "p10": self.p10,
                "p50": self.p50,
                "p90": self.p90,
                "model_name": self.model_name,
            }
        )


class BaseForecaster(abc.ABC):
    """Common interface for every SANKET forecaster."""

    name: str = "base"
    supports_probabilistic: bool = True
    supports_covariates: bool = False
    requires_gpu: bool = False

    def __init__(self, **kwargs: Any) -> None:
        self.params: dict[str, Any] = dict(kwargs)
        self._fitted: bool = False

    @abc.abstractmethod
    def fit(
        self,
        train: pd.DataFrame,
        static_features: pd.DataFrame | None = None,
    ) -> BaseForecaster:
        """Fit on a long-format panel with columns: unique_id, ds, y (+ exogenous)."""

    @abc.abstractmethod
    def predict(
        self,
        horizon: int,
        future_exog: pd.DataFrame | None = None,
        level: tuple[int, ...] = (10, 50, 90),
    ) -> ForecastQuantiles:
        """Forecast `horizon` periods forward for every series the model knows."""

    @property
    def is_fitted(self) -> bool:
        return self._fitted

    def _require_fitted(self) -> None:
        if not self._fitted:
            raise RuntimeError(f"{self.name}: predict() called before fit()")

    def save(self, path: str) -> None:
        import joblib
        joblib.dump(self, path)

    @classmethod
    def load(cls, path: str) -> BaseForecaster:
        import joblib
        return joblib.load(path)
