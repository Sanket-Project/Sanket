from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import structlog

from sanket_ml.data.features import add_intermittency_flags

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ModelChoice:
    unique_id: str
    chosen_model: str
    demand_class: str
    reason: str


def route_by_demand_class(
    panel: pd.DataFrame,
    available_models: list[str],
    *,
    intermittent_preference: tuple[str, ...] = ("croston", "tft"),
    smooth_preference: tuple[str, ...] = ("timesfm", "tft", "lightgbm"),
    erratic_preference: tuple[str, ...] = ("lightgbm", "chronos", "tft"),
    lumpy_preference: tuple[str, ...] = ("croston", "lightgbm"),
) -> list[ModelChoice]:
    """Heuristic per-series model router based on Syntetos-Boylan classification.

    Returns one choice per unique series. Caller can then route each series
    to its preferred model — this is what powers the meta-ensemble where
    different SKUs use different stacks.
    """
    classified = add_intermittency_flags(panel.drop_duplicates("unique_id"))
    decisions: list[ModelChoice] = []
    available = set(available_models)
    for _, row in classified.iterrows():
        cls = row["demand_class"]
        prefs = {
            "smooth": smooth_preference,
            "intermittent": intermittent_preference,
            "erratic": erratic_preference,
            "lumpy": lumpy_preference,
            "all_zero": ("seasonal_naive",),
        }.get(cls, smooth_preference)
        chosen = next((m for m in prefs if m in available), available_models[0] if available_models else "lightgbm")
        decisions.append(
            ModelChoice(
                unique_id=str(row["unique_id"]),
                chosen_model=chosen,
                demand_class=cls,
                reason=f"adi={row['adi']:.2f}, cv2={row['cv2']:.2f} → {cls}",
            )
        )
    return decisions
