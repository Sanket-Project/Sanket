"""Live trend signal endpoints.

GET  /trends/live           — most recent samples for the active industry
GET  /trends/score          — aggregated TrendScore (score + volatility + drivers)
GET  /trends/economic       — economic indicator series (FRED)
GET  /trends/social         — social buzz series (Reddit + Google Trends)
POST /trends/refresh        — manually trigger the ingestion pipeline (admin only)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from sqlalchemy import select

from app.core.exceptions import PermissionDeniedError
from app.models.enums import IndustryCode, TrendSignalKind
from app.models.trend import TrendSignal
from app.routers.industry_router import ActiveIndustry, TenantId
from app.schemas.trends import TrendScoreOut, TrendSignalOut
from app.services.signal_evidence import signal_evidence

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/trends", tags=["trends"])


@router.get("/company/catalogue")
async def company_catalogue_options(
    request: Request, ctx: ActiveIndustry, tenant_id: TenantId,
    kind: Literal["product", "sku"] = "product",
    q: str = Query(default="", max_length=150),
    limit: int = Query(default=30, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    product_id: uuid.UUID | None = None,
) -> dict:
    from app.services.company_trends import catalogue_options
    async with request.app.state.db.session(str(tenant_id)) as session:
        return await catalogue_options(session, tenant_id, ctx.code, kind=kind, q=q, limit=limit,
                                       offset=offset, product_id=product_id)


@router.get("/company")
async def company_trend_analysis(
    request: Request, ctx: ActiveIndustry, tenant_id: TenantId,
    days: int = Query(default=28, ge=7, le=90),
    product_id: uuid.UUID | None = None,
    sku_id: uuid.UUID | None = None,
    state: str | None = Query(default=None, max_length=100),
    district: str | None = Query(default=None, max_length=100),
) -> dict:
    from app.services.company_trends import company_trends
    async with request.app.state.db.session(str(tenant_id)) as session:
        return await company_trends(session, tenant_id, ctx.code, days=days,
                                    product_id=product_id, sku_id=sku_id, state=state, district=district)


@router.post("/company/refresh", status_code=202)
async def refresh_company_trends(
    request: Request, background_tasks: BackgroundTasks, ctx: ActiveIndustry, tenant_id: TenantId,
) -> dict:
    if getattr(request.state, "role", "viewer") not in ("owner", "admin"):
        raise PermissionDeniedError("Trend refresh requires owner or admin")
    queue = getattr(request.app.state, "arq", None)
    if queue is not None:
        try:
            # arq keeps completed results; time buckets let later sweeps run.
            # The DB lock/freshness check handles workers spanning a bucket.
            bucket = int(datetime.now(UTC).timestamp()) // 900
            job = await queue.enqueue_job("run_company_trends", str(tenant_id), ctx.code,
                                          _job_id=f"company-interest:{tenant_id}:{ctx.code}:{bucket}")
        except Exception as exc:
            raise HTTPException(503, "Market interest refresh queue unavailable; retry later.") from exc
        if job is None:
            return {"status": "skipped", "reason": "A refresh was already requested in this 15-minute window."}
        return {"status": "queued"}
    from app.services.company_trends import refresh_company_interest
    background_tasks.add_task(refresh_company_interest, request.app.state.db, tenant_id, ctx.code)
    return {"status": "queued", "execution": "local_background"}


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
    pipeline = getattr(request.app.state, "signal_pipeline", None)
    evidence = signal_evidence(
        captured_at=[r.captured_at for r in records],
        sources=[r.source for r in records],
        industry=ctx.code,
        now=datetime.now(UTC),
        lookback_hours=lookback_hours,
        last_run=getattr(pipeline, "last_run", None),
    )

    return TrendScoreOut(
        industry=industry,
        score=score.score,
        # A volatility of 0 from no samples is not agreement — withhold it.
        volatility=score.volatility if evidence["agreement_reportable"] else None,
        evidence=evidence,
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
