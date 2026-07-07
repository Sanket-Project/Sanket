"""Base types shared across signal connectors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class SignalSample:
    """A single normalized signal observation produced by a connector.

    All connectors emit this shape so downstream fusion can stay source-agnostic.
    `normalized_score ∈ [-1, +1]` is the platform-unified momentum metric.
    """

    source: str  # 'fred' | 'google_trends' | 'reddit' | 'synthetic'
    kind: str  # 'economic_indicator' | 'social_buzz' | ...
    series_key: str  # stable identifier (e.g. 'CPIAUCSL', 'google:winter_jacket')
    industry: str  # 'fashion' | 'electronics' | 'pharma'
    captured_at: datetime
    raw_value: float | None
    normalized_score: float
    confidence: float = 1.0
    category_tags: list[str] = field(default_factory=list)
    sku_tags: list[str] = field(default_factory=list)
    region: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


class SignalConnector(ABC):
    """Abstract base — every external API connector implements `fetch()`.

    Connectors must NEVER raise on network errors; they return an empty list and
    log instead. Pipeline must remain resilient when individual sources fail.
    """

    name: str = "abstract"

    @abstractmethod
    async def fetch(self, industry: str) -> list[SignalSample]:
        """Return current signal samples relevant to the given industry."""
        ...


def clip(value: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, value))


def z_to_score(z: float, scale: float = 2.5) -> float:
    """Map a z-score to [-1, +1] via tanh — gentle saturation past ±scale·σ."""
    import math

    return math.tanh(z / scale)
