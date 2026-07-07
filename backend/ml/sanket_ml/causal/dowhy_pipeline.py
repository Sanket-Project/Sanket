from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import structlog
from dowhy import CausalModel

log = structlog.get_logger(__name__)


@dataclass
class CausalEffect:
    treatment: str
    outcome: str
    ate: float                       # average treatment effect
    p_value: float | None
    refutation_methods: list[str]
    refutation_passed: bool
    method: str


class PromoUpliftEstimator:
    """Estimate the causal effect of a promo flag / markdown on units sold,
    adjusting for confounders (price level, seasonality, weather, etc.).

    Wraps DoWhy's four-step process: model → identify → estimate → refute.
    """

    def __init__(
        self,
        treatment: str = "promo",
        outcome: str = "y",
        common_causes: list[str] | None = None,
        instrument: str | None = None,
    ) -> None:
        self.treatment = treatment
        self.outcome = outcome
        self.common_causes = common_causes or [
            "y_lag_1", "y_lag_4", "month", "week", "markdown",
        ]
        self.instrument = instrument

    def estimate(
        self,
        df: pd.DataFrame,
        method: str = "backdoor.linear_regression",
        run_refutation: bool = True,
    ) -> CausalEffect:
        # Filter columns and rows
        needed = [self.treatment, self.outcome, *self.common_causes]
        data = df[[c for c in needed if c in df.columns]].dropna().copy()
        if self.treatment not in data.columns:
            raise ValueError(f"Treatment column '{self.treatment}' missing")

        # Binarize treatment if continuous
        if data[self.treatment].nunique() > 2:
            data[self.treatment] = (data[self.treatment] > 0).astype(int)

        model = CausalModel(
            data=data,
            treatment=self.treatment,
            outcome=self.outcome,
            common_causes=[c for c in self.common_causes if c in data.columns],
            instruments=[self.instrument] if self.instrument else None,
        )
        identified = model.identify_effect(proceed_when_unidentifiable=True)
        estimate = model.estimate_effect(identified, method_name=method)

        refutations: list[str] = []
        refutation_passed = True
        if run_refutation:
            try:
                r1 = model.refute_estimate(
                    identified, estimate, method_name="random_common_cause"
                )
                refutations.append(f"random_common_cause: new_effect={r1.new_effect:.4f}")
                if abs(r1.new_effect - estimate.value) > 0.5 * abs(estimate.value + 1e-9):
                    refutation_passed = False
            except Exception as exc:
                log.warning("refute.random_common_cause.failed", error=str(exc))
            try:
                r2 = model.refute_estimate(
                    identified, estimate, method_name="placebo_treatment_refuter",
                    placebo_type="permute",
                )
                refutations.append(f"placebo: new_effect={r2.new_effect:.4f}")
                if abs(r2.new_effect) > 0.1 * abs(estimate.value + 1e-9):
                    refutation_passed = False
            except Exception as exc:
                log.warning("refute.placebo.failed", error=str(exc))

        return CausalEffect(
            treatment=self.treatment,
            outcome=self.outcome,
            ate=float(estimate.value),
            p_value=getattr(estimate, "p_value", None),
            refutation_methods=refutations,
            refutation_passed=refutation_passed,
            method=method,
        )
