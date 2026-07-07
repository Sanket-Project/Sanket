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
class AgroOrchestratorResult:
    train_result: TrainResult
    safety_stock_plan: pd.DataFrame
    seasonal_replenishment: pd.DataFrame


class AgroOrchestrator:
    """End-to-end orchestration for the agrocenter vertical:
       train → safety-stock sizing → seasonal pre-planting replenishment."""

    def __init__(self) -> None:
        self.pipeline = TrainingPipeline()

    def run(
        self,
        tenant_id: uuid.UUID,
        horizon_weeks: int = 26,
        service_level: float = 0.95,
    ) -> AgroOrchestratorResult:
        log.info("agrocenter.orchestrate.start", tenant=str(tenant_id))
        cfg = TrainConfig(
            tenant_id=tenant_id,
            industry="agrocenter",
            horizon_weeks=horizon_weeks,
        )
        train_result = self.pipeline.run(cfg)

        panel, static = self.pipeline.load_panel(cfg)
        safety_stocks = self._compute_safety_stocks(static, service_level)
        replenishment = self._compute_seasonal_replenishment(static, horizon_weeks)

        return AgroOrchestratorResult(
            train_result=train_result,
            safety_stock_plan=safety_stocks,
            seasonal_replenishment=replenishment,
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
                        mean_demand=float(sku.get("mean_demand", 50) or 50),
                        std_demand=float(sku.get("std_demand", 15) or 15),
                        lead_time_days=int(sku.get("lead_time_days", 21) or 21),
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
                log.warning("agrocenter.safety_stock.failed", sku=sku["unique_id"], error=str(exc))
        return pd.DataFrame(rows)

    @staticmethod
    def _compute_seasonal_replenishment(static: pd.DataFrame, horizon_weeks: int) -> pd.DataFrame:
        planner = ReplenishmentPlanner()
        rows: list[dict] = []
        for _, sku in static.iterrows():
            try:
                result = planner.plan(
                    ReplenishmentInputs(
                        sku_id=sku["unique_id"],
                        on_hand=int(sku.get("safety_stock", 0) or 0),
                        inbound=0,
                        mean_demand_weekly=float(sku.get("mean_demand", 50) or 50) / 4,
                        lead_time_weeks=max(1, int((sku.get("lead_time_days", 21) or 21) / 7)),
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
                log.warning("agrocenter.replenishment.failed", sku=sku["unique_id"], error=str(exc))
        return pd.DataFrame(rows)
