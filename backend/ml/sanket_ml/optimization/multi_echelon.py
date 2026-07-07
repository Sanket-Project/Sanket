"""Two-echelon safety stock optimizer (Distribution Centre → Branch).

Uses Clark-Scarf echelon stock decomposition:
  SS_branch = z * σ_branch * sqrt(LT_branch)
  SS_dc     = z * σ_dc     * sqrt(LT_dc + max(LT_branch))

where σ is weekly demand standard deviation and LT is lead time in weeks.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from scipy.stats import norm


@dataclass(frozen=True, slots=True)
class EchelonNode:
    name: str
    demand_mean_weekly: float
    demand_std_weekly: float
    lead_time_days: int
    holding_cost_pct: float = 0.25
    unit_cost: float = 1.0


@dataclass
class MultiEchelonResult:
    dc_safety_stock: int
    branch_safety_stocks: dict[str, int]
    total_system_safety_stock: int
    annual_holding_cost: float
    service_level: float


class MultiEchelonOptimizer:
    """Clark-Scarf two-echelon safety stock decomposition."""

    def optimize(
        self,
        dc: EchelonNode,
        branches: list[EchelonNode],
        service_level: float = 0.95,
    ) -> MultiEchelonResult:
        z = float(norm.ppf(service_level))
        max_branch_lt_weeks = max((b.lead_time_days / 7) for b in branches) if branches else 0

        # DC safety stock covers its own lead time plus the longest branch lead time
        dc_lt_weeks = dc.lead_time_days / 7 + max_branch_lt_weeks
        dc_ss = max(0, round(z * dc.demand_std_weekly * math.sqrt(dc_lt_weeks)))

        branch_ss: dict[str, int] = {}
        for b in branches:
            lt_weeks = b.lead_time_days / 7
            ss = max(0, round(z * b.demand_std_weekly * math.sqrt(lt_weeks)))
            branch_ss[b.name] = ss

        total_ss = dc_ss + sum(branch_ss.values())

        # Approximate annual holding cost
        annual_holding = (
            dc_ss * dc.unit_cost * dc.holding_cost_pct
            + sum(
                branch_ss[b.name] * b.unit_cost * b.holding_cost_pct
                for b in branches
            )
        )

        return MultiEchelonResult(
            dc_safety_stock=dc_ss,
            branch_safety_stocks=branch_ss,
            total_system_safety_stock=total_ss,
            annual_holding_cost=round(annual_holding, 2),
            service_level=service_level,
        )
