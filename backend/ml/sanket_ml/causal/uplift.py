from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import structlog
from econml.dml import CausalForestDML
from sklearn.ensemble import GradientBoostingRegressor

log = structlog.get_logger(__name__)


@dataclass
class UpliftResult:
    cate: np.ndarray            # per-row conditional ATE
    ate: float
    feature_importance: dict[str, float]
    treatment_col: str
    outcome_col: str


class UpliftModel:
    """Heterogeneous treatment effect estimator using EconML's CausalForestDML.

    Use cases:
      • Fashion: which customer segments / SKUs respond best to a markdown?
      • Electronics: which channels benefit most from a price drop?
    """

    def __init__(
        self,
        treatment: str,
        outcome: str,
        features: list[str],
        n_estimators: int = 200,
        max_depth: int = 6,
        random_state: int = 42,
    ) -> None:
        self.treatment = treatment
        self.outcome = outcome
        self.features = features
        self._model = CausalForestDML(
            model_y=GradientBoostingRegressor(n_estimators=200, max_depth=4),
            model_t=GradientBoostingRegressor(n_estimators=200, max_depth=4),
            n_estimators=n_estimators,
            max_depth=max_depth,
            discrete_treatment=True,
            random_state=random_state,
        )
        self._fitted = False

    def fit(self, df: pd.DataFrame) -> UpliftModel:
        df = df[[self.treatment, self.outcome, *self.features]].dropna()
        Y = df[self.outcome].to_numpy()
        T = df[self.treatment].astype(int).to_numpy()
        X = df[self.features].to_numpy()
        self._model.fit(Y=Y, T=T, X=X)
        self._fitted = True
        log.info("uplift.fit.done", n_rows=len(df), n_features=len(self.features))
        return self

    def predict(self, df: pd.DataFrame) -> UpliftResult:
        if not self._fitted:
            raise RuntimeError("UpliftModel.fit() not called")
        X = df[self.features].to_numpy()
        cate = self._model.effect(X)
        # Feature importance from underlying forest
        try:
            imp = self._model.feature_importances_
            fi = dict(zip(self.features, imp.tolist()))
        except Exception:
            fi = {}
        return UpliftResult(
            cate=cate,
            ate=float(np.mean(cate)),
            feature_importance=fi,
            treatment_col=self.treatment,
            outcome_col=self.outcome,
        )
