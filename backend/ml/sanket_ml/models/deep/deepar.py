from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import structlog
from neuralforecast import NeuralForecast
from neuralforecast.losses.pytorch import DistributionLoss
from neuralforecast.models import DeepAR

from sanket_ml.config import get_ml_settings
from sanket_ml.models.base import BaseForecaster, ForecastQuantiles
from sanket_ml.registry import ModelSpec, register

log = structlog.get_logger(__name__)


class DeepARForecaster(BaseForecaster):
    """Autoregressive RNN with parametric output distribution.
    Strong on global panels with thousands of related series (electronics SKU networks)."""

    name = "deepar"
    supports_probabilistic = True
    supports_covariates = True

    def __init__(
        self,
        horizon: int = 12,
        input_size: int = 52,
        lstm_n_layers: int = 2,
        lstm_hidden_size: int = 128,
        max_steps: int = 1000,
        batch_size: int = 64,
        learning_rate: float = 1e-3,
        freq: str = "W",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            horizon=horizon,
            input_size=input_size,
            lstm_n_layers=lstm_n_layers,
            lstm_hidden_size=lstm_hidden_size,
            max_steps=max_steps,
            batch_size=batch_size,
            freq=freq,
            **kwargs,
        )
        self._horizon = horizon
        self._freq = freq
        settings = get_ml_settings()
        accelerator = "auto" if settings.device == "auto" else settings.device
        self._model = DeepAR(
            h=horizon,
            input_size=input_size,
            lstm_n_layers=lstm_n_layers,
            lstm_hidden_size=lstm_hidden_size,
            trajectory_samples=200,
            loss=DistributionLoss(distribution="StudentT", level=[80]),
            max_steps=max_steps,
            batch_size=batch_size,
            learning_rate=learning_rate,
            random_seed=settings.random_seed,
            accelerator=accelerator,
            enable_progress_bar=False,
            scaler_type="robust",
        )
        self._nf: NeuralForecast | None = None

    def fit(self, train: pd.DataFrame, static_features: pd.DataFrame | None = None) -> DeepARForecaster:
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
        # DeepAR with level=[80] returns DeepAR, DeepAR-lo-80, DeepAR-hi-80
        p50 = np.clip(fc["DeepAR"].to_numpy().astype("float32"), 0.0, None)
        p10 = np.clip(fc.get("DeepAR-lo-80", fc["DeepAR"]).to_numpy().astype("float32"), 0.0, None)
        p90 = np.maximum(fc.get("DeepAR-hi-80", fc["DeepAR"]).to_numpy().astype("float32"), p50)
        return ForecastQuantiles(
            unique_id=fc["unique_id"].astype(str).tolist(),
            ds=pd.to_datetime(fc["ds"]).tolist(),
            p10=p10, p50=p50, p90=p90,
            model_name="deepar",
        )


register(
    ModelSpec(
        name="deepar",
        factory=DeepARForecaster,
        family="deep",
        supports_covariates=True,
        default_weight=1.0,
    )
)
