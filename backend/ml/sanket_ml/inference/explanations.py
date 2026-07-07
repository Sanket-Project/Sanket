from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
import structlog

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class FeatureContribution:
    feature: str
    shap_value: float
    feature_value: Any


@dataclass(frozen=True, slots=True)
class Explanation:
    sku_id: str
    forecast_date: pd.Timestamp
    base_value: float
    prediction: float
    top_contributions: list[FeatureContribution]
    direction: str  # "increase" or "decrease"


class ShapExplainer:
    """SHAP-based explanations for the LightGBM median quantile booster.
    Other model families fall back to simple feature-importance ranking."""

    def __init__(self, lgbm_forecaster, top_k: int = 6) -> None:
        from sanket_ml.models.gradient_boost.lightgbm_forecaster import LightGBMForecaster
        if not isinstance(lgbm_forecaster, LightGBMForecaster):
            raise TypeError("ShapExplainer requires a LightGBMForecaster")
        if 0.5 not in lgbm_forecaster._models:
            raise ValueError("LGBM median quantile model not present")
        import shap
        self._booster = lgbm_forecaster._models[0.5]
        self._features = lgbm_forecaster._feature_cols
        self._explainer = shap.TreeExplainer(self._booster)
        self._top_k = top_k

    def explain(
        self,
        X: pd.DataFrame,
        sku_ids: list[str],
        forecast_dates: list[pd.Timestamp],
    ) -> list[Explanation]:
        X = X[self._features].copy()
        shap_values = self._explainer.shap_values(X)
        if isinstance(shap_values, list):
            shap_values = shap_values[0]
        base_value = float(self._explainer.expected_value)
        if isinstance(self._explainer.expected_value, (list, np.ndarray)):
            base_value = float(np.asarray(self._explainer.expected_value).ravel()[0])

        explanations: list[Explanation] = []
        for i, (sku, ds) in enumerate(zip(sku_ids, forecast_dates)):
            row_shap = shap_values[i]
            row_vals = X.iloc[i].to_dict()
            pred = float(self._booster.predict(X.iloc[[i]])[0])
            # Top contributions by absolute SHAP value
            order = np.argsort(-np.abs(row_shap))[: self._top_k]
            contribs = [
                FeatureContribution(
                    feature=self._features[k],
                    shap_value=float(row_shap[k]),
                    feature_value=row_vals[self._features[k]],
                )
                for k in order
            ]
            net_effect = pred - base_value
            explanations.append(
                Explanation(
                    sku_id=sku,
                    forecast_date=ds,
                    base_value=base_value,
                    prediction=pred,
                    top_contributions=contribs,
                    direction="increase" if net_effect > 0 else "decrease",
                )
            )
        return explanations
