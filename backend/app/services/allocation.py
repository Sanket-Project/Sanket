"""DC→store allocation (location spec §5.2). Pure.

Every store is lifted toward its target. When the DC cannot cover every need,
stock is rationed by equal days of cover (water-filling) so no store runs out
first; quantities are packs (``moq``) and never exceed supply.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StoreNeed:
    location: str
    position: float
    target: float
    daily_rate: float

    @property
    def need(self) -> float:
        return max(0.0, self.target - self.position)


def _fill(s: StoreNeed, level: float) -> float:
    return min(s.need, max(0.0, level * s.daily_rate - s.position))


def cover_level(stores: list[StoreNeed], supply: float) -> float:
    live = [s for s in stores if s.daily_rate > 0 and s.need > 0]
    if not live:
        return 0.0
    lo, hi = 0.0, max((s.position + s.need) / s.daily_rate for s in live)
    for _ in range(100):
        mid = (lo + hi) / 2
        if sum(_fill(s, mid) for s in live) > supply:
            hi = mid
        else:
            lo = mid
    return lo


def _round(raw: dict[str, float], cap: int, moq: int) -> dict[str, int]:
    base = {k: int(math.floor(v / moq)) * moq for k, v in raw.items()}
    left = (cap - sum(base.values())) // moq
    for k in sorted(raw, key=lambda k: raw[k] - base[k], reverse=True):
        if left <= 0:
            break
        if raw[k] - base[k] > 0:
            base[k] += moq
            left -= 1
    return base


def allocate(
    stores: list[StoreNeed], supply: float, moq: int = 1, min_units: int = 1
) -> dict[str, int]:
    moq = max(1, int(moq))
    cap = max(0, int(math.floor(supply)))
    if cap == 0:
        return {}
    needs = {s.location: s.need for s in stores if s.need > 0 and s.daily_rate > 0}
    rounded_up = {k: int(math.ceil(v / moq)) * moq for k, v in needs.items()}
    if sum(rounded_up.values()) <= cap:
        out = rounded_up
    else:
        level = cover_level(stores, cap)
        raw = {s.location: _fill(s, level) for s in stores if s.daily_rate > 0 and s.need > 0}
        out = _round(raw, cap, moq)
    return {k: v for k, v in out.items() if v > 0 and v >= min_units}
