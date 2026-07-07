"""Anomaly detection router — detects demand shocks in historical sales."""

from __future__ import annotations

from typing import Any

import pandas as pd
import structlog
from fastapi import APIRouter, Request
from sqlalchemy import func, select
from sqlalchemy import text as sa_text

from app.models.enums import IndustryCode
from app.routers.industry_router import ActiveIndustry, TenantId

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/anomaly", tags=["anomaly"])


@router.get("/skus")
async def anomaly_skus(
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    days: int = 90,
    limit: int = 50,
) -> dict[str, Any]:
    """Detect anomalous demand weeks per SKU using STL + Isolation Forest."""
    from sanket_ml.models.anomaly_detector import SalesAnomalyDetector

    from app.models.sales import HistoricalSale

    if days < 7:
        days = 7
    if limit < 1 or limit > 200:
        limit = 50

    db = request.app.state.db
    industry = IndustryCode(ctx.code)

    from datetime import UTC, datetime, timedelta

    cutoff = datetime.now(UTC) - timedelta(days=days)

    async with db.session(str(tenant_id)) as session:
        _week = func.date_trunc(sa_text("'week'"), HistoricalSale.sale_time)
        rows = await session.execute(
            select(
                HistoricalSale.sku_id,
                _week.label("week"),
                func.sum(HistoricalSale.units_sold).label("units"),
            )
            .where(
                HistoricalSale.tenant_id == tenant_id,
                HistoricalSale.industry == industry,
                HistoricalSale.sale_time >= cutoff,
            )
            .group_by(HistoricalSale.sku_id, _week)
            .order_by(HistoricalSale.sku_id, _week)
        )
        data = rows.fetchall()

    if not data:
        return {"industry": ctx.code, "sku_count": 0, "anomalous_skus": []}

    df = pd.DataFrame(data, columns=["sku_id", "week", "units"])
    df["week"] = pd.to_datetime(df["week"])
    detector = SalesAnomalyDetector()

    results: list[dict] = []
    for sku_id, grp in df.groupby("sku_id"):
        series = grp.set_index("week")["units"].astype(float).sort_index()
        anomaly_rows = detector.detect(series)
        n_anomalies = sum(1 for r in anomaly_rows if r.is_anomaly)
        if n_anomalies == 0:
            continue
        last_anomaly = max((r.ds for r in anomaly_rows if r.is_anomaly), default=None)
        results.append(
            {
                "sku_id": str(sku_id),
                "anomaly_count": n_anomalies,
                "latest_anomaly_date": last_anomaly,
                "anomaly_rows": [
                    {"ds": r.ds, "y": r.y, "score": r.anomaly_score}
                    for r in anomaly_rows
                    if r.is_anomaly
                ],
            }
        )

    results.sort(key=lambda x: x["anomaly_count"], reverse=True)
    return {
        "industry": ctx.code,
        "window_days": days,
        "sku_count": len(results),
        "anomalous_skus": results[:limit],
    }
