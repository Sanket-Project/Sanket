from __future__ import annotations

import uuid
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Request
from pydantic import ValidationError as RowValidationError
from sqlalchemy import func, or_, select

from app.core.exceptions import (
    ConflictError,
    NotFoundError,
    SanketBaseError,
    SKULimitExceededError,
)
from app.core.rbac import require_admin
from app.models.product import Product, Sku
from app.models.tenant import Tenant
from app.routers.industry_router import ActiveIndustry, TenantId, UserId
from app.schemas.product import (
    SkuBulkCreate,
    SkuBulkDelete,
    SkuBulkResult,
    SkuBulkRow,
    SkuCreate,
    SkuOut,
    SkuUpdate,
)
from app.services import audit
from app.services.industry_context import IndustryContext

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/skus", tags=["skus"])


_FALLBACK_CURRENCY = "USD"  # the column default, used only when nothing better is known


def _workspace_currency(settings: dict | None) -> str | None:
    code = str((settings or {}).get("currency") or "").strip().upper()
    return code if len(code) == 3 and code.isalpha() else None


def _uuid_or_none(value: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


def _checked_attributes(ctx: IndustryContext, attributes: dict[str, Any]) -> dict[str, Any]:
    """Normalise industry attribute spellings, then refuse anything invalid (422)."""
    normalized = ctx.normalize_sku_attributes(attributes)
    errors = ctx.validate_sku_attributes(normalized)
    if errors:
        from app.core.exceptions import ValidationError

        raise ValidationError(f"SKU attribute errors: {'; '.join(errors)}")
    return normalized


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
        q = q.order_by(Sku.created_at.desc(), Sku.id.desc()).limit(min(limit, 200)).offset(offset)
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
    pid = _uuid_or_none(product_id)
    if pid is None:
        raise NotFoundError("Product")
    industry = IndustryCode(ctx.code)

    body = body.model_copy(update={"attributes": _checked_attributes(ctx, body.attributes)})

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

        fields = body.model_dump()
        fields["currency"] = (
            body.currency or _workspace_currency(tenant_row.settings) or _FALLBACK_CURRENCY
        )
        new_sku = Sku(
            tenant_id=tenant_id,
            product_id=pid,
            industry=industry,
            **fields,
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


@router.post("/bulk", response_model=SkuBulkResult)
async def bulk_create_skus(
    body: SkuBulkCreate,
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    user_id: UserId,
) -> dict[str, Any]:
    """Create up to 500 SKUs in one request, reporting each row that could not be created.

    A catalogue import used to send one request per SKU and ran into the per-user
    rate limit. Rows name their product by code (external_id) or id. A code that
    already exists is skipped, as the single create's 409 is; any other problem
    fails only that row.
    """
    from app.models.enums import IndustryCode

    db = request.app.state.db
    industry = IndustryCode(ctx.code)
    skipped = 0
    errors: list[dict[str, Any]] = []
    created: list[tuple[Sku, SkuBulkRow]] = []

    def fail(index: int, sku_code: Any, reason: str) -> None:
        errors.append(
            {
                "index": index,
                "sku_code": sku_code if isinstance(sku_code, str) else None,
                "reason": reason,
            }
        )

    def given(field: str) -> list[str]:
        return [v for raw in body.rows if isinstance(v := raw.get(field), str) and v]

    async with db.session(str(tenant_id)) as session:
        tenant_row = await session.get(Tenant, tenant_id)
        if tenant_row is None:
            raise NotFoundError("Tenant")
        workspace_currency = _workspace_currency(tenant_row.settings) or _FALLBACK_CURRENCY
        sku_count = (
            await session.scalar(select(func.count(Sku.id)).where(Sku.tenant_id == tenant_id)) or 0
        )
        products = (
            await session.execute(
                select(Product.id, Product.external_id).where(Product.tenant_id == tenant_id)
            )
        ).all()
        product_by_code = {code: pid for pid, code in products if code}
        product_ids = {pid for pid, _ in products}
        # Only this batch's codes/barcodes/external ids can collide, so look up just those.
        taken = (
            await session.execute(
                select(Sku.sku_code, Sku.gtin, Sku.external_id).where(
                    Sku.tenant_id == tenant_id,
                    or_(
                        Sku.sku_code.in_(given("sku_code")),
                        Sku.gtin.in_(given("gtin")),
                        Sku.external_id.in_(given("external_id")),
                    ),
                )
            )
        ).all()
        taken_codes = {code for code, _, _ in taken}
        taken_gtins = {gtin for _, gtin, _ in taken if gtin}
        taken_external_ids = {ext for _, _, ext in taken if ext}

        for index, raw in enumerate(body.rows):
            try:
                row = SkuBulkRow.model_validate(raw)
                attributes = _checked_attributes(ctx, row.attributes)
            except RowValidationError as exc:
                fail(
                    index,
                    raw.get("sku_code"),
                    "; ".join(
                        f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
                    ),
                )
                continue
            except SanketBaseError as exc:
                fail(index, raw.get("sku_code"), str(exc.detail))
                continue

            pid = _uuid_or_none(row.product)
            product_id = product_by_code.get(row.product) or (pid if pid in product_ids else None)
            if product_id is None:
                fail(index, row.sku_code, f"No product with code or id '{row.product}'")
                continue
            if row.sku_code in taken_codes:
                skipped += 1
                continue
            # Unique per workspace; one collision would otherwise abort the whole batch.
            if row.gtin and row.gtin in taken_gtins:
                fail(index, row.sku_code, f"Barcode {row.gtin} is already used by another SKU")
                continue
            if row.external_id and row.external_id in taken_external_ids:
                fail(
                    index,
                    row.sku_code,
                    f"External id {row.external_id} is already used by another SKU",
                )
                continue
            if sku_count + len(created) >= tenant_row.max_skus:
                fail(index, row.sku_code, f"SKU limit reached ({tenant_row.max_skus} on this plan)")
                continue

            fields = row.model_dump(exclude={"product"})
            fields["attributes"] = attributes
            fields["currency"] = row.currency or workspace_currency
            sku = Sku(tenant_id=tenant_id, product_id=product_id, industry=industry, **fields)
            session.add(sku)
            created.append((sku, row))
            taken_codes.add(row.sku_code)
            if row.gtin:
                taken_gtins.add(row.gtin)
            if row.external_id:
                taken_external_ids.add(row.external_id)

        await session.flush()
        for sku, row in created:
            await audit.record(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                action="sku.create",
                entity_type="sku",
                entity_id=str(sku.id),
                industry=industry,
                new_value=row.model_dump(mode="json"),
                request_id=getattr(request.state, "request_id", None),
            )

    log.info("sku.bulk_created", created=len(created), skipped=skipped, failed=len(errors))
    return {"created": len(created), "skipped": skipped, "failed": len(errors), "errors": errors}


@router.post("/bulk-delete")
async def bulk_delete_skus(
    body: SkuBulkDelete,
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    user_id: UserId,
    _rbac: Annotated[None, require_admin],
) -> dict[str, Any]:
    from app.models.enums import IndustryCode
    from app.models.pharma import PharmaBatch

    db = request.app.state.db
    industry = IndustryCode(ctx.code)
    sids: list[uuid.UUID] = []
    for raw in body.sku_ids:
        try:
            sids.append(uuid.UUID(raw))
        except ValueError:
            continue

    if not sids:
        return {"deleted": 0}

    async with db.session(str(tenant_id)) as session:
        batch_count = (
            await session.scalar(
                select(func.count(PharmaBatch.id)).where(
                    PharmaBatch.sku_id.in_(sids), PharmaBatch.tenant_id == tenant_id
                )
            )
            or 0
        )
        if batch_count:
            raise ConflictError(
                f"Cannot delete SKUs: {batch_count} pharma batch record(s) must be retained (GxP)."
            )

        skus = (
            await session.scalars(
                select(Sku).where(
                    Sku.id.in_(sids),
                    Sku.tenant_id == tenant_id,
                    Sku.industry == industry,
                )
            )
        ).all()

        if not skus:
            return {"deleted": 0}

        for s in skus:
            await audit.record(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                action="sku.delete",
                entity_type="sku",
                entity_id=str(s.id),
                industry=industry,
                old_value={"sku_code": s.sku_code, "bulk": True},
                request_id=getattr(request.state, "request_id", None),
            )
            await session.delete(s)

    log.info("skus.bulk_deleted", deleted=len(skus))
    return {"deleted": len(skus)}


@router.delete("/all")
async def delete_all_skus(
    request: Request,
    ctx: ActiveIndustry,
    tenant_id: TenantId,
    user_id: UserId,
    _rbac: Annotated[None, require_admin],
) -> dict[str, Any]:
    """Hard-delete all SKUs for the tenant in the active industry."""
    from app.models.enums import IndustryCode
    from app.models.pharma import PharmaBatch

    db = request.app.state.db
    industry = IndustryCode(ctx.code)

    async with db.session(str(tenant_id)) as session:
        batch_count = (
            await session.scalar(
                select(func.count(PharmaBatch.id))
                .join(Sku, Sku.id == PharmaBatch.sku_id)
                .where(
                    Sku.tenant_id == tenant_id,
                    Sku.industry == industry,
                )
            )
            or 0
        )
        if batch_count:
            raise ConflictError(
                f"Cannot clear SKUs: {batch_count} pharma batch record(s) in this industry must be retained (GxP)."
            )

        skus = (
            await session.scalars(
                select(Sku).where(
                    Sku.tenant_id == tenant_id,
                    Sku.industry == industry,
                )
            )
        ).all()

        if not skus:
            return {"deleted": 0}

        for s in skus:
            await audit.record(
                session,
                tenant_id=tenant_id,
                user_id=user_id,
                action="sku.delete",
                entity_type="sku",
                entity_id=str(s.id),
                industry=industry,
                old_value={"sku_code": s.sku_code, "clear_all": True},
                request_id=getattr(request.state, "request_id", None),
            )
            await session.delete(s)

    log.info("skus.all_deleted", deleted=len(skus))
    return {"deleted": len(skus)}


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
        if "attributes" in updates:
            updates["attributes"] = _checked_attributes(ctx, updates["attributes"])
        for field, value in updates.items():
            setattr(sku, field, value)
        # updated_at is set by the database on write; load it while the session
        # is open, otherwise serialising the detached row raises after commit.
        await session.flush()
        await session.refresh(sku)

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
