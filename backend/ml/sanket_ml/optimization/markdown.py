from __future__ import annotations

from dataclasses import dataclass

import structlog
from ortools.linear_solver import pywraplp

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class MarkdownSkuInputs:
    sku_id: str
    on_hand: int
    unit_cost: float
    full_price: float
    salvage_value: float           # value of leftover units at end of season
    price_elasticity: float        # negative: -1.5 typical for fashion
    base_demand_weekly: float


@dataclass(frozen=True, slots=True)
class MarkdownPlan:
    sku_id: str
    weekly_discount_pct: list[float]
    expected_units_sold: list[float]
    expected_revenue: float
    expected_leftover_units: int


class MarkdownOptimizer:
    """Choose a weekly discount schedule that maximizes end-of-season profit
    while ensuring inventory clearance. Uses log-linear demand:
        d_t = base * (1 + elasticity * discount_pct_t)
    Constraints: Σ d_t ≤ on_hand; discounts ∈ allowed grid.
    """

    def __init__(
        self,
        discount_grid: tuple[float, ...] = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7),
        time_limit_seconds: int = 30,
    ) -> None:
        self.discount_grid = discount_grid
        self.time_limit_seconds = time_limit_seconds

    def optimize(
        self,
        sku: MarkdownSkuInputs,
        horizon_weeks: int,
    ) -> MarkdownPlan:
        solver = pywraplp.Solver.CreateSolver("CBC")
        if solver is None:
            raise RuntimeError("OR-Tools CBC solver unavailable")
        solver.SetTimeLimit(self.time_limit_seconds * 1000)

        T = horizon_weeks
        D = len(self.discount_grid)
        # x[t,d] = 1 if discount d active in week t
        x = {(t, d): solver.IntVar(0, 1, f"x_{t}_{d}") for t in range(T) for d in range(D)}
        for t in range(T):
            solver.Add(sum(x[(t, d)] for d in range(D)) == 1)

        # Expected demand per week (linearized via grid)
        def demand_at(t):
            return solver.Sum(
                    self.discount_grid[d]
                    * 0.0  # placeholder, replaced below
                    for d in range(D)
                )  # we'll rebuild below

        # Expected demand for grid (precomputed scalars)
        d_grid = [
            max(0.0, sku.base_demand_weekly * (1.0 + sku.price_elasticity * dp))
            for dp in self.discount_grid
        ]
        units_sold = [
            solver.Sum(d_grid[d] * x[(t, d)] for d in range(D)) for t in range(T)
        ]
        # Cumulative units sold ≤ on_hand
        solver.Add(solver.Sum(units_sold) <= sku.on_hand)

        # Objective: maximize revenue - cost of goods
        revenue_terms = []
        for t in range(T):
            for d in range(D):
                price = sku.full_price * (1.0 - self.discount_grid[d])
                revenue_terms.append(price * d_grid[d] * x[(t, d)])
        # Leftover salvage value
        leftover = sku.on_hand - solver.Sum(units_sold)
        objective = solver.Sum(revenue_terms) + sku.salvage_value * leftover - sku.unit_cost * sku.on_hand
        solver.Maximize(objective)

        status = solver.Solve()
        if status not in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
            log.warning("markdown.infeasible", sku=sku.sku_id, status=status)
            return MarkdownPlan(
                sku_id=sku.sku_id,
                weekly_discount_pct=[0.0] * T,
                expected_units_sold=[0.0] * T,
                expected_revenue=0.0,
                expected_leftover_units=sku.on_hand,
            )

        discounts: list[float] = []
        weekly_units: list[float] = []
        revenue = 0.0
        for t in range(T):
            chosen = None
            for d in range(D):
                if x[(t, d)].solution_value() > 0.5:
                    chosen = d
                    break
            chosen = chosen or 0
            discounts.append(self.discount_grid[chosen])
            weekly_units.append(d_grid[chosen])
            revenue += sku.full_price * (1 - self.discount_grid[chosen]) * d_grid[chosen]

        leftover_units = max(0, int(round(sku.on_hand - sum(weekly_units))))

        return MarkdownPlan(
            sku_id=sku.sku_id,
            weekly_discount_pct=discounts,
            expected_units_sold=weekly_units,
            expected_revenue=revenue,
            expected_leftover_units=leftover_units,
        )
