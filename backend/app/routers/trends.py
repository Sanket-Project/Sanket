"""Live trend signal endpoints.

GET  /trends/live           — most recent samples for the active industry
GET  /trends/score          — aggregated TrendScore (score + volatility + drivers)
GET  /trends/economic       — economic indicator series (FRED)
GET  /trends/social         — social buzz series (Reddit + Google Trends)
POST /trends/refresh        — manually trigger the ingestion pipeline (admin only)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from app.core.exceptions import PermissionDeniedError
from app.models.enums import IndustryCode, TrendSignalKind
from app.models.trend import TrendSignal
from app.routers.industry_router import ActiveIndustry, TenantId
from app.schemas.trends import TrendScoreOut, TrendSignalOut

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/trends", tags=["trends"])


@router.get("/live", response_model=list[TrendSignalOut])
async def list_live_signals(
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    kind: str | None = Query(default=None),
    hours: int = Query(default=72, ge=1, le=720),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[Any]:
    db = request.app.state.db
    industry = IndustryCode(ctx.code)
    cutoff = datetime.now(UTC) - timedelta(hours=hours)

    async with db.session(str(tenant_id)) as session:
        q = select(TrendSignal).where(
            TrendSignal.industry == industry,
            TrendSignal.captured_at >= cutoff,
        )
        if kind:
            q = q.where(TrendSignal.kind == kind)
        q = q.order_by(TrendSignal.captured_at.desc()).limit(limit)
        rows = await session.execute(q)
        return list(rows.scalars().all()) if hasattr(rows, "scalars") else list(rows or [])


@router.get("/score", response_model=TrendScoreOut)
async def aggregate_trend_score(
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    horizon_days: int = Query(default=90, ge=7, le=365),
    lookback_hours: int = Query(default=168, ge=24, le=720),
) -> TrendScoreOut:
    """Return the aggregated trend score for the active industry."""
    from sanket_ml.fusion.trend_scorer import SignalRecord, TrendScorer

    db = request.app.state.db
    industry = IndustryCode(ctx.code)
    cutoff = datetime.now(UTC) - timedelta(hours=lookback_hours)

    async with db.session(str(tenant_id)) as session:
        q = (
            select(TrendSignal)
            .where(
                TrendSignal.industry == industry,
                TrendSignal.captured_at >= cutoff,
            )
            .order_by(TrendSignal.captured_at.desc())
        )
        rows = await session.execute(q)
        signals_db = list(rows.scalars().all()) if hasattr(rows, "scalars") else list(rows or [])

    records: list[SignalRecord] = []
    for s in signals_db:
        try:
            records.append(
                SignalRecord(
                    source=s.source.value if hasattr(s.source, "value") else str(s.source),
                    kind=s.kind.value if hasattr(s.kind, "value") else str(s.kind),
                    series_key=s.series_key,
                    industry=s.industry.value if hasattr(s.industry, "value") else str(s.industry),
                    normalized_score=float(s.normalized_score),
                    confidence=float(s.confidence),
                    captured_at=s.captured_at,
                    category_tags=list(s.category_tags or []),
                )
            )
        except Exception as exc:
            log.warning("trends.score.record_skipped", error=str(exc))

    scorer = TrendScorer()
    score = scorer.score(industry=ctx.code, signals=records, horizon_days=horizon_days)

    return TrendScoreOut(
        industry=industry,
        score=score.score,
        volatility=score.volatility,
        sample_count=score.sample_count,
        by_kind=score.by_kind,
        drivers=score.drivers,
        demand_factors=getattr(score, "demand_factors", []),
        horizon_days=score.horizon_days,
        as_of=datetime.now(UTC),
    )


@router.get("/economic", response_model=list[TrendSignalOut])
async def economic_indicators(
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[Any]:
    db = request.app.state.db
    industry = IndustryCode(ctx.code)
    async with db.session(str(tenant_id)) as session:
        q = (
            select(TrendSignal)
            .where(
                TrendSignal.industry == industry,
                TrendSignal.kind == TrendSignalKind.economic_indicator,
                ~TrendSignal.series_key.like("logistics:%"),
                ~TrendSignal.series_key.like("weather:%"),
            )
            .order_by(TrendSignal.captured_at.desc())
            .limit(limit)
        )
        rows = await session.execute(q)
        return list(rows.scalars().all()) if hasattr(rows, "scalars") else list(rows or [])


@router.get("/social", response_model=list[TrendSignalOut])
async def social_signals(
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[Any]:
    db = request.app.state.db
    industry = IndustryCode(ctx.code)
    async with db.session(str(tenant_id)) as session:
        q = (
            select(TrendSignal)
            .where(
                TrendSignal.industry == industry,
                TrendSignal.kind.in_(
                    [TrendSignalKind.social_buzz, TrendSignalKind.search_interest]
                ),
                ~TrendSignal.series_key.like("trends:regional_demand:%"),
            )
            .order_by(TrendSignal.captured_at.desc())
            .limit(limit)
        )
        rows = await session.execute(q)
        return list(rows.scalars().all()) if hasattr(rows, "scalars") else list(rows or [])


@router.get("/supply-chain", response_model=list[TrendSignalOut])
async def supply_chain_signals(
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[Any]:
    """Retrieve logistics routing corridors and localized weather factor signals for the active industry."""
    db = request.app.state.db
    industry = IndustryCode(ctx.code)
    async with db.session(str(tenant_id)) as session:
        q = (
            select(TrendSignal)
            .where(
                TrendSignal.industry == industry,
                (
                    TrendSignal.series_key.like("logistics:%")
                    | TrendSignal.series_key.like("weather:%")
                ),
            )
            .order_by(TrendSignal.captured_at.desc())
            .limit(limit)
        )
        rows = await session.execute(q)
        return list(rows.scalars().all()) if hasattr(rows, "scalars") else list(rows or [])


@router.get("/regional", response_model=list[TrendSignalOut])
async def list_regional_signals(
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    limit: int = Query(default=300, ge=1, le=1000),
) -> list[Any]:
    """Retrieve regional demand trends for the active industry."""
    db = request.app.state.db
    industry = IndustryCode(ctx.code)

    async with db.session(str(tenant_id)) as session:
        q = (
            select(TrendSignal)
            .where(
                TrendSignal.industry == industry,
                TrendSignal.series_key.like("trends:regional_demand:%"),
            )
            .order_by(TrendSignal.captured_at.desc())
            .limit(limit)
        )
        rows = await session.execute(q)
        return list(rows.scalars().all()) if hasattr(rows, "scalars") else list(rows or [])


@router.post("/refresh", status_code=202)
async def trigger_refresh(request: Request) -> dict:
    """Force the signal ingestion pipeline to fetch immediately.

    Owners + admins only — Reddit/Trends have rate limits."""
    role = getattr(request.state, "role", "viewer")
    if role not in ("owner", "admin"):
        raise PermissionDeniedError("Trend refresh requires owner or admin")

    pipeline = getattr(request.app.state, "signal_pipeline", None)
    if pipeline is None:
        return {"status": "skipped", "reason": "pipeline not configured"}
    counts = await pipeline.run_once()
    return {"status": "ok", "counts": counts}
