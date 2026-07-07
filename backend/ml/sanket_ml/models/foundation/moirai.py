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


class MoiraiForecaster(BaseForecaster):
    """Salesforce Moirai-1.1-R — masked-encoder TS foundation model with
    arbitrary-frequency support and multivariate inputs."""

    name = "moirai"
    supports_probabilistic = True
    supports_covariates = True

    def __init__(
        self,
        repo: str | None = None,
        prediction_length: int = 26,
        context_length: int = 512,
        patch_size: int | str = "auto",
        num_samples: int = 100,
        freq: str = "W",
        **kwargs: Any,
    ) -> None:
        super().__init__(
            repo=repo, prediction_length=prediction_length,
            context_length=context_length, patch_size=patch_size,
            num_samples=num_samples, freq=freq, **kwargs,
        )
        settings = get_ml_settings()
        self._repo = repo or settings.moirai_repo
        self._prediction_length = prediction_length
        self._context_length = context_length
        self._patch_size = patch_size
        self._num_samples = num_samples
        self._freq = freq
        self._predictor = None
        self._history: pd.DataFrame | None = None

    def _ensure_model(self) -> None:
        if self._predictor is not None:
            return
        try:
            from uni2ts.model.moirai import MoiraiForecast, MoiraiModule  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "Moirai requires `pip install uni2ts`. See SalesforceAIResearch/uni2ts."
            ) from e
        module = MoiraiModule.from_pretrained(self._repo)
        settings = get_ml_settings()
        device = "cuda" if (torch.cuda.is_available() and settings.device != "cpu") else "cpu"
        self._predictor = MoiraiForecast(
            module=module,
            prediction_length=self._prediction_length,
            context_length=self._context_length,
            patch_size=self._patch_size,
            num_samples=self._num_samples,
            target_dim=1,
            feat_dynamic_real_dim=0,
            past_feat_dynamic_real_dim=0,
        ).to(device)
        self._predictor.eval()
        log.info("moirai.loaded", repo=self._repo, device=device)

    def fit(self, train: pd.DataFrame, static_features: pd.DataFrame | None = None) -> MoiraiForecaster:
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

        device = next(self._predictor.parameters()).device  # type: ignore[union-attr]
        for uid in ids:
            ys = (
                self._history[self._history["unique_id"] == uid]
                .sort_values("ds")["y"]
                .to_numpy(dtype=np.float32)[-self._context_length:]
            )
            past = torch.tensor(ys, dtype=torch.float32, device=device).reshape(1, -1, 1)
            with torch.no_grad():
                samples = self._predictor(past_target=past, past_observed_target=torch.ones_like(past).bool())
            # samples shape: (num_samples, prediction_length, 1) or similar
            arr = samples.cpu().numpy().squeeze(-1)  # (S, H)
            q10 = np.quantile(arr, 0.1, axis=0)
            q50 = np.quantile(arr, 0.5, axis=0)
            q90 = np.quantile(arr, 0.9, axis=0)
            for t in range(horizon):
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
            model_name="moirai",
        )


register(
    ModelSpec(
        name="moirai",
        factory=MoiraiForecaster,
        family="foundation",
        supports_covariates=True,
        cold_start_friendly=True,
        default_weight=1.2,
    )
)
