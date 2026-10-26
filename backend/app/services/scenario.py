"""Digital twin — a weekly simulation of the supply chain under a scenario.

"What if sales jump 30%?" / "What if supplier A fails?" / "What if the port
strikes?" / "What if tariffs go up?" are all the same question with different
levers, and none of them can be answered by scaling a forecast line. Whether a
demand surge actually costs you anything depends on how much stock you hold,
how long the supplier takes, when your next review cycle lands, and whether the
order you place arrives before the demand does.

So this module *simulates* rather than scales: for every SKU it runs the real
inventory recursion week by week — arrivals, demand, shortfall, review, reorder
— once for the baseline and once with the scenario's levers applied, and reports
the difference. The levers move physical parameters (demand, lead time, cost,
supplier availability), never the outputs.

Pure and dependency-free; :func:`run` in ``scenario_runner`` supplies real data.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from statistics import NormalDist
from typing import Any, Literal

from app.services.decision_engine import (
    DEFAULT_HOLDING_COST_PCT,
    DEFAULT_SERVICE_LEVEL,
    P10_P90_SIGMA_SPAN,
    DemandBand,
    SkuEconomics,
)

LeverKind = Literal[
    "demand_shock",
    "price_change",
    "lead_time_delta",
    "supplier_outage",
    "cost_change",
    "service_level",
]

#: How much demand moves for a 1% price move. −1.2 is a middle-of-the-road
#: retail own-price elasticity; tenants can override per scenario.
DEFAULT_PRICE_ELASTICITY = -1.2
DEFAULT_REVIEW_WEEKS = 4


@dataclass(frozen=True, slots=True)
class Scenario:
    """The levers. Every field is a physical change to the world, not to a KPI."""

    name: str = "Custom scenario"
    #: Percent change in underlying demand, e.g. +30 for a 30% surge.
    demand_shock_pct: float = 0.0
    #: Percent change in selling price. Moves demand through the elasticity.
    price_change_pct: float = 0.0
    price_elasticity: float = DEFAULT_PRICE_ELASTICITY
    #: Extra days on every supplier lead time (port strike, customs backlog).
    lead_time_delta_days: int = 0
    #: Percent change in unit cost (tariffs, commodity moves, FX).
    cost_change_pct: float = 0.0
    #: Weeks during which no replenishment arrives at all (supplier failure).
    supplier_outage_weeks: int = 0
    #: Restrict the outage to specific SKUs; empty means the whole portfolio.
    supplier_outage_sku_ids: tuple[str, ...] = ()
    #: Override the service level the reorder policy targets.
    service_level: float | None = None
    #: Ramp the demand shock in linearly over this many weeks (0 = immediate).
    ramp_weeks: int = 0

    def is_noop(self) -> bool:
        return not any(
            (
                self.demand_shock_pct,
                self.price_change_pct,
                self.lead_time_delta_days,
                self.cost_change_pct,
                self.supplier_outage_weeks,
                self.service_level is not None,
            )
        )


@dataclass(frozen=True, slots=True)
class SimConfig:
    horizon_weeks: int = 26
    review_weeks: int = DEFAULT_REVIEW_WEEKS
    holding_cost_pct: float = DEFAULT_HOLDING_COST_PCT
    service_level: float = DEFAULT_SERVICE_LEVEL


@dataclass
class SkuOutcome:
    sku_id: str
    sku_code: str
    demand_units: float = 0.0
    shipped_units: float = 0.0
    short_units: float = 0.0
    weeks_stocked_out: int = 0
    first_stockout_week: int | None = None
    avg_inventory_units: float = 0.0
    peak_inventory_units: float = 0.0
    ordered_units: float = 0.0
    #: Money is None when the SKU's unit price or cost is unknown — a missing
    #: cost is not free stock.
    revenue: float | None = 0.0
    gross_margin: float | None = 0.0
    order_cost: float | None = 0.0
    holding_cost: float | None = 0.0
    weekly_on_hand: list[float] = field(default_factory=list)
    weekly_demand: list[float] = field(default_factory=list)

    @property
    def fill_rate(self) -> float:
        return (self.shipped_units / self.demand_units) if self.demand_units > 0 else 1.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "sku_id": self.sku_id,
            "sku_code": self.sku_code,
            "demand_units": round(self.demand_units, 1),
            "shipped_units": round(self.shipped_units, 1),
            "short_units": round(self.short_units, 1),
            "fill_rate": round(self.fill_rate, 4),
            "weeks_stocked_out": self.weeks_stocked_out,
            "first_stockout_week": self.first_stockout_week,
            "avg_inventory_units": round(self.avg_inventory_units, 1),
            "peak_inventory_units": round(self.peak_inventory_units, 1),
            "ordered_units": round(self.ordered_units, 1),
            "revenue": _round(self.revenue),
            "gross_margin": _round(self.gross_margin),
            "order_cost": _round(self.order_cost),
            "holding_cost": _round(self.holding_cost),
        }


def _round(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(value, digits)


def _sum(values: list[float | None], digits: int = 2) -> float | None:
    """Portfolio money: None when any SKU's figure is unknown, because a sum of
    only the valued SKUs would read as the whole portfolio."""
    if any(v is None for v in values):
        return None
    return round(sum(values), digits)  # type: ignore[arg-type]


def _diff(a: float | None, b: float | None, digits: int = 2) -> float | None:
    return None if a is None or b is None else round(a - b, digits)


def apply_levers(
    band: DemandBand, sku: SkuEconomics, scenario: Scenario, horizon: int
) -> tuple[list[float], list[float], int, float, float]:
    """Translate levers into the physical inputs of the simulation.

    Returns ``(weekly_demand, weekly_sigma, lead_time_days, unit_cost, unit_price)``.
    The forecast is never extended past its last week: callers cap ``horizon``
    to the weeks the model actually produced.
    """
    if horizon > len(band.p50):
        raise ValueError(
            f"Horizon of {horizon} weeks exceeds the {len(band.p50)}-week forecast; "
            "weeks beyond the forecast would be invented."
        )
    demand: list[float] = []
    sigma: list[float] = []

    price_mult = 1.0 + scenario.price_change_pct / 100.0
    # Constant-elasticity response: a 10% price cut with ε = −1.2 lifts volume
    # by about 12%. Clamped so an extreme lever cannot produce negative demand.
    elasticity_mult = max(0.05, price_mult ** scenario.price_elasticity) if price_mult > 0 else 1.0

    for w in range(horizon):
        base, hi, lo = band.p50[w], band.p90[w], band.p10[w]

        shock = scenario.demand_shock_pct / 100.0
        if scenario.ramp_weeks > 0:
            shock *= min(1.0, (w + 1) / scenario.ramp_weeks)
        mult = (1.0 + shock) * elasticity_mult

        demand.append(max(0.0, base * mult))
        sigma.append(max(0.0, (hi - lo) / P10_P90_SIGMA_SPAN * mult))

    lead = max(1, int(sku.lead_time_days) + int(scenario.lead_time_delta_days))
    cost = sku.unit_cost * (1.0 + scenario.cost_change_pct / 100.0)
    price = sku.unit_price * price_mult
    return demand, sigma, lead, cost, price


def simulate_sku(
    *,
    sku: SkuEconomics,
    band: DemandBand,
    scenario: Scenario,
    config: SimConfig,
) -> SkuOutcome:
    """Run the weekly inventory recursion for one SKU under one scenario."""
    horizon = max(1, config.horizon_weeks)
    demand, sigma, lead_days, unit_cost, unit_price = apply_levers(band, sku, scenario, horizon)

    lead_weeks = max(1, int(math.ceil(lead_days / 7)))
    service = scenario.service_level if scenario.service_level is not None else config.service_level
    z = NormalDist().inv_cdf(min(0.9999, max(0.50, service)))

    outage = scenario.supplier_outage_weeks
    if outage and scenario.supplier_outage_sku_ids:
        if sku.sku_id not in scenario.supplier_outage_sku_ids:
            outage = 0

    on_hand = sku.available_units
    # Stock already on order is modelled as arriving at the end of the current
    # lead time — the position a real planner is holding on day one.
    pipeline: dict[int, float] = {}
    if sku.inbound_units > 0:
        pipeline[min(horizon - 1, lead_weeks - 1)] = sku.inbound_units

    out = SkuOutcome(sku_id=sku.sku_id, sku_code=sku.sku_code)
    inv_sum = 0.0

    for w in range(horizon):
        # Arrivals — suppressed entirely while the supplier is down.
        if w >= outage:
            on_hand += pipeline.pop(w, 0.0)
        elif w in pipeline:
            # Delayed, not lost: the shipment lands the week the outage ends.
            pipeline[outage] = pipeline.pop(w) + pipeline.get(outage, 0.0)

        d = demand[w]
        shipped = min(on_hand, d)
        short = d - shipped
        on_hand -= shipped

        out.demand_units += d
        out.shipped_units += shipped
        out.short_units += short
        if short > 0.001:
            out.weeks_stocked_out += 1
            if out.first_stockout_week is None:
                out.first_stockout_week = w

        inv_sum += on_hand
        out.peak_inventory_units = max(out.peak_inventory_units, on_hand)
        out.weekly_on_hand.append(round(on_hand, 1))
        out.weekly_demand.append(round(d, 1))

        # Periodic review: place an order to bring the position back up.
        if w % max(1, config.review_weeks) == 0 and w >= outage:
            protection = lead_weeks + config.review_weeks
            expected = sum(demand[w : w + protection]) or (d * protection)
            var = sum(s**2 for s in sigma[w : w + protection])
            target = expected + z * math.sqrt(var)
            position = on_hand + sum(pipeline.values())
            gap = target - position
            if gap > 0:
                qty = math.ceil(gap / max(1, sku.moq)) * max(1, sku.moq)
                arrival = w + lead_weeks
                if arrival < horizon:
                    pipeline[arrival] = pipeline.get(arrival, 0.0) + qty
                out.ordered_units += qty

    out.avg_inventory_units = inv_sum / horizon
    out.revenue = out.shipped_units * unit_price if sku.price_known else None
    out.gross_margin = (
        out.shipped_units * (unit_price - unit_cost)
        if sku.price_known and sku.cost_known
        else None
    )
    out.order_cost = out.ordered_units * unit_cost if sku.cost_known else None
    out.holding_cost = (
        out.avg_inventory_units * unit_cost * config.holding_cost_pct * (horizon / 52.0)
        if sku.cost_known
        else None
    )
    return out


def _portfolio(outcomes: list[SkuOutcome], currency: str) -> dict[str, Any]:
    demand = sum(o.demand_units for o in outcomes)
    shipped = sum(o.shipped_units for o in outcomes)
    short = sum(o.short_units for o in outcomes)
    return {
        "currency": currency,
        "skus": len(outcomes),
        "demand_units": round(demand, 0),
        "shipped_units": round(shipped, 0),
        "short_units": round(short, 0),
        "fill_rate": round((shipped / demand) if demand > 0 else 1.0, 4),
        "skus_stocking_out": sum(1 for o in outcomes if o.weeks_stocked_out > 0),
        "revenue": _sum([o.revenue for o in outcomes]),
        "gross_margin": _sum([o.gross_margin for o in outcomes]),
        # Filled in by `compare`, which knows each SKU's price under the scenario.
        "lost_revenue": 0.0,
        "avg_inventory_units": round(sum(o.avg_inventory_units for o in outcomes), 0),
        "peak_inventory_units": round(sum(o.peak_inventory_units for o in outcomes), 0),
        "units_ordered": round(sum(o.ordered_units for o in outcomes), 0),
        "purchase_spend": _sum([o.order_cost for o in outcomes]),
        "holding_cost": _sum([o.holding_cost for o in outcomes]),
    }


def compare(
    *,
    skus: list[SkuEconomics],
    bands: dict[str, DemandBand],
    scenario: Scenario,
    config: SimConfig,
    currency: str = "INR",
) -> dict[str, Any]:
    """Run baseline and scenario, and report the delta.

    The baseline is the *same simulation* with no levers, so every difference
    is attributable to the scenario rather than to modelling choices.
    """
    base_scenario = Scenario(name="Baseline", price_elasticity=scenario.price_elasticity)

    simulated = [sk for sk in skus if bands.get(sk.sku_id) is not None and bands[sk.sku_id].p50]
    available = min((len(bands[sk.sku_id].p50) for sk in simulated), default=0)
    requested = config.horizon_weeks
    capped_reason = None
    if simulated and requested > available:
        capped_reason = (
            f"The forecast covers {available} weeks, so the simulation stops at {available} weeks "
            f"instead of the {requested} requested. Weeks beyond the forecast are not invented."
        )
        config = replace(config, horizon_weeks=available)

    base_out: list[SkuOutcome] = []
    scen_out: list[SkuOutcome] = []
    per_sku: list[dict[str, Any]] = []

    for sku in skus:
        band = bands.get(sku.sku_id)
        if band is None or not band.p50:
            continue
        b = simulate_sku(sku=sku, band=band, scenario=base_scenario, config=config)
        s = simulate_sku(sku=sku, band=band, scenario=scenario, config=config)
        base_out.append(b)
        scen_out.append(s)
        per_sku.append(
            {
                "sku_id": sku.sku_id,
                "sku_code": sku.sku_code,
                "baseline": b.as_dict(),
                "scenario": s.as_dict(),
                "delta": {
                    "fill_rate": round(s.fill_rate - b.fill_rate, 4),
                    "short_units": round(s.short_units - b.short_units, 1),
                    "revenue": _diff(s.revenue, b.revenue),
                    "gross_margin": _diff(s.gross_margin, b.gross_margin),
                    "units_ordered": round(s.ordered_units - b.ordered_units, 1),
                    "purchase_spend": _diff(s.order_cost, b.order_cost),
                    "avg_inventory_units": round(
                        s.avg_inventory_units - b.avg_inventory_units, 1
                    ),
                },
                "weekly": {
                    "demand": s.weekly_demand,
                    "on_hand": s.weekly_on_hand,
                    "baseline_on_hand": b.weekly_on_hand,
                },
            }
        )

    base_totals = _portfolio(base_out, currency)
    scen_totals = _portfolio(scen_out, currency)

    # Unmet demand valued at the scenario's selling price, computed per SKU
    # because prices differ (a portfolio-average price would be meaningless).
    def lost(
        outcomes: list[SkuOutcome], sku_map: dict[str, SkuEconomics], mult: float
    ) -> float | None:
        return _sum([
            o.short_units * (sku_map[o.sku_id].unit_price * mult)
            if sku_map[o.sku_id].price_known else None
            for o in outcomes
            if o.sku_id in sku_map
        ])

    sku_map = {s.sku_id: s for s in skus}
    price_mult = 1.0 + scenario.price_change_pct / 100.0
    base_totals["lost_revenue"] = lost(base_out, sku_map, 1.0)
    scen_totals["lost_revenue"] = lost(scen_out, sku_map, price_mult)

    # Unvalued SKUs sort by units short instead of margin, after the valued ones.
    per_sku.sort(
        key=lambda r: (
            r["delta"]["gross_margin"] is None,
            r["delta"]["gross_margin"] or 0.0,
            -r["delta"]["short_units"],
        )
    )

    return {
        "scenario": {
            "name": scenario.name,
            "demand_shock_pct": scenario.demand_shock_pct,
            "price_change_pct": scenario.price_change_pct,
            "price_elasticity": scenario.price_elasticity,
            "lead_time_delta_days": scenario.lead_time_delta_days,
            "cost_change_pct": scenario.cost_change_pct,
            "supplier_outage_weeks": scenario.supplier_outage_weeks,
            "supplier_outage_sku_ids": list(scenario.supplier_outage_sku_ids),
            "service_level": scenario.service_level,
            "ramp_weeks": scenario.ramp_weeks,
        },
        "config": {
            "horizon_weeks": config.horizon_weeks,
            "requested_horizon_weeks": requested,
            "forecast_weeks_available": available,
            "horizon_capped_reason": capped_reason,
            "review_weeks": config.review_weeks,
            "holding_cost_pct": config.holding_cost_pct,
            "service_level": config.service_level,
        },
        "baseline": base_totals,
        "result": scen_totals,
        "impact": {
            "fill_rate_pts": round(
                (scen_totals["fill_rate"] - base_totals["fill_rate"]) * 100, 2
            ),
            "revenue": _diff(scen_totals["revenue"], base_totals["revenue"]),
            "gross_margin": _diff(scen_totals["gross_margin"], base_totals["gross_margin"]),
            "lost_revenue": _diff(scen_totals["lost_revenue"], base_totals["lost_revenue"]),
            "purchase_spend": _diff(scen_totals["purchase_spend"], base_totals["purchase_spend"]),
            "avg_inventory_units": round(
                scen_totals["avg_inventory_units"] - base_totals["avg_inventory_units"], 0
            ),
            "skus_stocking_out": scen_totals["skus_stocking_out"]
            - base_totals["skus_stocking_out"],
        },
        "by_sku": per_sku[:100],
        "valuation_coverage": {
            "skus_with_cost": sum(1 for sk in simulated if sk.cost_known),
            "skus_with_price": sum(1 for sk in simulated if sk.price_known),
            "skus_total": len(simulated),
        },
    }


# ──────────────────────────────────────────────────────────────────────────────
# Presets — the questions people actually ask, one click each
# ──────────────────────────────────────────────────────────────────────────────

PRESETS: dict[str, dict[str, Any]] = {
    "demand_surge": {
        "label": "Sales increase 30%",
        "description": "A sustained 30% demand lift, ramped in over 4 weeks.",
        "scenario": {"name": "Sales +30%", "demand_shock_pct": 30.0, "ramp_weeks": 4},
    },
    "demand_collapse": {
        "label": "Sales drop 25%",
        "description": "Demand falls 25% — how much stock is left stranded?",
        "scenario": {"name": "Sales −25%", "demand_shock_pct": -25.0, "ramp_weeks": 2},
    },
    "supplier_failure": {
        "label": "A supplier fails",
        "description": "No replenishment arrives for 8 weeks; in-transit stock is delayed, not lost.",
        "scenario": {"name": "Supplier outage (8 weeks)", "supplier_outage_weeks": 8},
    },
    "port_strike": {
        "label": "Port strike",
        "description": "Every supplier lead time grows by 21 days for the whole horizon.",
        "scenario": {"name": "Port strike (+21 days)", "lead_time_delta_days": 21},
    },
    "tariff_increase": {
        "label": "Tariffs increase 15%",
        "description": "Landed unit cost rises 15% with selling prices held — a margin squeeze.",
        "scenario": {"name": "Tariff +15%", "cost_change_pct": 15.0},
    },
    "price_cut": {
        "label": "Cut prices 10%",
        "description": "A 10% price cut, with demand responding at −1.2 elasticity.",
        "scenario": {"name": "Price −10%", "price_change_pct": -10.0},
    },
    "service_push": {
        "label": "Push service level to 99%",
        "description": "Raise the target fill rate and see what it costs in working capital.",
        "scenario": {"name": "Service level 99%", "service_level": 0.99},
    },
}
