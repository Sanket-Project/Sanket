"""Cross-industry shortage correlation router.

Finds categories that appear as critical shortage alerts across 2+ industries
within a 7-day window — surfacing systemic supply-chain risks.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from fastapi import APIRouter, Request
from sqlalchemy import select

from app.routers.industry_router import TenantId

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/alerts", tags=["cross-industry"])


@router.get("/cross-industry")
async def cross_industry_correlation(
    request: Request,
    tenant_id: TenantId,
    window_days: int = 7,
) -> dict[str, Any]:
    """Return category-level shortage correlations spanning multiple industries."""
    from app.models.shortage_alert import ShortageAlert

    db = request.app.state.db
    cutoff = datetime.now(UTC) - timedelta(days=window_days)

    async with db.session(str(tenant_id)) as session:
        result = await session.execute(
            select(ShortageAlert)
            .where(
                ShortageAlert.tenant_id == tenant_id,
                ShortageAlert.severity == "critical",
                ShortageAlert.status.in_(("open", "acknowledged")),
                ShortageAlert.fired_at >= cutoff,
            )
            .order_by(ShortageAlert.fired_at.desc())
            .limit(500)
        )
        alerts = result.scalars().all()

    # Group by (industry, category) — extract category from title heuristic
    by_category: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for alert in alerts:
        industry = alert.industry.value if hasattr(alert.industry, "value") else str(alert.industry)
        # Category is first word of title or derived from drivers
        category = _extract_category(alert)
        by_category[category][industry].append(
            {
                "alert_id": str(alert.id),
                "risk_score": float(alert.risk_score),
                "fired_at": alert.fired_at.isoformat(),
            }
        )

    # Find categories present in 2+ industries
    correlations: list[dict] = []
    for category, industry_map in by_category.items():
        if len(industry_map) < 2:
            continue
        all_alerts = [a for alerts_list in industry_map.values() for a in alerts_list]
        avg_risk = sum(a["risk_score"] for a in all_alerts) / len(all_alerts)
        correlations.append(
            {
                "category": category,
                "industries": sorted(industry_map.keys()),
                "industry_count": len(industry_map),
                "alert_count": len(all_alerts),
                "avg_risk_score": round(avg_risk, 3),
                "by_industry": {k: len(v) for k, v in industry_map.items()},
            }
        )

    correlations.sort(key=lambda x: (x["industry_count"], x["avg_risk_score"]), reverse=True)

    return {
        "window_days": window_days,
        "total_critical_alerts": len(alerts),
        "correlated_categories": len(correlations),
        "correlations": correlations[:50],
    }


def _extract_category(alert: Any) -> str:
    title = getattr(alert, "title", "") or ""
    if title:
        return title.split()[0].lower().rstrip(":")
    drivers = getattr(alert, "drivers", []) or []
    if drivers and isinstance(drivers[0], dict):
        return drivers[0].get("series_key", "unknown").split(":")[0]
    return "unknown"
