"""The decision engine — turns a forecast into an order, with reasons.

A forecast of 12,000 units is not a decision. The decision is *"raise a PO for
10,500 units, because the supplier now takes 21 days, you are holding 2,100
already, and you have told us to hit a 97% service level"*. That sentence is
what this module produces.

Everything here is deliberately pure and dependency-free (no SQLAlchemy, no
FastAPI) so the arithmetic can be unit tested and audited on its own. The
database-facing builder lives in :mod:`app.services.decision_builder`.

Method
------
Classic periodic-review order-up-to policy, run per SKU:

    protection window = supplier lead time + review period
    demand           = Σ p50 over the protection window
    σ                = pooled weekly σ implied by the p10/p90 band
    safety stock     = z(service level) · σ
    order-up-to      = demand + safety stock
    order            = round-up-to-MOQ( order-up-to − (on hand − reserved + inbound) )

The *baseline* we compare against is what the planner does in the spreadsheet
today: cover the pessimistic p90 case over the same window, with no statistical
pooling of variance. The gap between that and the policy order is the working
capital the system releases, and it is stored per recommendation so the ROI
ledger is auditable rather than asserted.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import NormalDist
from typing import Literal

from app.services.forecast_confidence import ConfidenceScore

DecisionKind = Literal["purchase_order", "excess_stock", "safety_stock_update"]
Urgency = Literal["critical", "high", "normal", "low"]

#: p90 − p10 spans this many standard deviations for a normal distribution.
#: Public because the scenario simulator derives weekly σ the same way.
P10_P90_SIGMA_SPAN = 2.5631031310892007
_P10_P90_SIGMA_SPAN = P10_P90_SIGMA_SPAN  # backwards-compatible alias

DEFAULT_SERVICE_LEVEL = 0.97
DEFAULT_REVIEW_PERIOD_DAYS = 28
DEFAULT_LEAD_TIME_DAYS = 14
DEFAULT_HOLDING_COST_PCT = 0.25  # annual, as a fraction of unit cost


@dataclass(frozen=True, slots=True)
class SkuEconomics:
    sku_id: str
    sku_code: str
    on_hand_units: float
    reserved_units: float = 0.0
    inbound_units: float = 0.0
    lead_time_days: int = DEFAULT_LEAD_TIME_DAYS
    moq: int = 1
    unit_cost: float = 0.0
    unit_price: float = 0.0
    currency: str = "INR"
    configured_safety_stock: int = 0
    #: False when the SKU has no recorded unit cost / price. A missing value is
    #: unknown, not free: money derived from it is reported as None, while a
    #: recorded 0 stays a known 0.
    cost_known: bool = True
    price_known: bool = True
    lead_time_assumed: bool = False

    @property
    def available_units(self) -> float:
        return max(0.0, self.on_hand_units - self.reserved_units)

    @property
    def position_units(self) -> float:
        """Stock we can count on covering future demand: available + on order."""
        return self.available_units + max(0.0, self.inbound_units)


@dataclass(frozen=True, slots=True)
class DemandBand:
    """Weekly probabilistic demand, ordered from the current week forward."""

    p10: list[float]
    p50: list[float]
    p90: list[float]

    def __post_init__(self) -> None:
        if not (len(self.p10) == len(self.p50) == len(self.p90)):
            raise ValueError("p10/p50/p90 must be the same length")

    @property
    def horizon_weeks(self) -> int:
        return len(self.p50)


@dataclass(frozen=True, slots=True)
class PolicyConfig:
    service_level: float = DEFAULT_SERVICE_LEVEL
    review_period_days: int = DEFAULT_REVIEW_PERIOD_DAYS
    holding_cost_pct: float = DEFAULT_HOLDING_COST_PCT
    #: Below this confidence score a recommendation is still produced but marked
    #: advisory — the user should look at the data before acting on it.
    min_confidence_to_act: int = 60


@dataclass(frozen=True, slots=True)
class Reason:
    """One driver of the recommendation, in the planner's language."""

    code: str
    text: str
    impact_units: float | None = None

    def as_dict(self) -> dict:
        return {"code": self.code, "text": self.text, "impact_units": self.impact_units}


@dataclass(frozen=True, slots=True)
class Decision:
    kind: DecisionKind
    sku_id: str
    sku_code: str
    headline: str
    recommended_units: int
    baseline_units: int
    urgency: Urgency
    confidence: int
    confidence_band: str
    reasons: list[Reason] = field(default_factory=list)
    economics: dict = field(default_factory=dict)
    inputs: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "sku_id": self.sku_id,
            "sku_code": self.sku_code,
            "headline": self.headline,
            "recommended_units": self.recommended_units,
            "baseline_units": self.baseline_units,
            "urgency": self.urgency,
            "confidence": self.confidence,
            "confidence_band": self.confidence_band,
            "reasons": [r.as_dict() for r in self.reasons],
            "economics": self.economics,
            "inputs": self.inputs,
        }


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _window_sum(weekly: list[float], days: float) -> float:
    """Sum a weekly series over ``days``, pro-rating the final partial week.

    Falls back to extending the last week's value when the requested window is
    longer than the forecast horizon — better than silently under-ordering.
    """
    if not weekly:
        return 0.0
    whole_weeks = int(days // 7)
    remainder = (days % 7) / 7.0
    total = 0.0
    for i in range(whole_weeks):
        total += weekly[i] if i < len(weekly) else weekly[-1]
    if remainder > 0:
        idx = whole_weeks
        total += (weekly[idx] if idx < len(weekly) else weekly[-1]) * remainder
    return total


def _pooled_sigma(band: DemandBand, days: float) -> float:
    """Standard deviation of total demand across the protection window.

    Weekly σ comes from the width of the p10–p90 band. Independent weeks pool as
    √(Σ σ²), which is why ordering for the *window* needs far less safety stock
    than ordering p90 every week — the core of the working-capital saving.
    """
    whole_weeks = int(days // 7)
    remainder = (days % 7) / 7.0
    var = 0.0

    def week_sigma(i: int) -> float:
        if not band.p90:
            return 0.0
        hi = band.p90[i] if i < len(band.p90) else band.p90[-1]
        lo = band.p10[i] if i < len(band.p10) else band.p10[-1]
        return max(0.0, (hi - lo) / _P10_P90_SIGMA_SPAN)

    for i in range(whole_weeks):
        var += week_sigma(i) ** 2
    if remainder > 0:
        var += (week_sigma(whole_weeks) ** 2) * remainder
    return math.sqrt(var)


def _round_to_moq(units: float, moq: int) -> int:
    if units <= 0:
        return 0
    m = max(1, int(moq))
    return int(math.ceil(units / m) * m)


def _z_for(service_level: float) -> float:
    sl = min(0.9999, max(0.50, float(service_level)))
    return NormalDist().inv_cdf(sl)


def _money(value: float, known: bool) -> float | None:
    return round(value, 2) if known else None


def _urgency(days_of_cover: float, lead_time_days: int) -> Urgency:
    if days_of_cover <= lead_time_days:
        return "critical"
    if days_of_cover <= lead_time_days + 14:
        return "high"
    if days_of_cover <= lead_time_days + 45:
        return "normal"
    return "low"


# ──────────────────────────────────────────────────────────────────────────────
# The engine
# ──────────────────────────────────────────────────────────────────────────────


def decide(
    *,
    sku: SkuEconomics,
    band: DemandBand,
    confidence: ConfidenceScore,
    policy: PolicyConfig | None = None,
    trailing_weekly_mean: float | None = None,
) -> list[Decision]:
    """Produce every decision this SKU warrants — usually zero or one.

    Returns a list because one SKU can simultaneously need an order (front of
    the horizon) and a safety-stock correction (a standing setting that is
    wrong). Callers that only want orders can filter on ``kind``.
    """
    policy = policy or PolicyConfig()
    decisions: list[Decision] = []

    lead_days = max(1, int(sku.lead_time_days or DEFAULT_LEAD_TIME_DAYS))
    protection_days = lead_days + max(0, int(policy.review_period_days))

    demand_p50 = _window_sum(band.p50, protection_days)
    demand_p90 = _window_sum(band.p90, protection_days)
    sigma = _pooled_sigma(band, protection_days)
    z = _z_for(policy.service_level)
    safety_units = z * sigma

    order_up_to = demand_p50 + safety_units
    position = sku.position_units
    raw_gap = order_up_to - position
    recommended = _round_to_moq(raw_gap, sku.moq)

    # The spreadsheet baseline: cover p90 for the whole window, no pooling.
    baseline = _round_to_moq(max(0.0, demand_p90 - position), sku.moq)

    weekly_p50 = band.p50[0] if band.p50 else 0.0
    daily = (sum(band.p50[:4]) / 4.0 / 7.0) if band.p50 else 0.0
    days_of_cover = (sku.available_units / daily) if daily > 0 else float("inf")

    # ── Purchase order ───────────────────────────────────────────────────────
    if recommended > 0:
        reasons = _order_reasons(
            sku=sku,
            policy=policy,
            lead_days=lead_days,
            protection_days=protection_days,
            demand_p50=demand_p50,
            safety_units=safety_units,
            position=position,
            recommended=recommended,
            raw_gap=raw_gap,
            confidence=confidence,
            trailing_weekly_mean=trailing_weekly_mean,
            weekly_p50=weekly_p50,
        )
        capital = recommended * sku.unit_cost
        baseline_capital = baseline * sku.unit_cost
        holding = capital * policy.holding_cost_pct * (protection_days / 365.0)
        unmet_without_order = max(0.0, demand_p50 - position)
        urgency = _urgency(days_of_cover, lead_days)

        decisions.append(
            Decision(
                kind="purchase_order",
                sku_id=sku.sku_id,
                sku_code=sku.sku_code,
                headline=f"Raise a purchase order for {recommended:,} units",
                recommended_units=recommended,
                baseline_units=baseline,
                urgency=urgency,
                confidence=confidence.score,
                confidence_band=confidence.band,
                reasons=reasons,
                economics={
                    "currency": sku.currency,
                    "capital_committed": _money(capital, sku.cost_known),
                    "baseline_capital": _money(baseline_capital, sku.cost_known),
                    "working_capital_released": _money(
                        max(0.0, baseline_capital - capital), sku.cost_known
                    ),
                    "holding_cost_over_window": _money(holding, sku.cost_known),
                    "revenue_protected": _money(
                        unmet_without_order * sku.unit_price, sku.price_known
                    ),
                    "units_at_risk_without_order": round(unmet_without_order, 1),
                },
                inputs=_inputs_blob(
                    sku, policy, lead_days, protection_days,
                    demand_p50, demand_p90, sigma, z, safety_units,
                    position, days_of_cover, band.horizon_weeks,
                ),
            )
        )

    # ── Excess stock ─────────────────────────────────────────────────────────
    # Holding more than twice the protection-window requirement is capital
    # sitting still. Only raised when there is genuinely a lot of it, so the
    # queue does not fill with rounding noise.
    elif position > order_up_to * 2 and position - order_up_to > max(10.0, sku.moq):
        excess = position - order_up_to
        excess_reasons = [
            Reason(
                "excess_position",
                f"You hold {position:,.0f} units against {order_up_to:,.0f} needed "
                f"through the next {protection_days} days",
                impact_units=excess,
            ),
        ]
        if sku.cost_known:
            excess_reasons.append(
                Reason(
                    "capital_locked",
                    f"{sku.currency} {excess * sku.unit_cost:,.0f} of working capital is "
                    f"tied up in stock you will not sell in that window",
                )
            )
        decisions.append(
            Decision(
                kind="excess_stock",
                sku_id=sku.sku_id,
                sku_code=sku.sku_code,
                headline=f"{excess:,.0f} units of excess stock — stop reordering, consider a markdown",
                recommended_units=0,
                baseline_units=0,
                urgency="low",
                confidence=confidence.score,
                confidence_band=confidence.band,
                reasons=excess_reasons,
                economics={
                    "currency": sku.currency,
                    "excess_units": round(excess, 1),
                    "capital_locked": _money(excess * sku.unit_cost, sku.cost_known),
                    "annual_holding_cost": _money(
                        excess * sku.unit_cost * policy.holding_cost_pct, sku.cost_known
                    ),
                },
                inputs=_inputs_blob(
                    sku, policy, lead_days, protection_days,
                    demand_p50, demand_p90, sigma, z, safety_units,
                    position, days_of_cover, band.horizon_weeks,
                ),
            )
        )

    # ── Standing safety-stock setting ────────────────────────────────────────
    # The configured value is what every other rule in the product keys off, so
    # a stale one quietly corrupts alerts and reorder points too.
    configured = float(sku.configured_safety_stock or 0)
    implied = safety_units
    if implied > 0 and abs(configured - implied) > max(5.0, implied * 0.35):
        direction = "raise" if implied > configured else "lower"
        decisions.append(
            Decision(
                kind="safety_stock_update",
                sku_id=sku.sku_id,
                sku_code=sku.sku_code,
                headline=(
                    f"{direction.capitalize()} safety stock from {configured:,.0f} "
                    f"to {implied:,.0f} units"
                ),
                recommended_units=int(round(implied)),
                baseline_units=int(round(configured)),
                urgency="low",
                confidence=confidence.score,
                confidence_band=confidence.band,
                reasons=[
                    Reason(
                        "service_level_math",
                        f"A {policy.service_level:.0%} service level over a {protection_days}-day "
                        f"protection window needs {implied:,.0f} units of buffer "
                        f"(z={z:.2f} × σ={sigma:,.0f})",
                        impact_units=implied - configured,
                    ),
                    Reason(
                        "current_setting",
                        f"The SKU is currently configured for {configured:,.0f} units, "
                        f"which {'under' if implied > configured else 'over'}-protects it",
                    ),
                ],
                economics={
                    "currency": sku.currency,
                    "capital_delta": _money((implied - configured) * sku.unit_cost, sku.cost_known),
                },
                inputs=_inputs_blob(
                    sku, policy, lead_days, protection_days,
                    demand_p50, demand_p90, sigma, z, safety_units,
                    position, days_of_cover, band.horizon_weeks,
                ),
            )
        )

    return decisions


def _order_reasons(
    *,
    sku: SkuEconomics,
    policy: PolicyConfig,
    lead_days: int,
    protection_days: int,
    demand_p50: float,
    safety_units: float,
    position: float,
    recommended: int,
    raw_gap: float,
    confidence: ConfidenceScore,
    trailing_weekly_mean: float | None,
    weekly_p50: float,
) -> list[Reason]:
    reasons = [
        Reason(
            "protection_window",
            f"Supplier lead time is {lead_days} days and you review orders every "
            f"{policy.review_period_days} days, so this order has to cover "
            f"{protection_days} days of demand",
        ),
        Reason(
            "forecast_demand",
            f"Forecast demand over that window is {demand_p50:,.0f} units",
            impact_units=demand_p50,
        ),
        Reason(
            "service_level",
            f"Your {policy.service_level:.0%} service-level target adds "
            f"{safety_units:,.0f} units of safety stock",
            impact_units=safety_units,
        ),
    ]

    if position > 0:
        reasons.append(
            Reason(
                "current_position",
                f"You already hold {sku.available_units:,.0f} available"
                + (f" with {sku.inbound_units:,.0f} inbound" if sku.inbound_units > 0 else ""),
                impact_units=-position,
            )
        )

    if recommended > raw_gap + 0.5 and sku.moq > 1:
        reasons.append(
            Reason(
                "moq_rounding",
                f"Rounded up from {raw_gap:,.0f} to meet the supplier MOQ of {sku.moq:,}",
                impact_units=recommended - raw_gap,
            )
        )

    if trailing_weekly_mean is not None and trailing_weekly_mean > 0:
        change = (weekly_p50 - trailing_weekly_mean) / trailing_weekly_mean
        if abs(change) >= 0.12:
            direction = "up" if change > 0 else "down"
            reasons.append(
                Reason(
                    "demand_trend",
                    f"Weekly demand is trending {direction} {abs(change):.0%} versus the "
                    f"trailing average",
                )
            )

    if sku.cost_known and sku.unit_cost > 0:
        reasons.append(
            Reason(
                "carrying_cost",
                f"Carrying this order for {protection_days} days costs about "
                f"{sku.currency} "
                f"{recommended * sku.unit_cost * policy.holding_cost_pct * protection_days / 365:,.0f}"
                f" at a {policy.holding_cost_pct:.0%} annual holding rate",
            )
        )

    if confidence.score < policy.min_confidence_to_act:
        reasons.append(
            Reason(
                "low_confidence",
                f"Forecast confidence is only {confidence.score}% — "
                + ("; ".join(confidence.reasons[:2]) if confidence.reasons else "review before ordering"),
            )
        )

    return reasons


def _inputs_blob(
    sku: SkuEconomics,
    policy: PolicyConfig,
    lead_days: int,
    protection_days: int,
    demand_p50: float,
    demand_p90: float,
    sigma: float,
    z: float,
    safety_units: float,
    position: float,
    days_of_cover: float,
    horizon_weeks: int,
) -> dict:
    """Every number the recommendation was derived from, so the UI can show the
    working and a later audit can reproduce it exactly."""
    return {
        "lead_time_days": lead_days,
        "review_period_days": policy.review_period_days,
        "protection_days": protection_days,
        "service_level": policy.service_level,
        "z": round(z, 4),
        "demand_p50_over_window": round(demand_p50, 2),
        "demand_p90_over_window": round(demand_p90, 2),
        "sigma_over_window": round(sigma, 2),
        "safety_stock_units": round(safety_units, 2),
        "order_up_to": round(demand_p50 + safety_units, 2),
        "on_hand_units": round(sku.on_hand_units, 2),
        "reserved_units": round(sku.reserved_units, 2),
        "inbound_units": round(sku.inbound_units, 2),
        "position_units": round(position, 2),
        "days_of_cover": None if days_of_cover == float("inf") else round(days_of_cover, 1),
        "moq": sku.moq,
        "unit_cost": sku.unit_cost if sku.cost_known else None,
        "unit_price": sku.unit_price if sku.price_known else None,
        "lead_time_assumed": sku.lead_time_assumed,
        "forecast_horizon_weeks": horizon_weeks,
        "holding_cost_pct": policy.holding_cost_pct,
    }
