from __future__ import annotations

import uuid
from dataclasses import dataclass

import pandas as pd
import structlog

from sanket_ml.optimization.markdown import MarkdownOptimizer, MarkdownSkuInputs
from sanket_ml.training.pipeline import TrainConfig, TrainingPipeline, TrainResult

log = structlog.get_logger(__name__)


@dataclass
class FashionOrchestratorResult:
    train_result: TrainResult
    size_curves: pd.DataFrame
    markdown_recommendations: pd.DataFrame


class FashionOrchestrator:
    """End-to-end orchestration for the fashion vertical:
       train → size-curve analysis → markdown optimization → uplift on promos."""

    def __init__(self) -> None:
        self.pipeline = TrainingPipeline()

    def run(
        self,
        tenant_id: uuid.UUID,
        horizon_weeks: int = 26,
    ) -> FashionOrchestratorResult:
        log.info("fashion.orchestrate.start", tenant=str(tenant_id))
        cfg = TrainConfig(
            tenant_id=tenant_id,
            industry="fashion",
            horizon_weeks=horizon_weeks,
        )
        train_result = self.pipeline.run(cfg)

        # Size-curve analysis from static metadata + history
        panel, static = self.pipeline.load_panel(cfg)
        size_curves = self._compute_size_curves(panel.data, static)
        markdowns = self._recommend_markdowns(static, horizon_weeks)

        return FashionOrchestratorResult(
            train_result=train_result,
            size_curves=size_curves,
            markdown_recommendations=markdowns,
        )

    @staticmethod
    def _compute_size_curves(panel: pd.DataFrame, static: pd.DataFrame) -> pd.DataFrame:
        if static.empty or "attributes" not in static.columns:
            return pd.DataFrame()
        static = static.copy()
        static["size"] = static["attributes"].apply(
            lambda a: a.get("size") if isinstance(a, dict) else None
        )
        joined = panel.merge(
            static[["unique_id", "size", "product_id"]], on="unique_id", how="left"
        )
        agg = (
            joined.groupby(["product_id", "size"], dropna=False)["y"]
            .sum()
            .reset_index()
            .rename(columns={"y": "units"})
        )
        totals = agg.groupby("product_id")["units"].transform("sum")
        agg["share_pct"] = (agg["units"] / totals.replace(0, 1) * 100).round(2)
        return agg.sort_values(["product_id", "units"], ascending=[True, False])

    @staticmethod
    def _recommend_markdowns(static: pd.DataFrame, horizon_weeks: int) -> pd.DataFrame:
        optimizer = MarkdownOptimizer()
        rows: list[dict] = []
        for _, sku in static.iterrows():
            if pd.isna(sku.get("unit_price")) or sku["unit_price"] is None:
                continue
            try:
                plan = optimizer.optimize(
                    MarkdownSkuInputs(
                        sku_id=sku["unique_id"],
                        on_hand=int(sku.get("safety_stock", 0) or 0) + 200,  # approximation
                        unit_cost=float(sku.get("unit_cost") or 0.0),
                        full_price=float(sku["unit_price"]),
                        salvage_value=float(sku.get("unit_cost") or 0.0) * 0.3,
                        price_elasticity=-1.5,
                        base_demand_weekly=10.0,
                    ),
                    horizon_weeks=horizon_weeks,
                )
                rows.append({
                    "sku_id": sku["unique_id"],
                    "weekly_discount_pct": plan.weekly_discount_pct,
                    "expected_revenue": plan.expected_revenue,
                    "expected_leftover_units": plan.expected_leftover_units,
                })
            except Exception as exc:
                log.warning("fashion.markdown.failed", sku=sku["unique_id"], error=str(exc))
        return pd.DataFrame(rows)
