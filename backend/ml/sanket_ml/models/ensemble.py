from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
import structlog
from scipy.optimize import minimize

from sanket_ml.models.base import ForecastQuantiles

log = structlog.get_logger(__name__)


def pinball_loss(y_true: np.ndarray, y_pred: np.ndarray, quantile: float) -> float:
    diff = y_true - y_pred
    return float(np.mean(np.maximum(quantile * diff, (quantile - 1) * diff)))


def weighted_average(forecasts: list[ForecastQuantiles], weights: list[float]) -> ForecastQuantiles:
    if not forecasts:
        raise ValueError("No forecasts to combine")
    if len(forecasts) != len(weights):
        raise ValueError(f"forecasts ({len(forecasts)}) vs weights ({len(weights)}) length mismatch")

    w = np.asarray(weights, dtype="float32")
    w = w / w.sum()

    base = forecasts[0]
    keys = list(zip(base.unique_id, [pd.Timestamp(d) for d in base.ds]))

    p10_acc = np.zeros(len(keys), dtype="float32")
    p50_acc = np.zeros(len(keys), dtype="float32")
    p90_acc = np.zeros(len(keys), dtype="float32")

    for _i, (fc, wi) in enumerate(zip(forecasts, w)):
        fc_keys = list(zip(fc.unique_id, [pd.Timestamp(d) for d in fc.ds]))
        if fc_keys != keys:
            # Re-align by building a dict
            lookup = {k: idx for idx, k in enumerate(fc_keys)}
            idx = np.array([lookup.get(k, -1) for k in keys])
            valid = idx >= 0
            p10_acc[valid] += wi * fc.p10[idx[valid]]
            p50_acc[valid] += wi * fc.p50[idx[valid]]
            p90_acc[valid] += wi * fc.p90[idx[valid]]
        else:
            p10_acc += wi * fc.p10
            p50_acc += wi * fc.p50
            p90_acc += wi * fc.p90

    return ForecastQuantiles(
        unique_id=[k[0] for k in keys],
        ds=[k[1] for k in keys],
        p10=p10_acc,
        p50=p50_acc,
        p90=np.maximum(p90_acc, p50_acc),
        model_name="ensemble_weighted",
    )


@dataclass
class StackedEnsemble:
    """Convex-weighted ensemble whose weights minimize pinball loss on a
    held-out validation set. Solves: min Σ_q pinball(y, Σ_m w_m p̂_{m,q}) s.t. w ≥ 0, Σ w = 1."""
    model_names: list[str] = field(default_factory=list)
    weights: dict[str, float] = field(default_factory=dict)

    def fit(
        self,
        validation: pd.DataFrame,
        forecasts: list[ForecastQuantiles],
        quantiles: tuple[float, ...] = (0.1, 0.5, 0.9),
    ) -> StackedEnsemble:
        """validation: DataFrame with columns [unique_id, ds, y]."""
        validation = validation.copy()
        validation["ds"] = pd.to_datetime(validation["ds"])

        # Build matrix P of shape (n_obs, n_models, n_quantiles)
        keys_v = list(zip(validation["unique_id"].astype(str), validation["ds"]))
        y_true = validation["y"].to_numpy(dtype="float64")
        n = len(keys_v)
        m = len(forecasts)
        nq = len(quantiles)
        P = np.zeros((n, m, nq), dtype="float64")

        for j, fc in enumerate(forecasts):
            fc_keys = list(zip(fc.unique_id, [pd.Timestamp(d) for d in fc.ds]))
            lookup = {k: idx for idx, k in enumerate(fc_keys)}
            preds_per_q = {0.1: fc.p10, 0.5: fc.p50, 0.9: fc.p90}
            for i, k in enumerate(keys_v):
                if k not in lookup:
                    P[i, j, :] = np.nan
                    continue
                idx = lookup[k]
                for q_idx, q in enumerate(quantiles):
                    arr = preds_per_q.get(q, fc.p50)
                    P[i, j, q_idx] = arr[idx]

        valid_rows = ~np.isnan(P).any(axis=(1, 2))
        P = P[valid_rows]
        y_true = y_true[valid_rows]
        if len(P) == 0:
            self.weights = {fc.model_name: 1 / m for fc in forecasts}
            self.model_names = [fc.model_name for fc in forecasts]
            return self

        def loss(w: np.ndarray) -> float:
            w = np.abs(w)
            w = w / w.sum()
            total = 0.0
            for q_idx, q in enumerate(quantiles):
                combined = (P[:, :, q_idx] * w).sum(axis=1)
                total += pinball_loss(y_true, combined, q)
            return total

        x0 = np.ones(m) / m
        result = minimize(
            loss,
            x0,
            method="SLSQP",
            bounds=[(0.0, 1.0)] * m,
            constraints={"type": "eq", "fun": lambda w: w.sum() - 1.0},
            options={"maxiter": 200, "ftol": 1e-6},
        )
        w_opt = np.abs(result.x)
        w_opt = w_opt / w_opt.sum()
        self.model_names = [fc.model_name for fc in forecasts]
        self.weights = dict(zip(self.model_names, w_opt.tolist()))
        log.info("ensemble.fit.done", weights=self.weights, final_loss=float(result.fun))
        return self

    def predict(self, forecasts: list[ForecastQuantiles]) -> ForecastQuantiles:
        if not self.weights:
            raise RuntimeError("StackedEnsemble.fit() must be called before predict()")
        w = [self.weights.get(fc.model_name, 0.0) for fc in forecasts]
        return weighted_average(forecasts, w)
