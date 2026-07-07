from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import structlog
from fastapi import APIRouter, Request
from sqlalchemy import func, select

from app.core.exceptions import GxPComplianceError, NotFoundError, PermissionDeniedError
from app.models.enums import GxPBatchStatus, IndustryCode
from app.models.pharma import PharmaBatch
from app.models.product import Sku
from app.models.trend import TrendSignal
from app.routers.industry_router import ActiveIndustry, TenantId, UserId
from app.services import audit
from app.services.industry_context import PHARMA

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/pharma", tags=["pharma"])


@router.get("/overview")
async def pharma_overview(
    request: Request, ctx: ActiveIndustry, tenant_id: TenantId
) -> dict[str, Any]:
    """Return pharma-vertical KPIs: batch counts by status, expiry alerts, shortage signals."""
    db = request.app.state.db

    async with db.session(str(tenant_id)) as session:
        total_skus = (
            await session.scalar(
                select(func.count(Sku.id)).where(
                    Sku.tenant_id == tenant_id,
                    Sku.industry == IndustryCode.pharma,
                    Sku.is_active.is_(True),
                )
            )
            or 0
        )

        quarantine_batches = (
            await session.scalar(
                select(func.count(PharmaBatch.id)).where(
                    PharmaBatch.tenant_id == tenant_id,
                    PharmaBatch.gxp_status == GxPBatchStatus.quarantine,
                )
            )
            or 0
        )

        released_batches = (
            await session.scalar(
                select(func.count(PharmaBatch.id)).where(
                    PharmaBatch.tenant_id == tenant_id,
                    PharmaBatch.gxp_status == GxPBatchStatus.released,
                )
            )
            or 0
        )

        non_conforming_batches = (
            await session.scalar(
                select(func.count(PharmaBatch.id)).where(
                    PharmaBatch.tenant_id == tenant_id,
                    PharmaBatch.gxp_status.in_(
                        (GxPBatchStatus.rejected, GxPBatchStatus.recalled, GxPBatchStatus.expired)
                    ),
                )
            )
            or 0
        )

        total_batches = (
            await session.scalar(
                select(func.count(PharmaBatch.id)).where(PharmaBatch.tenant_id == tenant_id)
            )
            or 0
        )

        expiry_threshold = date.today() + timedelta(days=90)
        expiring_soon = (
            await session.scalar(
                select(func.count(PharmaBatch.id)).where(
                    PharmaBatch.tenant_id == tenant_id,
                    PharmaBatch.gxp_status == GxPBatchStatus.released,
                    PharmaBatch.expiry_date <= expiry_threshold,
                    PharmaBatch.expiry_date >= date.today(),
                )
            )
            or 0
        )

        critical_threshold = date.today() + timedelta(days=30)
        expiring_critical = (
            await session.scalar(
                select(func.count(PharmaBatch.id)).where(
                    PharmaBatch.tenant_id == tenant_id,
                    PharmaBatch.gxp_status == GxPBatchStatus.released,
                    PharmaBatch.expiry_date <= critical_threshold,
                    PharmaBatch.expiry_date >= date.today(),
                )
            )
            or 0
        )

        regulatory_signals = (
            await session.scalar(
                select(func.count(TrendSignal.id)).where(
                    TrendSignal.industry == IndustryCode.pharma,
                    TrendSignal.kind.in_(("news_sentiment", "economic_indicator")),
                )
            )
            or 0
        )

    return {
        "industry": "pharma",
        "gxp_mode": True,
        "kpis": {
            "active_skus": total_skus,
            "batches_in_quarantine": quarantine_batches,
            "batches_released": released_batches,
            "batches_non_conforming": non_conforming_batches,
            "batches_total": total_batches,
            "batches_expiring_in_90_days": expiring_soon,
            "batches_expiring_critical_30_days": expiring_critical,
            "active_regulatory_signals": regulatory_signals,
        },
        "forecast_horizon_weeks": PHARMA.default_horizon_weeks,
        "active_models": PHARMA.forecast_models,
    }


@router.post("/batches/{batch_id}/release")
async def release_batch(
    batch_id: str,
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    user_id: UserId,
) -> dict[str, Any]:
    """QA release a pharma batch. Requires 'admin' or 'owner' role (GxP control)."""
    role = getattr(request.state, "role", "viewer")
    if role not in ("owner", "admin"):
        raise PermissionDeniedError("Batch release requires admin or owner role")

    import uuid as _uuid

    db = request.app.state.db
    bid = _uuid.UUID(batch_id)

    async with db.session(str(tenant_id)) as session:
        batch = await session.scalar(
            select(PharmaBatch).where(
                PharmaBatch.id == bid,
                PharmaBatch.tenant_id == tenant_id,
            )
        )
        if batch is None:
            raise NotFoundError("PharmaBatch")

        if batch.gxp_status != GxPBatchStatus.quarantine:
            raise GxPComplianceError(
                f"Batch is in status '{batch.gxp_status.value}', can only release from 'quarantine'"
            )

        if batch.cold_chain_required and (
            batch.storage_temp_min_c is None or batch.storage_temp_max_c is None
        ):
            raise GxPComplianceError("Cold-chain batch missing temperature range records")

        old_status = batch.gxp_status.value
        batch.gxp_status = GxPBatchStatus.released
        batch.qa_released_by = user_id
        batch.qa_released_at = datetime.now(tz=UTC)

        await audit.record(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            action="pharma_batch.release",
            entity_type="pharma_batch",
            entity_id=str(bid),
            industry=IndustryCode.pharma,
            old_value={"gxp_status": old_status},
            new_value={"gxp_status": "released"},
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("User-Agent"),
            request_id=getattr(request.state, "request_id", None),
        )

    log.info("pharma.batch.released", batch_id=batch_id, released_by=str(user_id))

    return {
        "batch_id": batch_id,
        "lot_number": batch.lot_number,
        "gxp_status": "released",
        "qa_released_by": str(user_id),
        "qa_released_at": batch.qa_released_at.isoformat(),
    }


@router.get("/batches/expiring")
async def expiring_batches(
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    days: int = 90,
) -> dict[str, Any]:
    """List released batches expiring within the given number of days."""
    if days < 1 or days > 365:
        days = 90

    db = request.app.state.db
    threshold = date.today() + timedelta(days=days)

    async with db.session(str(tenant_id)) as session:
        rows = await session.execute(
            select(PharmaBatch)
            .where(
                PharmaBatch.tenant_id == tenant_id,
                PharmaBatch.gxp_status == GxPBatchStatus.released,
                PharmaBatch.expiry_date <= threshold,
                PharmaBatch.expiry_date >= date.today(),
            )
            .order_by(PharmaBatch.expiry_date)
        )
        batches = rows.scalars().all()

    return {
        "threshold_days": days,
        "count": len(batches),
        "batches": [
            {
                "id": str(b.id),
                "sku_id": str(b.sku_id),
                "lot_number": b.lot_number,
                "ndc_code": b.ndc_code,
                "expiry_date": b.expiry_date.isoformat(),
                "quantity_remaining": b.quantity_remaining,
                "cold_chain_required": b.cold_chain_required,
            }
            for b in batches
        ],
    }
