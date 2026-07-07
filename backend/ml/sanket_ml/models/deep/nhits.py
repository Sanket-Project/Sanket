from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from neuralforecast import NeuralForecast
from neuralforecast.losses.pytorch import MQLoss
from neuralforecast.models import NHITS

from sanket_ml.config import get_ml_settings
from sanket_ml.models.base import BaseForecaster, ForecastQuantiles
from sanket_ml.registry import ModelSpec, register


class NHITSForecaster(BaseForecaster):
    """Neural Hierarchical Interpolation for Time Series — fast, accurate,
    excellent on long horizons (e.g. pharma 52-week)."""

    name = "nhits"
    supports_probabilistic = True
    supports_covariates = True

    def __init__(
        self,
        horizon: int = 26,
        input_size: int = 104,
        max_steps: int = 1000,
        batch_size: int = 64,
        learning_rate: float = 1e-3,
        freq: str = "W",
        quantiles: tuple[float, ...] = (0.1, 0.5, 0.9),
        n_blocks: tuple[int, ...] = (1, 1, 1),
        n_pool_kernel_size: tuple[int, ...] = (2, 2, 1),
        n_freq_downsample: tuple[int, ...] = (4, 2, 1),
        **kwargs: Any,
    ) -> None:
        super().__init__(
            horizon=horizon, input_size=input_size, max_steps=max_steps,
            batch_size=batch_size, learning_rate=learning_rate, freq=freq,
            quantiles=quantiles, **kwargs,
        )
        self._horizon = horizon
        self._freq = freq
        self._quantiles = list(quantiles)
        settings = get_ml_settings()
        accelerator = "auto" if settings.device == "auto" else settings.device
        self._model = NHITS(
            h=horizon,
            input_size=input_size,
            loss=MQLoss(quantiles=list(quantiles)),
            n_blocks=list(n_blocks),
            n_pool_kernel_size=list(n_pool_kernel_size),
            n_freq_downsample=list(n_freq_downsample),
            max_steps=max_steps,
            batch_size=batch_size,
            learning_rate=learning_rate,
            random_seed=settings.random_seed,
            accelerator=accelerator,
            enable_progress_bar=False,
            scaler_type="robust",
        )
        self._nf: NeuralForecast | None = None

    def fit(self, train: pd.DataFrame, static_features: pd.DataFrame | None = None) -> NHITSForecaster:
        df = train[["unique_id", "ds", "y"]].copy()
        df["ds"] = pd.to_datetime(df["ds"])
        self._nf = NeuralForecast(models=[self._model], freq=self._freq)
        self._nf.fit(df=df, static_df=static_features)
        self._fitted = True
        return self

    def predict(
        self,
        horizon: int,
        future_exog: pd.DataFrame | None = None,
        level: tuple[int, ...] = (10, 50, 90),
    ) -> ForecastQuantiles:
        self._require_fitted()
        assert self._nf is not None
        fc = self._nf.predict(futr_df=future_exog)
        cols = fc.columns.tolist()

        def pick(q: float) -> np.ndarray:
            for c in cols:
                if c.startswith("NHITS") and (c.endswith(f"-{int(q * 100)}") or c.endswith(f"-q-{int(q * 100)}")):
                    return fc[c].to_numpy().astype("float32")
            for c in cols:
                if c.startswith("NHITS"):
                    return fc[c].to_numpy().astype("float32")
            raise KeyError(f"No NHITS column for q={q}")

        p10 = np.clip(pick(0.1), 0.0, None)
        p50 = np.clip(pick(0.5), 0.0, None)
        p90 = np.maximum(pick(0.9), p50)
        return ForecastQuantiles(
            unique_id=fc["unique_id"].astype(str).tolist(),
            ds=pd.to_datetime(fc["ds"]).tolist(),
            p10=p10, p50=p50, p90=p90,
            model_name="nhits",
        )


register(
    ModelSpec(
        name="nhits",
        factory=NHITSForecaster,
        family="deep",
        supports_covariates=True,
        default_weight=1.1,
    )
)
