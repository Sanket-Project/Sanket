from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from statsforecast import StatsForecast
from statsforecast.models import TSB, CrostonClassic, CrostonOptimized, CrostonSBA

from sanket_ml.models.base import BaseForecaster, ForecastQuantiles
from sanket_ml.registry import ModelSpec, register


class CrostonForecaster(BaseForecaster):
    """Croston-family methods for intermittent demand — critical for pharma
    SKUs and slow-moving fashion long-tail items."""

    name = "croston"
    supports_probabilistic = True
    supports_covariates = False

    def __init__(
        self,
        variant: str = "sba",
        freq: str = "W",
        n_jobs: int = -1,
        **kwargs: Any,
    ) -> None:
        super().__init__(variant=variant, freq=freq, n_jobs=n_jobs, **kwargs)
        variants = {
            "classic": CrostonClassic(),
            "optimized": CrostonOptimized(),
            "sba": CrostonSBA(),
            "tsb": TSB(alpha_d=0.2, alpha_p=0.2),
        }
        if variant not in variants:
            raise ValueError(f"Unknown Croston variant: {variant}. Choose from {list(variants)}")
        self._sf: StatsForecast | None = None
        self._variant = variant
        self._freq = freq
        self._n_jobs = n_jobs
        self._model = variants[variant]
        self._last_dates: dict[str, pd.Timestamp] = {}
        self._residual_std: dict[str, float] = {}

    def fit(
        self,
        train: pd.DataFrame,
        static_features: pd.DataFrame | None = None,
    ) -> CrostonForecaster:
        df = train[["unique_id", "ds", "y"]].copy()
        df["ds"] = pd.to_datetime(df["ds"])
        self._sf = StatsForecast(
            models=[self._model],
            freq=self._freq,
            n_jobs=self._n_jobs,
            fallback_model=CrostonClassic(),
        )
        self._sf.fit(df)

        # Residual std per series for empirical prediction interval
        in_sample = self._sf.forecast_fitted_values()
        col = [c for c in in_sample.columns if c not in ("unique_id", "ds", "y")][0]
        for uid, g in in_sample.groupby("unique_id"):
            resid = (g["y"] - g[col]).to_numpy()
            self._residual_std[uid] = float(np.nanstd(resid)) if len(resid) else 1.0
            self._last_dates[uid] = pd.Timestamp(g["ds"].max())
        self._fitted = True
        return self

    def predict(
        self,
        horizon: int,
        future_exog: pd.DataFrame | None = None,
        level: tuple[int, ...] = (10, 50, 90),
    ) -> ForecastQuantiles:
        self._require_fitted()
        assert self._sf is not None
        fc = self._sf.predict(h=horizon)
        col = [c for c in fc.columns if c not in ("unique_id", "ds")][0]
        p50 = fc[col].to_numpy().astype("float32")

        # Build empirical prediction intervals from residual std
        sigmas = np.array(
            [self._residual_std.get(uid, 1.0) for uid in fc["unique_id"]], dtype="float32"
        )
        p10 = np.clip(p50 - 1.2816 * sigmas, 0.0, None)
        p90 = p50 + 1.2816 * sigmas
        return ForecastQuantiles(
            unique_id=fc["unique_id"].astype(str).tolist(),
            ds=pd.to_datetime(fc["ds"]).tolist(),
            p10=p10,
            p50=p50,
            p90=p90.astype("float32"),
            model_name=f"croston_{self._variant}",
        )


register(
    ModelSpec(
        name="croston",
        factory=CrostonForecaster,
        family="statistical",
        intermittent_friendly=True,
        cold_start_friendly=True,
        default_weight=0.7,
    )
)
