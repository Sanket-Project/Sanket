from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Request
from sqlalchemy import select

from app.core.exceptions import NotFoundError, PermissionDeniedError
from app.models.enums import IndustryCode, SignalStatus
from app.models.signal import ExternalSignal
from app.routers.industry_router import ActiveIndustry, TenantId, UserId
from app.schemas.signal import ExternalSignalCreate, ExternalSignalOut
from app.services import audit

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/signals", tags=["signals"])


@router.get("", response_model=list[ExternalSignalOut])
async def list_signals(
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    status: str | None = None,
    signal_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Any]:
    db = request.app.state.db
    industry = IndustryCode(ctx.code)

    async with db.session(str(tenant_id)) as session:
        q = select(ExternalSignal).where(
            ExternalSignal.tenant_id == tenant_id,
            ExternalSignal.industry == industry,
        )
        if status:
            q = q.where(ExternalSignal.status == status)
        if signal_type:
            q = q.where(ExternalSignal.signal_type == signal_type)
        q = q.order_by(ExternalSignal.effective_at.desc()).limit(min(limit, 200)).offset(offset)
        rows = await session.execute(q)
        return list(rows.scalars().all())


@router.post("", response_model=ExternalSignalOut, status_code=201)
async def ingest_signal(
    body: ExternalSignalCreate,
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    user_id: UserId,
) -> Any:
    db = request.app.state.db
    industry = IndustryCode(ctx.code)

    async with db.session(str(tenant_id)) as session:
        signal = ExternalSignal(
            tenant_id=tenant_id,
            industry=industry,
            **body.model_dump(),
        )
        session.add(signal)
        await session.flush()

        await audit.record(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            action="signal.ingest",
            entity_type="external_signal",
            entity_id=str(signal.id),
            industry=industry,
            new_value=body.model_dump(mode="json"),
            request_id=getattr(request.state, "request_id", None),
        )

    log.info("signal.ingested", signal_id=str(signal.id), type=body.signal_type)
    return signal


@router.post("/{signal_id}/validate", response_model=ExternalSignalOut)
async def validate_signal(
    signal_id: str,
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    user_id: UserId,
) -> Any:
    role = getattr(request.state, "role", "viewer")
    if role not in ("owner", "admin", "analyst"):
        raise PermissionDeniedError("Signal validation requires analyst role or above")

    db = request.app.state.db
    sid = uuid.UUID(signal_id)

    async with db.session(str(tenant_id)) as session:
        signal = await session.scalar(
            select(ExternalSignal).where(
                ExternalSignal.id == sid,
                ExternalSignal.tenant_id == tenant_id,
            )
        )
        if signal is None:
            raise NotFoundError("ExternalSignal")

        old_status = signal.status.value
        signal.status = SignalStatus.validated
        signal.validated_by = user_id
        signal.validated_at = datetime.now(tz=UTC)

        await audit.record(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            action="signal.validate",
            entity_type="external_signal",
            entity_id=str(sid),
            old_value={"status": old_status},
            new_value={"status": "validated"},
            request_id=getattr(request.state, "request_id", None),
        )

    return signal
