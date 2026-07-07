"""Trend-fused probabilistic forecast endpoints.

The hybrid forecast runs Chronos inference (~60s+), which is too long for a
synchronous HTTP request behind real proxies/load balancers. So it runs as a
durable background job:

    POST /forecast/hybrid/runs        → 202 { run_id, status: "pending" }
    GET  /forecast/hybrid/runs/{id}   → { status, result?, error? }

The job is enqueued to arq (Redis-backed) and executed by the forecast worker
(`app.workers.forecast_worker`). Progress + completion are also pushed over the
existing WebSocket layer (`forecast.run.progress` / `.completed` / `.failed`),
so the UI can show live progress and avoid polling when WS is connected.

The legacy synchronous `POST /forecast/hybrid` is retained (deprecated) for
backward compatibility — it runs the same job inline and blocks until done.
"""

from __future__ import annotations

import asyncio
import uuid

import httpx
import structlog
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from app.models.enums import IndustryCode
from app.models.trend import HybridForecastRun
from app.routers.industry_router import ActiveIndustry, TenantId, UserId
from app.schemas.trends import (
    HybridForecastOut,
    HybridForecastRequest,
    HybridRunAccepted,
    HybridRunStatus,
)
from app.services.hybrid_forecast import execute_hybrid_run
from app.services.industry_config import resolve_effective_config

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/forecast", tags=["forecast"])


async def _apply_effective_horizon(
    db, tenant_id: uuid.UUID, industry_code: str, body: HybridForecastRequest
) -> HybridForecastRequest:
    """Fill in horizon_weeks from the tenant's effective industry config when the
    client omitted it, so the archetype default / tenant override is honored."""
    if body.horizon_weeks is not None:
        return body
    async with db.session(str(tenant_id)) as session:
        config = await resolve_effective_config(session, tenant_id, industry_code)
    return body.model_copy(update={"horizon_weeks": config.effective_horizon})


async def _create_run_row(
    db, tenant_id: uuid.UUID, industry: IndustryCode, body: HybridForecastRequest
) -> uuid.UUID:
    run_id = uuid.uuid4()
    async with db.session(str(tenant_id)) as session:
        session.add(
            HybridForecastRun(
                id=run_id,
                tenant_id=tenant_id,
                industry=industry,
                horizon_weeks=body.horizon_weeks,
                status="pending",
                request_params=body.model_dump(mode="json"),
            )
        )
    return run_id


@router.post("/hybrid/runs", status_code=202, response_model=HybridRunAccepted)
async def create_hybrid_run(
    body: HybridForecastRequest,
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    user_id: UserId,
) -> HybridRunAccepted:
    """Enqueue a hybrid forecast run; returns immediately with a run_id to poll."""
    db = request.app.state.db
    industry = IndustryCode(ctx.code)
    body = await _apply_effective_horizon(db, tenant_id, ctx.code, body)
    run_id = await _create_run_row(db, tenant_id, industry, body)

    arq_pool = getattr(request.app.state, "arq", None)
    if arq_pool is not None:
        await arq_pool.enqueue_job(
            "run_hybrid_forecast",
            str(run_id),
            str(tenant_id),
            ctx.code,
            body.model_dump(mode="json"),
        )
        log.info("hybrid.run.enqueued", run_id=str(run_id), tenant=str(tenant_id))
    else:
        # No arq pool (Redis unconfigured) — degrade gracefully to in-process
        # execution so dev without a worker still functions.
        log.warning("hybrid.run.inprocess_fallback", run_id=str(run_id))
        http_client: httpx.AsyncClient | None = getattr(request.app.state, "http", None)
        realtime = getattr(request.app.state, "realtime", None)
        asyncio.create_task(
            execute_hybrid_run(
                db=db,
                http_client=http_client,
                realtime=realtime,
                run_id=run_id,
                tenant_id=tenant_id,
                industry_code=ctx.code,
                body=body,
            )
        )

    return HybridRunAccepted(run_id=run_id, status="pending")


@router.get("/hybrid/runs/{run_id}", response_model=HybridRunStatus)
async def get_hybrid_run(
    run_id: uuid.UUID,
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    user_id: UserId,
) -> HybridRunStatus:
    """Poll a hybrid forecast run; `result` is populated once status=completed."""
    db = request.app.state.db
    async with db.session(str(tenant_id)) as session:
        row = await session.scalar(select(HybridForecastRun).where(HybridForecastRun.id == run_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Forecast run not found")

    return HybridRunStatus(
        run_id=row.id,
        status=row.status,
        horizon_weeks=row.horizon_weeks,
        industry=row.industry,
        created_at=row.created_at,
        completed_at=row.completed_at,
        error=row.error,
        result=row.result,
    )


@router.post("/hybrid", response_model=HybridForecastOut, deprecated=True)
async def hybrid_forecast_sync(
    body: HybridForecastRequest,
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    user_id: UserId,
) -> HybridForecastOut:
    """Deprecated synchronous variant. Runs the job inline and blocks until done.

    Prefer POST /forecast/hybrid/runs + GET /forecast/hybrid/runs/{id}, which is
    not subject to client/proxy request timeouts. Kept for backward compatibility.
    """
    db = request.app.state.db
    industry = IndustryCode(ctx.code)
    http_client: httpx.AsyncClient | None = getattr(request.app.state, "http", None)
    realtime = getattr(request.app.state, "realtime", None)

    body = await _apply_effective_horizon(db, tenant_id, ctx.code, body)
    run_id = await _create_run_row(db, tenant_id, industry, body)
    await execute_hybrid_run(
        db=db,
        http_client=http_client,
        realtime=realtime,
        run_id=run_id,
        tenant_id=tenant_id,
        industry_code=ctx.code,
        body=body,
    )

    async with db.session(str(tenant_id)) as session:
        row = await session.scalar(select(HybridForecastRun).where(HybridForecastRun.id == run_id))
    if row is None or row.status != "completed" or row.result is None:
        detail = row.error if row and row.error else "Hybrid forecast failed"
        raise HTTPException(status_code=502, detail=detail)
    return HybridForecastOut.model_validate(row.result)
