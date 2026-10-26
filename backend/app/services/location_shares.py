"""share_split_v1: split a SKU forecast across locations (location spec §4.1–§4.2).

Pure functions only — the database service in ``location_forecast`` feeds them.

* A location's **rate** is its recency-weighted units per in-stock week; weeks
  it was out of stock are dropped from both sums, so lost sales never shrink
  its share. A week with no sales row is an observed zero.
* Unassigned sales (no location) have their own rate over every week and are
  held back: location shares sum to ``1 − unassigned``.
* Sparse SKUs are shrunk toward their category's shares with weight
  ``n / (n + k)``, where ``n`` is the weighted number of weeks with SKU sales.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

WINDOW_WEEKS = 12
HALF_LIFE_WEEKS = 4.0
SHRINK_K = 4.0
Z90 = 1.2816
_SKU_HISTORY_MIN_WEIGHT = 0.9


@dataclass(frozen=True, slots=True)
class WeekObs:
    week: date
    location: str | None
    units: float
    in_stock: bool | None = None


@dataclass(frozen=True, slots=True)
class ShareResult:
    shares: dict[str, float]
    basis: dict[str, str] = field(default_factory=dict)
    unassigned: float = 0.0
    evidence_weeks: float = 0.0


def _weights(weeks: list[date]) -> dict[date, float]:
    newest = max(weeks)
    return {w: 0.5 ** (((newest - w).days // 7) / HALF_LIFE_WEEKS) for w in weeks}


def rates(obs: list[WeekObs], weeks: list[date]) -> tuple[dict[str, float], float, float]:
    """(rate per location, unassigned rate, evidence weeks) over ``weeks``."""
    if not weeks:
        return {}, 0.0, 0.0
    w = _weights(weeks)
    units: dict[str | None, dict[date, float]] = defaultdict(lambda: defaultdict(float))
    oos: dict[str, set[date]] = defaultdict(set)
    sold_weeks: set[date] = set()
    for o in obs:
        if o.week not in w:
            continue
        units[o.location][o.week] += float(o.units)
        if o.location is not None and o.in_stock is False:
            oos[o.location].add(o.week)
        if o.units > 0:
            sold_weeks.add(o.week)

    loc_rates: dict[str, float] = {}
    for loc, by_week in units.items():
        if loc is None:
            continue
        in_stock_weeks = [wk for wk in weeks if wk not in oos[loc]]
        denom = sum(w[wk] for wk in in_stock_weeks)
        if denom <= 0:
            continue
        loc_rates[loc] = sum(w[wk] * by_week.get(wk, 0.0) for wk in in_stock_weeks) / denom
    total_w = sum(w.values())
    unassigned_rate = sum(w[wk] * u for wk, u in units.get(None, {}).items()) / total_w
    evidence = sum(w[wk] for wk in sold_weeks)
    return loc_rates, unassigned_rate, evidence


def shares_from_obs(obs: list[WeekObs], weeks: list[date]) -> ShareResult:
    loc_rates, un_rate, evidence = rates(obs, weeks)
    total = sum(loc_rates.values()) + un_rate
    if total <= 0:
        return ShareResult(shares={}, unassigned=0.0, evidence_weeks=0.0)
    return ShareResult(
        shares={l: r / total for l, r in loc_rates.items() if r > 0},
        basis={l: "sku_history" for l, r in loc_rates.items() if r > 0},
        unassigned=un_rate / total,
        evidence_weeks=evidence,
    )


def blend_shares(
    sku: ShareResult | None, category: ShareResult | None, k: float = SHRINK_K
) -> ShareResult:
    """Shrink SKU shares toward category shares; renormalise to ``1 − unassigned``."""
    n = sku.evidence_weeks if sku else 0.0
    if n <= 0:
        if not category or not category.shares:
            return ShareResult(shares={})
        return ShareResult(
            shares=dict(category.shares),
            basis={l: "category_prior" for l in category.shares},
            unassigned=category.unassigned,
            evidence_weeks=0.0,
        )
    lam = n / (n + k)
    cat = category.shares if category else {}
    locs = set(sku.shares) | set(cat)
    raw = {l: lam * sku.shares.get(l, 0.0) + (1 - lam) * cat.get(l, 0.0) for l in locs}
    raw = {l: v for l, v in raw.items() if v > 0}
    target = 1.0 - sku.unassigned
    scale = target / sum(raw.values()) if raw else 0.0
    if lam >= _SKU_HISTORY_MIN_WEIGHT:
        label = "sku_history"
    elif cat:
        label = "blended"
    else:
        label = "sku_history"
    return ShareResult(
        shares={l: v * scale for l, v in raw.items()},
        basis={l: label for l in raw},
        unassigned=sku.unassigned,
        evidence_weeks=n,
    )


def split_week(p10: float, p50: float, p90: float, share: float) -> tuple[float, float, float]:
    """Location quantiles for one week (multinomial thinning, spec §4.2)."""
    s = min(1.0, max(0.0, float(share)))
    sigma = max(0.0, float(p90) - float(p10)) / (2 * Z90)
    var = s * s * sigma * sigma + s * (1 - s) * max(0.0, float(p50))
    sd = math.sqrt(var)
    lp50 = s * float(p50)
    return max(0.0, lp50 - Z90 * sd), lp50, lp50 + Z90 * sd
