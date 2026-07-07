from __future__ import annotations

import uuid
from dataclasses import dataclass

import numpy as np
import pandas as pd
import structlog

from sanket_ml.optimization.replenishment import (
    ReplenishmentOptimizer,
    SkuInputs,
    safety_stock_recommendation,
)
from sanket_ml.training.pipeline import TrainConfig, TrainingPipeline, TrainResult

log = structlog.get_logger(__name__)


@dataclass
class ElectronicsOrchestratorResult:
    train_result: TrainResult
    replenishment_plans: pd.DataFrame
    safety_stock_recommendations: pd.DataFrame


class ElectronicsOrchestrator:
    """End-to-end orchestration for the electronics vertical:
       train → safety-stock optimization → multi-period replenishment plan."""

    def __init__(self) -> None:
        self.pipeline = TrainingPipeline()

    def run(
        self,
        tenant_id: uuid.UUID,
        horizon_weeks: int = 12,
        service_level: float = 0.95,
    ) -> ElectronicsOrchestratorResult:
        log.info("electronics.orchestrate.start", tenant=str(tenant_id))
        cfg = TrainConfig(
            tenant_id=tenant_id,
            industry="electronics",
            horizon_weeks=horizon_weeks,
        )
        train_result = self.pipeline.run(cfg)

        # Run optimization based on most recent forecast
        panel, static = self.pipeline.load_panel(cfg)
        forecast_means = (
            panel.data.groupby("unique_id")["y"]
            .apply(lambda s: float(s.tail(horizon_weeks).mean()))
            .to_dict()
        )

        safety_rows: list[dict] = []
        plan_rows: list[dict] = []
        optimizer = ReplenishmentOptimizer()

        for _, sku in static.iterrows():
            uid = sku["unique_id"]
            mean_demand = forecast_means.get(uid, 0.0)
            if mean_demand <= 0:
                continue
            forecast = np.full(horizon_weeks, mean_demand, dtype="float32")
            ss = safety_stock_recommendation(
                forecast,
                lead_time_days=int(sku.get("lead_time_days") or 14),
                service_level=service_level,
            )
            safety_rows.append({
                "sku_id": uid,
                "recommended_safety_stock": ss,
                "current_safety_stock": int(sku.get("safety_stock") or 0),
                "service_level": service_level,
            })
            try:
                plan = optimizer.optimize(
                    SkuInputs(
                        sku_id=uid,
                        on_hand=int(sku.get("safety_stock") or 0),
                        lead_time_days=int(sku.get("lead_time_days") or 14),
                        moq=int(sku.get("moq") or 1),
                        unit_cost=float(sku.get("unit_cost") or 0.0),
                        unit_price=float(sku.get("unit_price") or 0.0),
                        safety_stock=ss,
                    ),
                    demand_forecast=forecast,
                )
                plan_rows.append({
                    "sku_id": uid,
                    "weekly_orders": plan.weekly_orders,
                    "expected_stockouts": plan.expected_stockouts,
                    "total_cost": plan.total_cost,
                })
            except Exception as exc:
                log.warning("electronics.optim.failed", sku=uid, error=str(exc))

        return ElectronicsOrchestratorResult(
            train_result=train_result,
            replenishment_plans=pd.DataFrame(plan_rows),
            safety_stock_recommendations=pd.DataFrame(safety_rows),
        )
