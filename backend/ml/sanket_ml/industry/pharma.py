from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd
import structlog
from sqlalchemy import create_engine, text

from sanket_ml.config import get_ml_settings
from sanket_ml.optimization.replenishment import (
    safety_stock_recommendation,
)
from sanket_ml.training.pipeline import TrainConfig, TrainingPipeline, TrainResult

log = structlog.get_logger(__name__)


@dataclass
class PharmaOrchestratorResult:
    train_result: TrainResult
    expiry_risk: pd.DataFrame
    shortage_alerts: pd.DataFrame
    safety_stock_recommendations: pd.DataFrame


class PharmaOrchestrator:
    """End-to-end orchestration for the pharma vertical:
       train → forecast vs. batch expiry analysis → shortage detection
       Higher service level (≥0.99) reflects GxP / patient-safety constraints."""

    def __init__(self) -> None:
        self.pipeline = TrainingPipeline()
        self.settings = get_ml_settings()
        self._engine = create_engine(self.settings.database_url, pool_pre_ping=True)

    def run(
        self,
        tenant_id: uuid.UUID,
        horizon_weeks: int = 52,
        service_level: float = 0.99,
    ) -> PharmaOrchestratorResult:
        log.info("pharma.orchestrate.start", tenant=str(tenant_id))
        cfg = TrainConfig(
            tenant_id=tenant_id,
            industry="pharma",
            horizon_weeks=horizon_weeks,
        )
        train_result = self.pipeline.run(cfg)

        panel, static = self.pipeline.load_panel(cfg)
        forecast_means = (
            panel.data.groupby("unique_id")["y"]
            .apply(lambda s: float(s.tail(min(horizon_weeks, len(s))).mean()))
            .to_dict()
        )

        batches = self._load_batches(tenant_id)
        expiry_risk = self._expiry_risk_analysis(batches, forecast_means, horizon_weeks)
        shortage = self._shortage_alerts(static, forecast_means, horizon_weeks)
        ss_recs = self._safety_stock(static, forecast_means, horizon_weeks, service_level)

        return PharmaOrchestratorResult(
            train_result=train_result,
            expiry_risk=expiry_risk,
            shortage_alerts=shortage,
            safety_stock_recommendations=ss_recs,
        )

    def _load_batches(self, tenant_id: uuid.UUID) -> pd.DataFrame:
        with self._engine.begin() as conn:
            conn.execute(text("SET LOCAL app.current_tenant_id = :tid"), {"tid": str(tenant_id)})
            q = text(
                """
                SELECT
                    sku_id::text  AS unique_id,
                    lot_number,
                    quantity_remaining,
                    expiry_date,
                    gxp_status::text
                FROM pharma_batches
                WHERE tenant_id = :tid
                  AND gxp_status IN ('released','quarantine')
                  AND quantity_remaining > 0
                """
            )
            return pd.read_sql(q, conn, params={"tid": str(tenant_id)})

    @staticmethod
    def _expiry_risk_analysis(
        batches: pd.DataFrame,
        forecast_means: dict[str, float],
        horizon_weeks: int,
    ) -> pd.DataFrame:
        if batches.empty:
            return pd.DataFrame()
        today = date.today()
        rows: list[dict] = []
        for sku_id, g in batches.groupby("unique_id"):
            weekly_demand = max(0.0, forecast_means.get(sku_id, 0.0))
            g_sorted = g.sort_values("expiry_date")
            cumulative_consumed = 0.0
            for _, b in g_sorted.iterrows():
                weeks_to_expiry = max(0, (b["expiry_date"] - today).days // 7)
                consumable = weekly_demand * weeks_to_expiry
                at_risk = max(0, float(b["quantity_remaining"]) - max(0.0, consumable - cumulative_consumed))
                cumulative_consumed += min(consumable, float(b["quantity_remaining"]))
                if at_risk > 0:
                    rows.append({
                        "sku_id": sku_id,
                        "lot_number": b["lot_number"],
                        "expiry_date": b["expiry_date"],
                        "quantity_at_risk_of_expiry": int(round(at_risk)),
                        "weekly_demand_forecast": round(weekly_demand, 2),
                    })
        return pd.DataFrame(rows).sort_values("quantity_at_risk_of_expiry", ascending=False)

    @staticmethod
    def _shortage_alerts(
        static: pd.DataFrame,
        forecast_means: dict[str, float],
        horizon_weeks: int,
    ) -> pd.DataFrame:
        rows: list[dict] = []
        for _, sku in static.iterrows():
            uid = sku["unique_id"]
            on_hand = int(sku.get("safety_stock") or 0)
            mean_demand = forecast_means.get(uid, 0.0)
            if mean_demand <= 0:
                continue
            weeks_of_supply = on_hand / mean_demand if mean_demand > 0 else float("inf")
            if weeks_of_supply < (sku.get("lead_time_days") or 14) / 7 + 2:
                rows.append({
                    "sku_id": uid,
                    "weeks_of_supply": round(weeks_of_supply, 2),
                    "weekly_demand": round(mean_demand, 2),
                    "lead_time_days": sku.get("lead_time_days"),
                    "severity": "critical" if weeks_of_supply < 1 else "warning",
                })
        return pd.DataFrame(rows).sort_values("weeks_of_supply") if rows else pd.DataFrame()

    @staticmethod
    def _safety_stock(
        static: pd.DataFrame,
        forecast_means: dict[str, float],
        horizon_weeks: int,
        service_level: float,
    ) -> pd.DataFrame:
        rows: list[dict] = []
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
            rows.append({
                "sku_id": uid,
                "recommended_safety_stock": ss,
                "current_safety_stock": int(sku.get("safety_stock") or 0),
                "service_level": service_level,
            })
        return pd.DataFrame(rows)
