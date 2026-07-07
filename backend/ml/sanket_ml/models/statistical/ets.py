from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from statsforecast import StatsForecast
from statsforecast.models import AutoARIMA, AutoETS

from sanket_ml.models.base import BaseForecaster, ForecastQuantiles
from sanket_ml.registry import ModelSpec, register


class ETSForecaster(BaseForecaster):
    name = "ets"
    supports_probabilistic = True

    def __init__(self, freq: str = "W", season_length: int = 52, n_jobs: int = -1, **kwargs: Any) -> None:
        super().__init__(freq=freq, season_length=season_length, n_jobs=n_jobs, **kwargs)
        self._sf: StatsForecast | None = None
        self._freq = freq
        self._season_length = season_length
        self._n_jobs = n_jobs

    def fit(self, train: pd.DataFrame, static_features: pd.DataFrame | None = None) -> ETSForecaster:
        df = train[["unique_id", "ds", "y"]].copy()
        df["ds"] = pd.to_datetime(df["ds"])
        self._sf = StatsForecast(
            models=[AutoETS(season_length=self._season_length, model="ZZZ")],
            freq=self._freq,
            n_jobs=self._n_jobs,
            fallback_model=AutoARIMA(season_length=self._season_length),
        )
        self._sf.fit(df)
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
        fc = self._sf.predict(h=horizon, level=[80])
        # AutoETS columns: AutoETS, AutoETS-lo-80, AutoETS-hi-80
        return ForecastQuantiles(
            unique_id=fc["unique_id"].astype(str).tolist(),
            ds=pd.to_datetime(fc["ds"]).tolist(),
            p10=np.clip(fc["AutoETS-lo-80"].to_numpy().astype("float32"), 0.0, None),
            p50=fc["AutoETS"].to_numpy().astype("float32"),
            p90=fc["AutoETS-hi-80"].to_numpy().astype("float32"),
            model_name="ets",
        )


register(
    ModelSpec(
        name="ets",
        factory=ETSForecaster,
        family="statistical",
        cold_start_friendly=True,
        default_weight=0.6,
    )
)
