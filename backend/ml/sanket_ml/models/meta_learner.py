"""Auto model selector: picks the best-performing model per SKU based on MAPE.

Used by the forecast accuracy router to surface recommended models and by
the training pipeline to optionally thin the ensemble to top-N models.
"""
from __future__ import annotations

import structlog

log = structlog.get_logger(__name__)

FALLBACK_MODEL = "ensemble"


class AutoModelSelector:
    """Stateless selector — reads a metrics dict, returns the winner."""

    def select(self, metrics: dict[str, float]) -> str:
        """
        metrics: {model_name: mape} — lower MAPE is better.
        Returns the model name with the lowest finite MAPE, or FALLBACK_MODEL.
        """
        if not metrics:
            return FALLBACK_MODEL

        valid = {k: v for k, v in metrics.items() if v is not None and v == v and v >= 0}
        if not valid:
            return FALLBACK_MODEL

        best = min(valid, key=lambda k: valid[k])
        log.debug("auto_model.selected", model=best, mape=valid[best])
        return best

    def rank(self, metrics: dict[str, float]) -> list[tuple[str, float]]:
        """Return models sorted best→worst by MAPE."""
        valid = [(k, v) for k, v in metrics.items() if v is not None and v == v and v >= 0]
        return sorted(valid, key=lambda x: x[1])

    def top_n(self, metrics: dict[str, float], n: int = 3) -> list[str]:
        """Return top-N model names for ensemble pruning."""
        ranked = self.rank(metrics)
        return [name for name, _ in ranked[:n]] or [FALLBACK_MODEL]
