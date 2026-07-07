"""Economic Order Quantity (EOQ) calculator.

Classic Wilson formula:  EOQ = sqrt(2·D·S / H)
where:
  D = annual demand (units/year)
  S = order cost per order (fixed cost to place one order)
  H = annual holding cost per unit = holding_cost_pct * unit_cost

Also exposes sensitivity analysis across a demand range.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EOQResult:
    sku_id: str
    eoq_units: int
    reorder_frequency_weeks: float   # how often to order (weeks between orders)
    annual_order_cost: float
    annual_holding_cost: float
    total_annual_cost: float
    annual_demand: float
    unit_cost: float


class EOQCalculator:
    """Computes EOQ and cost breakdown for a single SKU."""

    def calculate(
        self,
        sku_id: str,
        annual_demand: float,
        order_cost: float,
        holding_cost_pct: float,
        unit_cost: float,
    ) -> EOQResult:
        if annual_demand <= 0 or unit_cost <= 0:
            return EOQResult(
                sku_id=sku_id, eoq_units=1,
                reorder_frequency_weeks=52.0,
                annual_order_cost=order_cost,
                annual_holding_cost=0.0,
                total_annual_cost=order_cost,
                annual_demand=annual_demand,
                unit_cost=unit_cost,
            )

        H = holding_cost_pct * unit_cost
        if H <= 0:
            H = 0.01 * unit_cost  # floor

        eoq = math.sqrt((2 * annual_demand * order_cost) / H)
        eoq_int = max(1, round(eoq))

        orders_per_year = annual_demand / eoq_int
        freq_weeks = 52.0 / orders_per_year

        annual_order = orders_per_year * order_cost
        annual_hold = (eoq_int / 2) * H
        total = annual_order + annual_hold

        return EOQResult(
            sku_id=sku_id,
            eoq_units=eoq_int,
            reorder_frequency_weeks=round(freq_weeks, 1),
            annual_order_cost=round(annual_order, 2),
            annual_holding_cost=round(annual_hold, 2),
            total_annual_cost=round(total, 2),
            annual_demand=annual_demand,
            unit_cost=unit_cost,
        )

    def sensitivity(
        self,
        sku_id: str,
        demand_range: list[float],
        order_cost: float,
        holding_cost_pct: float,
        unit_cost: float,
    ) -> list[EOQResult]:
        return [
            self.calculate(sku_id, d, order_cost, holding_cost_pct, unit_cost)
            for d in demand_range
        ]
