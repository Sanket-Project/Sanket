"""Scoped proposals and explicit, concurrency-checked product attribute patches."""
import hashlib
import json
import uuid

from sqlalchemy import select

from app.models.product import Product, Sku
from app.services import audit
from app.services.industry_context import get_industry_context
from app.services.llm.cleanup import CleanupInput
from app.services.llm.policy import PolicyStore
from app.services.llm.tasks import request_for

_CATEGORY_HINTS = {
    "fashion": ["Women's Apparel", "Men's Apparel", "Footwear", "Accessories", "Bags"],
    "electronics": ["Smartphones", "Laptops", "Audio", "Smart Home", "Tablets", "Accessories"],
    "pharma": ["Oncology", "Allergy", "Metabolic", "Antibiotics", "Cardiovascular"],
    "agrocenter": ["Fertilizers", "Seeds", "Pesticides", "Irrigation", "Soil Amendments"],
    "hardware": ["Power Tools", "Fasteners", "Electrical", "Plumbing", "Building Materials", "Safety"],
}


def _revision(sku, product):
    body = [sku.attributes, product.attributes, product.category, product.name, str(sku.updated_at), str(product.updated_at)]
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()


async def _rows(session, ctx, ids, *, lock=False):
    if not 1 <= len(ids) <= 40 or len(set(map(str, ids))) != len(ids):
        raise ValueError("Select between one and forty distinct SKUs")
    ids = [uuid.UUID(str(value)) for value in ids]
    query = select(Sku, Product).join(Product, Sku.product_id == Product.id).where(
        Sku.tenant_id == ctx.tenant_id, Sku.industry == ctx.industry, Sku.id.in_(ids),
        Product.tenant_id == ctx.tenant_id, Product.industry == ctx.industry).order_by(Sku.id)
    records = (await session.execute(query.with_for_update() if lock else query)).all()
    if len(records) != len(ids):
        raise ValueError("A selected product is unavailable in this workspace")
    return records


async def current_products(db, ctx, ids):
    async with db.session(str(ctx.tenant_id)) as session:
        await PolicyStore(db)._rows(session, ctx)
        return [{"id": str(sku.id), "product_id": str(product.id), "name": product.name,
                 "attributes": dict(sku.attributes or {}), "category": product.category,
                 "revision": _revision(sku, product)} for sku, product in await _rows(session, ctx, ids)]


async def suggest_cleanup(db, ai, ctx, ids):
    policy = await PolicyStore(db).load(ctx)
    if not policy.enabled or not policy.task_enabled:
        return {"state": "disabled", "suggestions": [], "duplicate_pairs": [], "products": []}
    if policy.sharing == "disabled" or not policy.product_names:
        return {"state": "policy_blocked", "suggestions": [], "duplicate_pairs": [], "products": []}
    products = await current_products(db, ctx, ids)
    categories = sorted(set(_CATEGORY_HINTS[ctx.industry.value] + [p["category"] for p in products]))
    data = CleanupInput.model_validate({"industry": ctx.industry.value, "categories": categories,
                                       "products": [{k: p[k] for k in ("id", "name", "revision")} for p in products]})
    if ai is None:
        return {"state": "unavailable", "suggestions": [], "duplicate_pairs": [], "products": products}
    result = await ai.run(ctx, request_for("product_cleanup", data.model_dump()))
    return {"state": result.state, "products": products,
            **(result.value.model_dump(mode="json") if result.state == "success" else {"suggestions": [], "duplicate_pairs": []})}


async def apply_cleanup(db, ctx, changes, *, confirm=False):
    if not isinstance(changes, list) or not 1 <= len(changes) <= 160:
        raise ValueError("Select the changes to review")
    if any(not isinstance(c, dict) or set(c) != {"sku_id", "field", "value", "revision"} for c in changes):
        raise ValueError("Invalid cleanup change")
    identities = [(str(c["sku_id"]), c["field"]) for c in changes]
    if len(set(identities)) != len(identities):
        raise ValueError("Duplicate cleanup fields")
    industry = get_industry_context(ctx.industry.value)
    async with db.session(str(ctx.tenant_id)) as session:
        user, _, _ = await PolicyStore(db)._rows(session, ctx, lock=confirm)
        if user.role not in {"owner", "admin"}:
            raise ValueError("Product cleanup requires an owner or admin")
        records = await _rows(session, ctx, list(dict.fromkeys(c["sku_id"] for c in changes)), lock=confirm)
        lookup = {str(sku.id): (sku, product, _revision(sku, product)) for sku, product in records}
        preview = []
        for change in changes:
            sku, product, revision = lookup[str(change["sku_id"])]
            if change["revision"] != revision:
                raise ValueError("Product changed; review fresh suggestions")
            key, value = change["field"], change["value"]
            if key not in {"category", "size", "color", "material", "season", "gender"} or not isinstance(value, str) or not 1 <= len(value) <= 100:
                raise ValueError("Unsupported cleanup field or value")
            if key != "category":
                if key not in industry.sku_attribute_schema:
                    raise ValueError("Attribute is unsupported for this industry")
                normalized = industry.normalize_sku_attributes({key: value})
                if industry.validate_sku_attributes(normalized):
                    raise ValueError("Invalid industry attribute")
                value = normalized[key]
            old = product.category if key == "category" else (sku.attributes or {}).get(key)
            preview.append({**change, "value": value, "before": old, "product_id": str(product.id)})
        categories = {}
        for change in preview:
            if change["field"] == "category":
                previous = categories.setdefault(change["product_id"], change["value"])
                if previous != change["value"]:
                    raise ValueError("Conflicting categories were proposed for variants of the same product")
        if confirm:
            for change in preview:
                sku, product, _ = lookup[str(change["sku_id"])]
                if change["field"] == "category":
                    product.category = change["value"]
                else:
                    sku.attributes = {**(sku.attributes or {}), change["field"]: change["value"]}
            await audit.record(session, tenant_id=ctx.tenant_id, user_id=ctx.user_id, industry=ctx.industry,
                               action="ai.cleanup.confirmed", entity_type="sku", strict=True,
                               new_value={"records": len(records), "fields": [c["field"] for c in preview]})
        return {"applied": confirm, "changes": preview}
