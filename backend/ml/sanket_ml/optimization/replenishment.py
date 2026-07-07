from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import structlog
from ortools.linear_solver import pywraplp

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class SkuInputs:
    sku_id: str
    on_hand: int
    lead_time_days: int
    moq: int
    unit_cost: float
    unit_price: float
    safety_stock: int
    holding_cost_per_unit_per_week: float = 0.05
    stockout_penalty_per_unit: float = 5.0


@dataclass(frozen=True, slots=True)
class ReplenishmentPlan:
    sku_id: str
    weekly_orders: list[int]
    expected_ending_inventory: list[int]
    expected_stockouts: list[int]
    total_cost: float


class ReplenishmentOptimizer:
    """Single-SKU multi-period inventory MIP.

    Minimizes:  Σ_t (holding_cost · ending_inv_t + stockout_penalty · shortage_t + unit_cost · order_t)
    Subject to: ending_inv_t = ending_inv_{t-1} + order_arrival_t - demand_t + shortage_t
                ending_inv_t ≥ safety_stock
                order_t ∈ {0, MOQ, 2·MOQ, ...}  via integer multiplier
    """

    def __init__(self, time_limit_seconds: int = 30) -> None:
        self.time_limit_seconds = time_limit_seconds

    def optimize(
        self,
        sku: SkuInputs,
        demand_forecast: np.ndarray,  # length = horizon, units per week
    ) -> ReplenishmentPlan:
        horizon = len(demand_forecast)
        lead_time_weeks = max(1, int(round(sku.lead_time_days / 7)))

        solver = pywraplp.Solver.CreateSolver("CBC")
        if solver is None:
            raise RuntimeError("OR-Tools CBC solver unavailable")
        solver.SetTimeLimit(self.time_limit_seconds * 1000)

        big_m = int(demand_forecast.sum()) * 5 + 1
        # Decision: order multiplier in MOQ units, per week
        n_units = [solver.IntVar(0, big_m, f"n_units_{t}") for t in range(horizon)]
        # Inventory states
        inv = [solver.NumVar(0, big_m, f"inv_{t}") for t in range(horizon)]
        # Shortage (positive part of unmet demand)
        short = [solver.NumVar(0, big_m, f"short_{t}") for t in range(horizon)]

        for t in range(horizon):
            arrival = n_units[t - lead_time_weeks] * sku.moq if t - lead_time_weeks >= 0 else 0
            prev_inv = inv[t - 1] if t > 0 else sku.on_hand
            # Flow balance: inv_t = max(0, prev_inv + arrival - demand)
            # Linearized: inv_t - short_t = prev_inv + arrival - demand_t
            solver.Add(inv[t] - short[t] == prev_inv + arrival - float(demand_forecast[t]))
            # Safety stock constraint
            solver.Add(inv[t] >= sku.safety_stock - short[t])

        cost = solver.Objective()
        for t in range(horizon):
            cost.SetCoefficient(inv[t], sku.holding_cost_per_unit_per_week)
            cost.SetCoefficient(short[t], sku.stockout_penalty_per_unit)
            cost.SetCoefficient(n_units[t], sku.unit_cost * sku.moq)
        cost.SetMinimization()

        status = solver.Solve()
        if status not in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
            log.warning("replen.infeasible", sku=sku.sku_id, status=status)
            return ReplenishmentPlan(
                sku_id=sku.sku_id,
                weekly_orders=[0] * horizon,
                expected_ending_inventory=[sku.on_hand] * horizon,
                expected_stockouts=[0] * horizon,
                total_cost=float("inf"),
            )

        orders = [int(round(n_units[t].solution_value())) * sku.moq for t in range(horizon)]
        ending = [int(round(inv[t].solution_value())) for t in range(horizon)]
        shortages = [int(round(short[t].solution_value())) for t in range(horizon)]

        return ReplenishmentPlan(
            sku_id=sku.sku_id,
            weekly_orders=orders,
            expected_ending_inventory=ending,
            expected_stockouts=shortages,
            total_cost=float(solver.Objective().Value()),
        )


def safety_stock_recommendation(
    demand_forecast: np.ndarray,
    lead_time_days: int,
    service_level: float = 0.95,
) -> int:
    """Newsvendor-style safety stock = z * σ_LT.
    z is the inverse normal CDF at the chosen service level."""
    from scipy.stats import norm

    if len(demand_forecast) == 0:
        return 0
    lt_weeks = max(1, lead_time_days / 7)
    sigma_period = float(np.std(demand_forecast))
    sigma_lt = sigma_period * np.sqrt(lt_weeks)
    z = float(norm.ppf(service_level))
    return max(0, int(round(z * sigma_lt)))


@dataclass(frozen=True, slots=True)
class ReplenishmentInputs:
    sku_id: str
    on_hand: int
    inbound: int
    mean_demand_weekly: float
    lead_time_weeks: int
    horizon_weeks: int
    moq: int


@dataclass(frozen=True, slots=True)
class ReplenishmentPlanResult:
    sku_id: str
    order_weeks: list[int]
    order_quantities: list[int]


class ReplenishmentPlanner:
    """Convenience planner wrapper around ReplenishmentOptimizer."""

    def plan(self, inputs: ReplenishmentInputs) -> ReplenishmentPlanResult:
        optimizer = ReplenishmentOptimizer()
        demand = np.full(inputs.horizon_weeks, inputs.mean_demand_weekly, dtype=np.float64)
        sku = SkuInputs(
            sku_id=inputs.sku_id,
            on_hand=inputs.on_hand,
            lead_time_days=inputs.lead_time_weeks * 7,
            moq=inputs.moq,
            unit_cost=1.0,
            unit_price=5.0,  # Arbitrary values for optimization
            safety_stock=inputs.on_hand,
        )
        plan = optimizer.optimize(sku, demand)

        order_weeks: list[int] = []
        order_quantities: list[int] = []
        for t, qty in enumerate(plan.weekly_orders):
            if qty > 0:
                order_weeks.append(t)
                order_quantities.append(qty)

        return ReplenishmentPlanResult(
            sku_id=inputs.sku_id,
            order_weeks=order_weeks,
            order_quantities=order_quantities,
        )

