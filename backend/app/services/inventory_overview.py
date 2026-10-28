"""SKU-paged inventory browsing. Coverage is calculated for the page, never the catalogue."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import IndustryCode
from app.models.inventory import InventoryLevel
from app.models.product import Product, Sku
from app.models.recommendation import Recommendation
from app.models.location import Location
from app.services.coverage import coverage


async def inventory_overview(
    session: AsyncSession, *, tenant_id: uuid.UUID, industry: str,
    offset: int = 0, limit: int = 25, search: str = "", location: str = "",
    attention: str = "all", sort: str = "sku",
) -> dict[str, Any]:
    ind = IndustryCode(industry)
    scope = [InventoryLevel.tenant_id == tenant_id, InventoryLevel.industry == ind,
             Sku.tenant_id == tenant_id, Product.tenant_id == tenant_id,
             Sku.industry == ind, Product.industry == ind]
    predicates = list(scope)
    if location:
        predicates.append(InventoryLevel.location == location)
    if search.strip():
        term = "%" + search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        predicates.append(or_(Sku.sku_code.ilike(term, escape="\\"),
                              Product.name.ilike(term, escape="\\"),
                              InventoryLevel.location.ilike(term, escape="\\")))
    if attention not in {"all", "needs", "excess", "unknown"}:
        raise ValueError(f"unsupported inventory attention filter: {attention}")
    if sort not in {"sku", "available_asc", "available_desc", "freshness"}:
        raise ValueError(f"unsupported inventory sort: {sort}")
    base = select(InventoryLevel).join(Sku, Sku.id == InventoryLevel.sku_id).join(Product, Product.id == Sku.product_id).where(*predicates)
    if attention != "all":
        all_coverage = await coverage(session, tenant_id=tenant_id, industry=industry)
        matching = {
            uuid.UUID(item["sku_id"])
            for item in all_coverage["skus"]
            if (
                attention == "needs" and any(loc.get("status") in {"critical", "low"} for loc in item["locations"])
            ) or (
                attention == "excess" and any(loc.get("status") == "excess" for loc in item["locations"])
            ) or (
                attention == "unknown" and any(loc.get("status") in {None, "unknown"} for loc in item["locations"])
            )
        }
        predicates.append(Sku.id.in_(matching) if matching else Sku.id == uuid.UUID(int=0))
    filtered = base.subquery()
    totals = (await session.execute(select(
        func.count(func.distinct(filtered.c.sku_id)), func.count(),
        func.coalesce(func.sum(func.greatest(filtered.c.on_hand_units - filtered.c.reserved_units, 0)), 0),
        func.coalesce(func.sum(filtered.c.inbound_units), 0),
    ).select_from(filtered))).one()
    order_by = {
        "sku": (Sku.sku_code, Sku.id),
        "available_asc": (func.sum(func.greatest(InventoryLevel.on_hand_units - InventoryLevel.reserved_units, 0)).asc(), Sku.sku_code),
        "available_desc": (func.sum(func.greatest(InventoryLevel.on_hand_units - InventoryLevel.reserved_units, 0)).desc(), Sku.sku_code),
        "freshness": (func.max(InventoryLevel.as_of).desc(), Sku.sku_code),
    }[sort]
    sku_rows = (await session.execute(
        select(Sku.id, Sku.sku_code, Product.name)
        .join(Product, Product.id == Sku.product_id)
        .join(InventoryLevel, InventoryLevel.sku_id == Sku.id)
        .where(*predicates).group_by(Sku.id, Sku.sku_code, Product.name).order_by(*order_by).offset(offset).limit(limit)
    )).all()
    ids = [row.id for row in sku_rows]
    levels = (await session.execute(base.where(InventoryLevel.sku_id.in_(ids)).order_by(InventoryLevel.location))).scalars().all() if ids else []
    locations = list((await session.execute(
        select(InventoryLevel.location).join(Sku, Sku.id == InventoryLevel.sku_id)
        .join(Product, Product.id == Sku.product_id).where(*scope)
        .distinct().order_by(InventoryLevel.location).limit(1000)
    )).scalars().all())
    cov = await coverage(session, tenant_id=tenant_id, industry=industry, sku_ids=ids)
    recommendations = (await session.execute(
        select(Recommendation.sku_id, Recommendation.headline, Location.code)
        .join(Location, Location.id == Recommendation.location_id)
        .where(Recommendation.tenant_id == tenant_id, Recommendation.industry == ind,
               Recommendation.sku_id.in_(ids), Recommendation.status == "open",
               or_(Recommendation.expires_at.is_(None), Recommendation.expires_at > datetime.now(UTC)))
        .distinct(Recommendation.sku_id, Recommendation.location_id)
        .order_by(Recommendation.sku_id, Recommendation.location_id,
                  case((Recommendation.kind == "purchase_order", 0), else_=1), Recommendation.created_at.desc())
    )).all() if ids else []
    return {
        "industry": industry, "offset": offset, "limit": limit,
        "total_skus": int(totals[0]), "total_positions": int(totals[1]),
        "totals": {"available_units": float(totals[2]), "inbound_units": float(totals[3])},
        "locations": locations,
        "skus": [{"sku_id": str(row.id), "sku_code": row.sku_code, "product_name": row.name} for row in sku_rows],
        "levels": [{"sku_id": str(lvl.sku_id), "sku_code": next(r.sku_code for r in sku_rows if r.id == lvl.sku_id),
                    "location": lvl.location, "on_hand_units": float(lvl.on_hand_units or 0),
                    "inbound_units": float(lvl.inbound_units or 0), "reserved_units": float(lvl.reserved_units or 0),
                    "available_units": float(lvl.available_units), "as_of": lvl.as_of.isoformat() if lvl.as_of else None,
                    "source": lvl.source} for lvl in levels],
        "coverage": {"industry": industry, **cov},
        "recommendations": [{"sku_id": str(r.sku_id), "location": r.code, "headline": r.headline}
                            for r in recommendations],
    }
