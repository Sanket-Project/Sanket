from __future__ import annotations

import math
from dataclasses import dataclass

from scipy.stats import norm


@dataclass(frozen=True, slots=True)
class SafetyStockInputs:
    sku_id: str
    mean_demand: float
    std_demand: float
    lead_time_days: int
    service_level: float


@dataclass(frozen=True, slots=True)
class SafetyStockResult:
    sku_id: str
    safety_stock: int
    reorder_point: int
    service_level: float


class SafetyStockOptimizer:
    """Computes recommended safety stock and reorder point using lead-time-scaled demand variance."""

    def optimize(self, inputs: SafetyStockInputs) -> SafetyStockResult:
        z = float(norm.ppf(inputs.service_level))
        lead_time_weeks = inputs.lead_time_days / 7.0

        # Convert monthly demand stats to weekly (assuming 4 weeks/month)
        mean_demand_weekly = inputs.mean_demand / 4.0
        std_demand_weekly = inputs.std_demand / 2.0  # sqrt(4) = 2

        # Calculate safety stock = z * std_demand_weekly * sqrt(lead_time_weeks)
        safety_stock_val = z * std_demand_weekly * math.sqrt(lead_time_weeks)
        safety_stock = max(0, int(round(safety_stock_val)))

        # Calculate reorder point = demand_during_lead_time + safety_stock
        demand_during_lead_time = mean_demand_weekly * lead_time_weeks
        reorder_point = max(0, int(round(demand_during_lead_time + safety_stock)))

        return SafetyStockResult(
            sku_id=inputs.sku_id,
            safety_stock=safety_stock,
            reorder_point=reorder_point,
            service_level=inputs.service_level,
        )
