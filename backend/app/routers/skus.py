from __future__ import annotations

import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Request
from sqlalchemy import func, select

from app.core.exceptions import ConflictError, NotFoundError, SKULimitExceededError
from app.models.product import Product, Sku
from app.models.tenant import Tenant
from app.routers.industry_router import ActiveIndustry, TenantId, UserId
from app.schemas.product import SkuCreate, SkuOut, SkuUpdate
from app.services import audit

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/skus", tags=["skus"])


@router.get("", response_model=list[SkuOut])
async def list_skus(
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    limit: int = 50,
    offset: int = 0,
    active_only: bool = True,
) -> list[Any]:
    from app.models.enums import IndustryCode

    db = request.app.state.db
    industry = IndustryCode(ctx.code)

    async with db.session(str(tenant_id)) as session:
        q = select(Sku).where(Sku.tenant_id == tenant_id, Sku.industry == industry)
        if active_only:
            q = q.where(Sku.is_active.is_(True))
        q = q.order_by(Sku.created_at.desc()).limit(min(limit, 200)).offset(offset)
        rows = await session.execute(q)
        return list(rows.scalars().all())


@router.post("/{product_id}/skus", response_model=SkuOut, status_code=201)
async def create_sku(
    product_id: str,
    body: SkuCreate,
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    user_id: UserId,
) -> Any:
    from app.models.enums import IndustryCode

    db = request.app.state.db
    pid = uuid.UUID(product_id)
    industry = IndustryCode(ctx.code)

    attr_errors = ctx.validate_sku_attributes(body.attributes)
    if attr_errors:
        from app.core.exceptions import ValidationError

        raise ValidationError(f"SKU attribute errors: {'; '.join(attr_errors)}")

    async with db.session(str(tenant_id)) as session:
        tenant_row = await session.get(Tenant, tenant_id)
        if tenant_row is None:
            raise NotFoundError("Tenant")

        current_count = (
            await session.scalar(select(func.count(Sku.id)).where(Sku.tenant_id == tenant_id)) or 0
        )
        if current_count >= tenant_row.max_skus:
            raise SKULimitExceededError(tenant_row.max_skus)

        product = await session.scalar(
            select(Product).where(Product.id == pid, Product.tenant_id == tenant_id)
        )
        if product is None:
            raise NotFoundError("Product")

        existing = await session.scalar(
            select(Sku).where(Sku.tenant_id == tenant_id, Sku.sku_code == body.sku_code)
        )
        if existing is not None:
            raise ConflictError(f"SKU code '{body.sku_code}' already exists")

        new_sku = Sku(
            tenant_id=tenant_id,
            product_id=pid,
            industry=industry,
            **body.model_dump(),
        )
        session.add(new_sku)
        await session.flush()

        await audit.record(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            action="sku.create",
            entity_type="sku",
            entity_id=str(new_sku.id),
            industry=industry,
            new_value=body.model_dump(mode="json"),
            request_id=getattr(request.state, "request_id", None),
        )

    log.info("sku.created", sku_id=str(new_sku.id), code=new_sku.sku_code)
    return new_sku


@router.delete("/{sku_id}")
async def delete_sku(
    sku_id: str,
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    user_id: UserId,
) -> dict[str, Any]:
    """Hard-delete a SKU.

    Blocked for SKUs that carry pharma batch records — those are GxP / 21 CFR
    Part 11 retained records and must never be silently cascade-deleted. The
    caller should deactivate (is_active=false) instead.
    """
    from app.models.pharma import PharmaBatch

    db = request.app.state.db
    sid = uuid.UUID(sku_id)

    async with db.session(str(tenant_id)) as session:
        sku = await session.scalar(select(Sku).where(Sku.id == sid, Sku.tenant_id == tenant_id))
        if sku is None:
            raise NotFoundError("Sku")

        batch_count = (
            await session.scalar(
                select(func.count(PharmaBatch.id)).where(
                    PharmaBatch.sku_id == sid, PharmaBatch.tenant_id == tenant_id
                )
            )
            or 0
        )
        if batch_count:
            raise ConflictError(
                f"Cannot delete SKU '{sku.sku_code}': it has {batch_count} pharma "
                "batch record(s) that must be retained (GxP). Deactivate it instead."
            )

        snapshot = {
            "sku_code": sku.sku_code,
            "product_id": str(sku.product_id),
            "is_active": sku.is_active,
        }
        await audit.record(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            action="sku.delete",
            entity_type="sku",
            entity_id=str(sid),
            industry=sku.industry,
            old_value=snapshot,
            request_id=getattr(request.state, "request_id", None),
        )
        await session.delete(sku)

    log.info("sku.deleted", sku_id=str(sid))
    return {"deleted": True, "id": str(sid)}


@router.get("/{sku_id}", response_model=SkuOut)
async def get_sku(sku_id: str, request: Request, ctx: ActiveIndustry, tenant_id: TenantId) -> Any:
    db = request.app.state.db
    sid = uuid.UUID(sku_id)

    async with db.session(str(tenant_id)) as session:
        sku = await session.scalar(select(Sku).where(Sku.id == sid, Sku.tenant_id == tenant_id))
        if sku is None:
            raise NotFoundError("Sku")
    return sku


@router.patch("/{sku_id}", response_model=SkuOut)
async def update_sku(
    sku_id: str,
    body: SkuUpdate,
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    user_id: UserId,
) -> Any:
    db = request.app.state.db
    sid = uuid.UUID(sku_id)

    async with db.session(str(tenant_id)) as session:
        sku = await session.scalar(select(Sku).where(Sku.id == sid, Sku.tenant_id == tenant_id))
        if sku is None:
            raise NotFoundError("Sku")

        old_snapshot = {
            "unit_cost": str(sku.unit_cost),
            "unit_price": str(sku.unit_price),
            "is_active": sku.is_active,
        }
        updates = body.model_dump(exclude_none=True)
        for field, value in updates.items():
            setattr(sku, field, value)

        await audit.record(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            action="sku.update",
            entity_type="sku",
            entity_id=str(sid),
            old_value=old_snapshot,
            new_value=updates,
            request_id=getattr(request.state, "request_id", None),
        )

    return sku
