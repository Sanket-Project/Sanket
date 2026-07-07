from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import structlog
from neuralforecast import NeuralForecast
from neuralforecast.losses.pytorch import MQLoss
from neuralforecast.models import TFT

from sanket_ml.config import get_ml_settings
from sanket_ml.models.base import BaseForecaster, ForecastQuantiles
from sanket_ml.registry import ModelSpec, register

log = structlog.get_logger(__name__)


class TFTForecaster(BaseForecaster):
    """Temporal Fusion Transformer — handles static, known-future, and
    observed-past covariates simultaneously with attention-based feature selection."""

    name = "tft"
    supports_probabilistic = True
    supports_covariates = True
    requires_gpu = False  # works on CPU but slow

    def __init__(
        self,
        horizon: int = 26,
        input_size: int = 104,
        hidden_size: int = 64,
        n_head: int = 4,
        attn_dropout: float = 0.1,
        dropout: float = 0.1,
        max_steps: int = 1000,
        batch_size: int = 64,
        learning_rate: float = 1e-3,
        freq: str = "W",
        quantiles: tuple[float, ...] = (0.1, 0.5, 0.9),
        **kwargs: Any,
    ) -> None:
        super().__init__(
            horizon=horizon,
            input_size=input_size,
            hidden_size=hidden_size,
            n_head=n_head,
            max_steps=max_steps,
            batch_size=batch_size,
            learning_rate=learning_rate,
            freq=freq,
            quantiles=quantiles,
            **kwargs,
        )
        self._horizon = horizon
        self._input_size = input_size
        self._freq = freq
        self._quantiles = list(quantiles)
        self._nf: NeuralForecast | None = None
        settings = get_ml_settings()
        accelerator = "auto" if settings.device == "auto" else settings.device
        self._model = TFT(
            h=horizon,
            input_size=input_size,
            hidden_size=hidden_size,
            n_head=n_head,
            attn_dropout=attn_dropout,
            dropout=dropout,
            loss=MQLoss(quantiles=list(quantiles)),
            max_steps=max_steps,
            batch_size=batch_size,
            learning_rate=learning_rate,
            random_seed=settings.random_seed,
            accelerator=accelerator,
            enable_progress_bar=False,
            scaler_type="robust",
        )

    def fit(
        self,
        train: pd.DataFrame,
        static_features: pd.DataFrame | None = None,
    ) -> TFTForecaster:
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
        # Columns from MQLoss: TFT-lo-10 ... TFT-median ... TFT-hi-90
        # Actually neuralforecast names them: TFT-q-10, TFT-q-50, TFT-q-90 etc.
        cols = fc.columns.tolist()

        def pick(q: float) -> np.ndarray:
            # neuralforecast names: "TFT-q-{int(q*100)}" or "TFT"
            candidates = [c for c in cols if c.startswith("TFT")]
            for c in candidates:
                if c.endswith(f"-{int(q * 100)}") or c.endswith(f"-q-{int(q * 100)}"):
                    return fc[c].to_numpy().astype("float32")
            # Fallback: median or first non-id column
            for c in candidates:
                return fc[c].to_numpy().astype("float32")
            raise KeyError(f"No TFT prediction column for q={q}")

        p10 = np.clip(pick(0.1), 0.0, None)
        p50 = np.clip(pick(0.5), 0.0, None)
        p90 = np.maximum(pick(0.9), p50)

        return ForecastQuantiles(
            unique_id=fc["unique_id"].astype(str).tolist(),
            ds=pd.to_datetime(fc["ds"]).tolist(),
            p10=p10,
            p50=p50,
            p90=p90,
            model_name="tft",
        )


register(
    ModelSpec(
        name="tft",
        factory=TFTForecaster,
        family="deep",
        supports_covariates=True,
        default_weight=1.2,
    )
)
