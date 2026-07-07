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


class LagLlamaForecaster(BaseForecaster):
    """Lag-Llama — decoder-only transformer with lag features as tokens.
    Strong on probabilistic forecasts with limited context."""

    name = "lag_llama"
    supports_probabilistic = True
    supports_covariates = False

    def __init__(
        self,
        repo: str | None = None,
        context_length: int = 256,
        prediction_length: int = 26,
        num_samples: int = 100,
        freq: str = "W",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            repo=repo, context_length=context_length,
            prediction_length=prediction_length, num_samples=num_samples,
            freq=freq, **kwargs,
        )
        settings = get_ml_settings()
        self._repo = repo or settings.lag_llama_repo
        self._context_length = context_length
        self._prediction_length = prediction_length
        self._num_samples = num_samples
        self._freq = freq
        self._predictor = None
        self._history: pd.DataFrame | None = None

    def _ensure_model(self) -> None:
        if self._predictor is not None:
            return
        try:
            from huggingface_hub import hf_hub_download
            from lag_llama.gluon.estimator import LagLlamaEstimator  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "Lag-Llama requires `pip install lag-llama` and huggingface_hub."
            ) from e

        settings = get_ml_settings()
        device = "cuda" if (torch.cuda.is_available() and settings.device != "cpu") else "cpu"
        # Pin the revision so we never pull a mutated upstream branch (CWE-494).
        ckpt = hf_hub_download(
            repo_id=self._repo,
            filename="lag-llama.ckpt",
            revision=settings.lag_llama_revision,
        )
        estimator = LagLlamaEstimator(
            ckpt_path=ckpt,
            prediction_length=self._prediction_length,
            context_length=self._context_length,
            num_parallel_samples=self._num_samples,
            device=torch.device(device),
        )
        self._predictor = estimator.create_predictor(
            estimator.create_transformation(),
            estimator.create_lightning_module(),
        )
        log.info("lag_llama.loaded", repo=self._repo, device=device)

    def fit(self, train: pd.DataFrame, static_features: pd.DataFrame | None = None) -> LagLlamaForecaster:
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
        from gluonts.dataset.pandas import PandasDataset  # type: ignore

        ds = PandasDataset.from_long_dataframe(
            self._history.rename(columns={"unique_id": "item_id", "y": "target"}),
            target="target",
            item_id="item_id",
            timestamp="ds",
            freq=self._freq,
        )

        max_ds = self._history["ds"].max()
        future_dates = pd.date_range(
            max_ds + pd.tseries.frequencies.to_offset(self._freq),
            periods=horizon,
            freq=self._freq,
        )

        uid_col: list[str] = []
        ds_col: list[pd.Timestamp] = []
        p10_list: list[float] = []
        p50_list: list[float] = []
        p90_list: list[float] = []

        for fc in self._predictor.predict(ds, num_samples=self._num_samples):  # type: ignore[union-attr]
            samples = fc.samples  # (num_samples, prediction_length)
            q10 = np.quantile(samples, 0.1, axis=0)
            q50 = np.quantile(samples, 0.5, axis=0)
            q90 = np.quantile(samples, 0.9, axis=0)
            uid = str(fc.item_id)
            for t in range(min(horizon, len(q50))):
                uid_col.append(uid)
                ds_col.append(future_dates[t])
                p10_list.append(float(q10[t]))
                p50_list.append(float(q50[t]))
                p90_list.append(float(q90[t]))

        p50_arr = np.clip(np.asarray(p50_list, dtype="float32"), 0.0, None)
        return ForecastQuantiles(
            unique_id=uid_col,
            ds=ds_col,
            p10=np.clip(np.asarray(p10_list, dtype="float32"), 0.0, None),
            p50=p50_arr,
            p90=np.maximum(np.asarray(p90_list, dtype="float32"), p50_arr),
            model_name="lag_llama",
        )


register(
    ModelSpec(
        name="lag_llama",
        factory=LagLlamaForecaster,
        family="foundation",
        cold_start_friendly=True,
        default_weight=1.0,
    )
)
