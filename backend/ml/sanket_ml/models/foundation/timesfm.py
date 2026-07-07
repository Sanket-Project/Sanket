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


class TimesFMForecaster(BaseForecaster):
    """Google TimesFM 200M — pretrained decoder-only TS foundation model.
    Zero-shot capable; supports optional fine-tuning via the timesfm package."""

    name = "timesfm"
    supports_probabilistic = True
    supports_covariates = False
    requires_gpu = False

    def __init__(
        self,
        repo: str | None = None,
        context_len: int = 512,
        horizon_len: int = 128,
        per_core_batch_size: int = 32,
        freq: str = "W",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            repo=repo, context_len=context_len, horizon_len=horizon_len,
            per_core_batch_size=per_core_batch_size, freq=freq, **kwargs,
        )
        settings = get_ml_settings()
        self._repo = repo or settings.timesfm_repo
        self._context_len = context_len
        self._horizon_len = horizon_len
        self._batch = per_core_batch_size
        self._freq = freq
        self._history: pd.DataFrame | None = None
        self._tfm = None  # lazy

    def _ensure_model(self) -> None:
        if self._tfm is not None:
            return
        try:
            import timesfm  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "TimesFM requires `pip install timesfm`. See google-research/timesfm."
            ) from e
        settings = get_ml_settings()
        backend = "gpu" if torch.cuda.is_available() and settings.device != "cpu" else "cpu"
        self._tfm = timesfm.TimesFm(
            hparams=timesfm.TimesFmHparams(
                backend=backend,
                per_core_batch_size=self._batch,
                horizon_len=self._horizon_len,
                context_len=self._context_len,
                num_layers=20,
            ),
            checkpoint=timesfm.TimesFmCheckpoint(huggingface_repo_id=self._repo),
        )
        log.info("timesfm.loaded", repo=self._repo, backend=backend)

    def fit(
        self,
        train: pd.DataFrame,
        static_features: pd.DataFrame | None = None,
    ) -> TimesFMForecaster:
        # Foundation models are zero-shot by default; "fit" just memorizes history.
        # For fine-tuning, use sanket_ml.training.pretraining.fine_tune_timesfm.
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
        forecasts_list: list[np.ndarray] = []
        quantile_list: list[np.ndarray] = []
        unique_id_col: list[str] = []
        ds_col: list[pd.Timestamp] = []
        max_ds = self._history["ds"].max()
        future_dates = pd.date_range(
            max_ds + pd.tseries.frequencies.to_offset(self._freq),
            periods=horizon,
            freq=self._freq,
        )

        # TimesFM expects list[np.ndarray]
        inputs = []
        for uid in ids:
            ys = self._history[self._history["unique_id"] == uid].sort_values("ds")["y"].to_numpy(dtype=np.float32)
            ys = ys[-self._context_len:]
            inputs.append(ys)

        freq_map = {"W": 1, "M": 2, "D": 0}
        freq_token = freq_map.get(self._freq, 1)

        point_fc, quantile_fc = self._tfm.forecast(  # type: ignore[union-attr]
            inputs,
            freq=[freq_token] * len(inputs),
        )
        # point_fc shape (N, horizon_len), quantile_fc shape (N, horizon_len, 10) [q=0.1..1.0]
        for i, uid in enumerate(ids):
            for t in range(horizon):
                unique_id_col.append(uid)
                ds_col.append(future_dates[t])
                forecasts_list.append(point_fc[i, t])
                quantile_list.append(quantile_fc[i, t])

        p50 = np.array([q[4] if len(q) > 4 else f for f, q in zip(forecasts_list, quantile_list)],
                       dtype="float32")
        p10 = np.clip(
            np.array([q[0] if len(q) > 0 else 0.0 for q in quantile_list], dtype="float32"),
            0.0,
            None,
        )
        p90 = np.maximum(
            np.array([q[8] if len(q) > 8 else 0.0 for q in quantile_list], dtype="float32"),
            p50,
        )

        return ForecastQuantiles(
            unique_id=unique_id_col,
            ds=ds_col,
            p10=p10,
            p50=np.clip(p50, 0.0, None),
            p90=p90,
            model_name="timesfm",
        )


register(
    ModelSpec(
        name="timesfm",
        factory=TimesFMForecaster,
        family="foundation",
        cold_start_friendly=True,
        default_weight=1.3,
    )
)
