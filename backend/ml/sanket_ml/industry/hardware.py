from __future__ import annotations

import uuid
from dataclasses import dataclass

import pandas as pd
import structlog

from sanket_ml.optimization.replenishment import ReplenishmentInputs, ReplenishmentPlanner
from sanket_ml.optimization.safety_stock import SafetyStockInputs, SafetyStockOptimizer
from sanket_ml.training.pipeline import TrainConfig, TrainingPipeline, TrainResult

log = structlog.get_logger(__name__)


@dataclass
class HardwareOrchestratorResult:
    train_result: TrainResult
    safety_stock_plan: pd.DataFrame
    replenishment_plan: pd.DataFrame


class HardwareOrchestrator:
    """End-to-end orchestration for the hardware & industrial-supply vertical:
       train → safety-stock sizing → lead-time-aware replenishment.

    Hardware demand is steadier than fashion but dominated by long, volatile
    supplier lead times, so safety-stock sizing and replenishment timing carry
    most of the value here.
    """

    def __init__(self) -> None:
        self.pipeline = TrainingPipeline()

    def run(
        self,
        tenant_id: uuid.UUID,
        horizon_weeks: int = 16,
        service_level: float = 0.95,
    ) -> HardwareOrchestratorResult:
        log.info("hardware.orchestrate.start", tenant=str(tenant_id))
        cfg = TrainConfig(
            tenant_id=tenant_id,
            industry="hardware",
            horizon_weeks=horizon_weeks,
        )
        train_result = self.pipeline.run(cfg)

        _, static = self.pipeline.load_panel(cfg)
        safety_stocks = self._compute_safety_stocks(static, service_level)
        replenishment = self._compute_replenishment(static, horizon_weeks)

        return HardwareOrchestratorResult(
            train_result=train_result,
            safety_stock_plan=safety_stocks,
            replenishment_plan=replenishment,
        )

    @staticmethod
    def _compute_safety_stocks(static: pd.DataFrame, service_level: float) -> pd.DataFrame:
        optimizer = SafetyStockOptimizer()
        rows: list[dict] = []
        for _, sku in static.iterrows():
            try:
                result = optimizer.optimize(
                    SafetyStockInputs(
                        sku_id=sku["unique_id"],
                        mean_demand=float(sku.get("mean_demand", 40) or 40),
                        std_demand=float(sku.get("std_demand", 12) or 12),
                        lead_time_days=int(sku.get("lead_time_days", 28) or 28),
                        service_level=service_level,
                    )
                )
                rows.append({
                    "sku_id": sku["unique_id"],
                    "recommended_safety_stock": result.safety_stock,
                    "reorder_point": result.reorder_point,
                    "service_level": service_level,
                })
            except Exception as exc:
                log.warning("hardware.safety_stock.failed", sku=sku["unique_id"], error=str(exc))
        return pd.DataFrame(rows)

    @staticmethod
    def _compute_replenishment(static: pd.DataFrame, horizon_weeks: int) -> pd.DataFrame:
        planner = ReplenishmentPlanner()
        rows: list[dict] = []
        for _, sku in static.iterrows():
            try:
                result = planner.plan(
                    ReplenishmentInputs(
                        sku_id=sku["unique_id"],
                        on_hand=int(sku.get("safety_stock", 0) or 0),
                        inbound=0,
                        mean_demand_weekly=float(sku.get("mean_demand", 40) or 40) / 4,
                        lead_time_weeks=max(1, int((sku.get("lead_time_days", 28) or 28) / 7)),
                        horizon_weeks=horizon_weeks,
                        moq=int(sku.get("moq", 1) or 1),
                    )
                )
                rows.append({
                    "sku_id": sku["unique_id"],
                    "order_weeks": result.order_weeks,
                    "order_quantities": result.order_quantities,
                    "total_units": sum(result.order_quantities),
                })
            except Exception as exc:
                log.warning("hardware.replenishment.failed", sku=sku["unique_id"], error=str(exc))
        return pd.DataFrame(rows)
