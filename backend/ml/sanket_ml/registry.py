from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sanket_ml.models.base import BaseForecaster


@dataclass(frozen=True, slots=True)
class ModelSpec:
    name: str
    factory: Callable[..., BaseForecaster]
    family: str  # "statistical" | "gbt" | "deep" | "foundation"
    requires_gpu: bool = False
    supports_probabilistic: bool = True
    supports_covariates: bool = True
    intermittent_friendly: bool = False
    cold_start_friendly: bool = False  # works on tiny histories
    default_weight: float = 1.0


# ──────────────────────────────────────────────────────────────────────────
# Registry — populated lazily by submodule imports to avoid heavy imports
# at top level.
# ──────────────────────────────────────────────────────────────────────────

_REGISTRY: dict[str, ModelSpec] = {}


def register(spec: ModelSpec) -> None:
    if spec.name in _REGISTRY:
        raise ValueError(f"Model '{spec.name}' already registered")
    _REGISTRY[spec.name] = spec


def get(name: str) -> ModelSpec:
    if name not in _REGISTRY:
        _bootstrap()
    if name not in _REGISTRY:
        raise KeyError(f"Unknown model: {name}. Registered: {sorted(_REGISTRY)}")
    return _REGISTRY[name]


def list_all() -> list[str]:
    if not _REGISTRY:
        _bootstrap()
    return sorted(_REGISTRY)


def _bootstrap() -> None:
    # Lazy import each model wrapper. Each module calls register() at import time.
    from sanket_ml.models.deep import deepar, nhits, tft  # noqa: F401
    from sanket_ml.models.foundation import chronos, lag_llama, moirai, timesfm  # noqa: F401
    from sanket_ml.models.gradient_boost import lightgbm_forecaster  # noqa: F401
    from sanket_ml.models.statistical import croston, ets, naive  # noqa: F401


# ──────────────────────────────────────────────────────────────────────────
# Per-industry default stacks
# ──────────────────────────────────────────────────────────────────────────

INDUSTRY_STACKS: dict[str, list[str]] = {
    "fashion": ["lightgbm", "chronos"],
    "electronics": ["timesfm", "chronos", "deepar", "tft", "lightgbm"],
    "pharma": ["tft", "croston", "nhits", "lightgbm", "chronos"],
}


def stack_for(industry: str) -> list[ModelSpec]:
    names = INDUSTRY_STACKS.get(industry)
    if names is None:
        raise KeyError(f"No stack defined for industry: {industry}")
    return [get(n) for n in names]
