from __future__ import annotations

import uuid
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Request
from sqlalchemy import func, select

from app.core.exceptions import ConflictError, NotFoundError
from app.core.rbac import require_admin
from app.models.product import Product, Sku
from app.routers.industry_router import ActiveIndustry, TenantId, UserId
from app.schemas.product import ProductCreate, ProductOut, ProductUpdate
from app.services import audit

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=list[ProductOut])
async def list_products(
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    limit: int = 50,
    offset: int = 0,
) -> list[Any]:
    from app.models.enums import IndustryCode

    db = request.app.state.db
    industry = IndustryCode(ctx.code)

    async with db.session(str(tenant_id)) as session:
        rows = await session.execute(
            select(Product)
            .where(Product.tenant_id == tenant_id, Product.industry == industry)
            .order_by(Product.created_at.desc())
            .limit(min(limit, 200))
            .offset(offset)
        )
        return list(rows.scalars().all())


@router.post("", response_model=ProductOut, status_code=201)
async def create_product(
    body: ProductCreate,
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    user_id: UserId,
) -> Any:
    from app.models.enums import IndustryCode

    db = request.app.state.db
    industry = IndustryCode(ctx.code)

    async with db.session(str(tenant_id)) as session:
        if body.external_id:
            existing = await session.scalar(
                select(Product).where(
                    Product.tenant_id == tenant_id,
                    Product.external_id == body.external_id,
                    Product.industry == industry,
                )
            )
            if existing is not None:
                raise ConflictError(f"Product with external_id '{body.external_id}' already exists")

        product = Product(tenant_id=tenant_id, industry=industry, **body.model_dump())
        session.add(product)
        await session.flush()

        await audit.record(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            action="product.create",
            entity_type="product",
            entity_id=str(product.id),
            industry=industry,
            new_value=body.model_dump(mode="json"),
            request_id=getattr(request.state, "request_id", None),
        )

    log.info("product.created", product_id=str(product.id), name=product.name)
    return product


@router.get("/{product_id}", response_model=ProductOut)
async def get_product(
    product_id: str, request: Request, ctx: ActiveIndustry, tenant_id: TenantId
) -> Any:
    db = request.app.state.db
    pid = uuid.UUID(product_id)

    async with db.session(str(tenant_id)) as session:
        product = await session.scalar(
            select(Product).where(Product.id == pid, Product.tenant_id == tenant_id)
        )
        if product is None:
            raise NotFoundError("Product")
    return product


@router.delete("/{product_id}")
async def delete_product(
    product_id: str,
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    user_id: UserId,
    _rbac: Annotated[None, require_admin],
) -> dict[str, Any]:
    """Hard-delete a product. Its SKUs cascade-delete via the FK.

    Requires admin or owner role — product deletion is destructive and
    cascades to all child SKUs.

    Blocked if any SKU under the product carries pharma batch records (GxP
    retention) — those must be preserved, so the product can't be removed
    until they are handled.
    """
    from app.models.enums import IndustryCode
    from app.models.pharma import PharmaBatch

    db = request.app.state.db
    pid = uuid.UUID(product_id)

    async with db.session(str(tenant_id)) as session:
        product = await session.scalar(
            select(Product).where(Product.id == pid, Product.tenant_id == tenant_id)
        )
        if product is None:
            raise NotFoundError("Product")

        batch_count = (
            await session.scalar(
                select(func.count(PharmaBatch.id))
                .join(Sku, Sku.id == PharmaBatch.sku_id)
                .where(Sku.product_id == pid, Sku.tenant_id == tenant_id)
            )
            or 0
        )
        if batch_count:
            raise ConflictError(
                f"Cannot delete product '{product.name}': {batch_count} pharma batch "
                "record(s) under its SKUs must be retained (GxP)."
            )

        sku_count = (
            await session.scalar(
                select(func.count(Sku.id)).where(Sku.product_id == pid, Sku.tenant_id == tenant_id)
            )
            or 0
        )

        await audit.record(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            action="product.delete",
            entity_type="product",
            entity_id=str(pid),
            industry=IndustryCode(ctx.code),
            old_value={"name": product.name, "cascaded_skus": sku_count},
            request_id=getattr(request.state, "request_id", None),
        )
        await session.delete(product)  # SKUs cascade via ON DELETE CASCADE

    log.info("product.deleted", product_id=str(pid), cascaded_skus=sku_count)
    return {"deleted": True, "id": str(pid), "cascaded_skus": sku_count}


@router.patch("/{product_id}", response_model=ProductOut)
async def update_product(
    product_id: str,
    body: ProductUpdate,
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    user_id: UserId,
) -> Any:
    db = request.app.state.db
    pid = uuid.UUID(product_id)

    async with db.session(str(tenant_id)) as session:
        product = await session.scalar(
            select(Product).where(Product.id == pid, Product.tenant_id == tenant_id)
        )
        if product is None:
            raise NotFoundError("Product")

        old_snapshot = {
            "name": product.name,
            "status": product.status.value if product.status else None,
        }
        updates = body.model_dump(exclude_none=True)
        for field, value in updates.items():
            setattr(product, field, value)

        await audit.record(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            action="product.update",
            entity_type="product",
            entity_id=str(pid),
            old_value=old_snapshot,
            new_value=updates,
            request_id=getattr(request.state, "request_id", None),
        )

    return product
