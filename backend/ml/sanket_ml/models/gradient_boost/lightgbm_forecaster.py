from __future__ import annotations

from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
import structlog

from sanket_ml.data.features import build_feature_matrix
from sanket_ml.models.base import BaseForecaster, ForecastQuantiles
from sanket_ml.registry import ModelSpec, register

log = structlog.get_logger(__name__)


_DEFAULT_PARAMS: dict[str, Any] = {
    "objective": "quantile",
    "metric": "quantile",
    "learning_rate": 0.05,
    "num_leaves": 127,
    "max_depth": -1,
    "min_data_in_leaf": 20,
    "feature_fraction": 0.8,
    "bagging_fraction": 0.8,
    "bagging_freq": 5,
    "lambda_l2": 1.0,
    "verbosity": -1,
    "force_row_wise": True,
}


class LightGBMForecaster(BaseForecaster):
    """Multi-quantile LightGBM forecaster trained on a global feature matrix.
    Three boosters (one per quantile) share the same feature set."""

    name = "lightgbm"
    supports_probabilistic = True
    supports_covariates = True

    def __init__(
        self,
        quantiles: tuple[float, float, float] = (0.1, 0.5, 0.9),
        num_boost_round: int = 2000,
        early_stopping_rounds: int = 100,
        seed: int = 42,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            quantiles=quantiles,
            num_boost_round=num_boost_round,
            early_stopping_rounds=early_stopping_rounds,
            seed=seed,
            **kwargs,
        )
        self._quantiles = quantiles
        self._n_rounds = num_boost_round
        self._early_stop = early_stopping_rounds
        self._seed = seed
        self._models: dict[float, lgb.Booster] = {}
        self._feature_cols: list[str] = []
        self._last_history: pd.DataFrame | None = None
        self._freq: str = "W"
        self._static: pd.DataFrame | None = None

    def fit(
        self,
        train: pd.DataFrame,
        static_features: pd.DataFrame | None = None,
    ) -> LightGBMForecaster:
        self._static = static_features
        feats = build_feature_matrix(train, industry=train.attrs.get("industry", "fashion"))
        self._feature_cols = [
            c for c in feats.columns
            if c not in ("unique_id", "ds", "y", "demand_class")
            and feats[c].dtype.kind in ("i", "f", "u")
        ]

        # Validation set: last 20% by date
        cutoff = feats["ds"].quantile(0.8)
        tr = feats[feats["ds"] <= cutoff]
        va = feats[feats["ds"] > cutoff]

        for q in self._quantiles:
            params = {**_DEFAULT_PARAMS, "alpha": q, "seed": self._seed}
            dtrain = lgb.Dataset(tr[self._feature_cols], label=tr["y"])
            dval = lgb.Dataset(va[self._feature_cols], label=va["y"], reference=dtrain)
            booster = lgb.train(
                params,
                dtrain,
                num_boost_round=self._n_rounds,
                valid_sets=[dval],
                valid_names=["val"],
                callbacks=[lgb.early_stopping(self._early_stop, verbose=False)],
            )
            self._models[q] = booster
            log.info("lgbm.fit.quantile.done", quantile=q, best_iter=booster.best_iteration)

        self._last_history = train.copy()
        self._freq = pd.infer_freq(
            train.sort_values("ds")["ds"].drop_duplicates().head(10)
        ) or "W"
        self._fitted = True
        return self

    def predict(
        self,
        horizon: int,
        future_exog: pd.DataFrame | None = None,
        level: tuple[int, ...] = (10, 50, 90),
    ) -> ForecastQuantiles:
        self._require_fitted()
        assert self._last_history is not None
        history = self._last_history.copy()
        ids = history["unique_id"].unique()
        max_ds = pd.to_datetime(history["ds"]).max()
        future_dates = pd.date_range(
            max_ds + pd.tseries.frequencies.to_offset(self._freq),
            periods=horizon,
            freq=self._freq,
        )

        records: list[dict] = []
        # Recursive multi-step forecast
        rolling = history.copy()
        for _step, ds in enumerate(future_dates):
            placeholder = pd.DataFrame(
                {"unique_id": ids, "ds": ds, "y": np.nan}
            )
            combined = pd.concat([rolling, placeholder], ignore_index=True)
            feats_step = build_feature_matrix(combined, industry=history.attrs.get("industry", "fashion"))
            current = feats_step[feats_step["ds"] == ds]
            if current.empty:
                continue
            X = current[self._feature_cols]
            preds = {q: self._models[q].predict(X) for q in self._quantiles}

            for i, uid in enumerate(current["unique_id"].tolist()):
                records.append({
                    "unique_id": uid,
                    "ds": ds,
                    "p10": float(max(preds[0.1][i], 0.0)),
                    "p50": float(max(preds[0.5][i], 0.0)),
                    "p90": float(max(preds[0.9][i], preds[0.5][i])),
                })
            # Feed median back into rolling state for next step
            rolling = pd.concat(
                [
                    rolling,
                    pd.DataFrame(
                        {
                            "unique_id": current["unique_id"].values,
                            "ds": ds,
                            "y": preds[0.5],
                        }
                    ),
                ],
                ignore_index=True,
            )

        out = pd.DataFrame(records)
        return ForecastQuantiles(
            unique_id=out["unique_id"].tolist(),
            ds=pd.to_datetime(out["ds"]).tolist(),
            p10=out["p10"].to_numpy().astype("float32"),
            p50=out["p50"].to_numpy().astype("float32"),
            p90=out["p90"].to_numpy().astype("float32"),
            model_name="lightgbm",
        )

    def feature_importance(self) -> pd.DataFrame:
        if 0.5 not in self._models:
            raise RuntimeError("Median model not available")
        booster = self._models[0.5]
        gains = booster.feature_importance(importance_type="gain")
        return (
            pd.DataFrame({"feature": self._feature_cols, "gain": gains})
            .sort_values("gain", ascending=False)
            .reset_index(drop=True)
        )


register(
    ModelSpec(
        name="lightgbm",
        factory=LightGBMForecaster,
        family="gbt",
        supports_covariates=True,
        default_weight=1.0,
    )
)
