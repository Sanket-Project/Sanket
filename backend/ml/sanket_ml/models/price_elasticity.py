"""Price elasticity model using log-log OLS regression.

Estimates: ln(units_sold) ~ β₀ + β₁·ln(effective_price) + β₂·promo_flag
where effective_price = unit_price * (1 - markdown_pct).

Requires a DataFrame with columns:
  units_sold (int), unit_price (float), markdown_pct (float 0-1), promo_flag (bool)
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
import structlog

log = structlog.get_logger(__name__)


@dataclass
class ElasticityResult:
    elasticity_coef: float      # β₁ — price elasticity (typically negative)
    promo_lift_coef: float      # β₂ — log-unit lift from promotion
    intercept: float            # β₀
    r_squared: float
    n_obs: int
    promo_lift_pct: float       # exp(β₂) - 1 expressed as percentage


class PriceElasticityModel:
    """Log-log OLS price elasticity estimator."""

    def __init__(self) -> None:
        self._coef: np.ndarray | None = None
        self._result: ElasticityResult | None = None

    def fit(self, df: pd.DataFrame) -> PriceElasticityModel:
        required = {"units_sold", "unit_price", "markdown_pct", "promo_flag"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"Missing columns: {missing}")

        work = df.dropna(subset=["units_sold", "unit_price"]).copy()
        work = work[(work["units_sold"] > 0) & (work["unit_price"] > 0)]
        if len(work) < 10:
            log.warning("price_elasticity.insufficient_data", n=len(work))
            self._result = ElasticityResult(
                elasticity_coef=-1.5, promo_lift_coef=0.2, intercept=5.0,
                r_squared=0.0, n_obs=len(work), promo_lift_pct=22.1,
            )
            return self

        work["markdown_pct"] = work["markdown_pct"].fillna(0).clip(0, 0.99)
        work["promo_flag"] = work["promo_flag"].fillna(False).astype(float)
        work["effective_price"] = work["unit_price"] * (1 - work["markdown_pct"])

        ln_y = np.log(work["units_sold"].astype(float).values)
        ln_p = np.log(work["effective_price"].clip(0.01).values)
        promo = work["promo_flag"].values

        # Design matrix: [1, ln(price), promo_flag]
        X = np.column_stack([np.ones(len(work)), ln_p, promo])
        coef, residuals, rank, _ = np.linalg.lstsq(X, ln_y, rcond=None)

        y_hat = X @ coef
        ss_res = float(np.sum((ln_y - y_hat) ** 2))
        ss_tot = float(np.sum((ln_y - ln_y.mean()) ** 2))
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

        self._coef = coef
        self._result = ElasticityResult(
            elasticity_coef=round(float(coef[1]), 4),
            promo_lift_coef=round(float(coef[2]), 4),
            intercept=round(float(coef[0]), 4),
            r_squared=round(r2, 4),
            n_obs=len(work),
            promo_lift_pct=round((math.exp(float(coef[2])) - 1) * 100, 2),
        )
        log.info(
            "price_elasticity.fitted",
            elasticity=self._result.elasticity_coef,
            promo_lift_pct=self._result.promo_lift_pct,
            r2=self._result.r_squared,
        )
        return self

    def predict(self, unit_price: float, markdown_pct: float = 0.0, promo_flag: bool = False) -> float:
        """Return predicted units sold at the given price point."""
        if self._coef is None or self._result is None:
            raise RuntimeError("Model not fitted — call fit() first.")
        effective_price = max(0.01, unit_price * (1 - markdown_pct))
        ln_pred = (
            self._result.intercept
            + self._result.elasticity_coef * math.log(effective_price)
            + self._result.promo_lift_coef * float(promo_flag)
        )
        return round(math.exp(ln_pred), 2)

    def summary(self) -> dict:
        if self._result is None:
            return {}
        return {
            "elasticity_coef": self._result.elasticity_coef,
            "promo_lift_coef": self._result.promo_lift_coef,
            "promo_lift_pct": self._result.promo_lift_pct,
            "intercept": self._result.intercept,
            "r_squared": self._result.r_squared,
            "n_obs": self._result.n_obs,
        }
