from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import structlog
import torch

from sanket_ml.config import get_ml_settings
from sanket_ml.models.base import BaseForecaster, ForecastQuantiles
from sanket_ml.registry import ModelSpec, register

log = structlog.get_logger(__name__)


class ChronosForecaster(BaseForecaster):
    """Amazon Chronos — T5-based TS foundation model. Tokenizes time-series
    into a fixed vocabulary and samples futures autoregressively."""

    name = "chronos"
    supports_probabilistic = True
    supports_covariates = False

    def __init__(
        self,
        repo: str | None = None,
        num_samples: int = 100,
        temperature: float = 1.0,
        top_k: int = 50,
        top_p: float = 1.0,
        freq: str = "W",
        context_len: int = 512,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            repo=repo, num_samples=num_samples, temperature=temperature,
            top_k=top_k, top_p=top_p, freq=freq, context_len=context_len, **kwargs,
        )
        settings = get_ml_settings()
        self._repo = repo or settings.chronos_repo
        self._num_samples = num_samples
        self._temperature = temperature
        self._top_k = top_k
        self._top_p = top_p
        self._freq = freq
        self._context_len = context_len
        self._history: pd.DataFrame | None = None
        self._pipeline = None

    def _ensure_model(self) -> None:
        if self._pipeline is not None:
            return
        from chronos import ChronosPipeline  # type: ignore

        settings = get_ml_settings()
        device = "cuda" if (torch.cuda.is_available() and settings.device != "cpu") else "cpu"
        dtype = torch.bfloat16 if device == "cuda" else torch.float32
        self._pipeline = ChronosPipeline.from_pretrained(
            self._repo,
            device_map=device,
            torch_dtype=dtype,
        )
        log.info("chronos.loaded", repo=self._repo, device=device)

    def fit(self, train: pd.DataFrame, static_features: pd.DataFrame | None = None) -> ChronosForecaster:
        self._history = train[["unique_id", "ds", "y"]].copy()
        self._history["ds"] = pd.to_datetime(self._history["ds"])
        self._fitted = True
        return self

    def predict(
        self,
        horizon: int,
        future_exog: pd.DataFrame | None = None,
        level: tuple[int, ...] = (10, 50, 90),
    ) -> ForecastQuantiles:
        self._require_fitted()
        assert self._history is not None
        self._ensure_model()

        ids = self._history["unique_id"].unique()
        ctx_list: list[torch.Tensor] = []
        for uid in ids:
            ys = self._history[self._history["unique_id"] == uid].sort_values("ds")["y"].to_numpy()
            ctx = torch.tensor(ys[-self._context_len:], dtype=torch.float32)
            ctx_list.append(ctx)

        # ChronosPipeline.predict expects a list of 1D tensors (or stacks them)
        forecast = self._pipeline.predict(  # type: ignore[union-attr]
            ctx_list,
            prediction_length=horizon,
            num_samples=self._num_samples,
            temperature=self._temperature,
            top_k=self._top_k,
            top_p=self._top_p,
        )
        # shape: (N, num_samples, horizon)
        arr = forecast.cpu().numpy() if isinstance(forecast, torch.Tensor) else np.asarray(forecast)
        p10 = np.quantile(arr, 0.1, axis=1)
        p50 = np.quantile(arr, 0.5, axis=1)
        p90 = np.quantile(arr, 0.9, axis=1)

        max_ds = self._history["ds"].max()
        future_dates = pd.date_range(
            max_ds + pd.tseries.frequencies.to_offset(self._freq),
            periods=horizon,
            freq=self._freq,
        )

        uid_col: list[str] = []
        ds_col: list[pd.Timestamp] = []
        p10_flat: list[float] = []
        p50_flat: list[float] = []
        p90_flat: list[float] = []
        for i, uid in enumerate(ids):
            for t in range(horizon):
                uid_col.append(uid)
                ds_col.append(future_dates[t])
                p10_flat.append(float(p10[i, t]))
                p50_flat.append(float(p50[i, t]))
                p90_flat.append(float(p90[i, t]))

        p50_arr = np.clip(np.asarray(p50_flat, dtype="float32"), 0.0, None)
        return ForecastQuantiles(
            unique_id=uid_col,
            ds=ds_col,
            p10=np.clip(np.asarray(p10_flat, dtype="float32"), 0.0, None),
            p50=p50_arr,
            p90=np.maximum(np.asarray(p90_flat, dtype="float32"), p50_arr),
            model_name="chronos",
        )


register(
    ModelSpec(
        name="chronos",
        factory=ChronosForecaster,
        family="foundation",
        cold_start_friendly=True,
        default_weight=1.2,
    )
)
