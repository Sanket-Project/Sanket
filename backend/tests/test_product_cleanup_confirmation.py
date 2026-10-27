import uuid

import pytest
from sqlalchemy import text

from test_import_confirmation import seed


async def product(db, ctx):
    pid, sid = uuid.uuid4(), uuid.uuid4()
    async with db.session(str(ctx.tenant_id)) as s:
        await s.execute(text("INSERT INTO products (id,tenant_id,industry,name,category) VALUES (:p,:t,'fashion','Blue Cotton Shirt XL','Shirts')"), {"p": pid, "t": ctx.tenant_id})
        await s.execute(text("INSERT INTO skus (id,tenant_id,industry,product_id,sku_code) VALUES (:s,:t,'fashion',:p,'CLEAN-A')"), {"s": sid, "t": ctx.tenant_id, "p": pid})
    return pid, sid


async def test_cleanup_confirmation_is_scoped_revision_checked_and_audited(app_role_db):
    from app.services.llm.product_cleanup import current_products, apply_cleanup
    ctx = await seed(app_role_db)
    pid, sid = await product(app_role_db, ctx)
    before = await current_products(app_role_db, ctx, [sid])
    change = {"sku_id": str(sid), "field": "size", "value": "XL", "revision": before[0]["revision"]}
    result = await apply_cleanup(app_role_db, ctx, [change], confirm=False)
    assert result["applied"] is False
    async with app_role_db.session(str(ctx.tenant_id)) as s:
        assert (await s.scalar(text("SELECT attributes FROM skus WHERE id=:s"), {"s": sid})) == {}
    assert (await apply_cleanup(app_role_db, ctx, [change], confirm=True))["applied"] is True
    async with app_role_db.session(str(ctx.tenant_id)) as s:
        assert (await s.scalar(text("SELECT attributes FROM skus WHERE id=:s"), {"s": sid}))["size"] == "XL"
        assert await s.scalar(text("SELECT count(*) FROM audit_log WHERE tenant_id=:t AND action='ai.cleanup.confirmed'"), {"t": ctx.tenant_id}) == 1
    with pytest.raises(ValueError, match="changed"):
        await apply_cleanup(app_role_db, ctx, [change], confirm=True)
    other = await seed(app_role_db)
    with pytest.raises(ValueError):
        await apply_cleanup(app_role_db, other, [change], confirm=True)


async def test_cleanup_rejects_economic_fields_and_rolls_back_if_audit_fails(app_role_db, monkeypatch):
    from app.services.llm.product_cleanup import current_products, apply_cleanup
    from app.services import audit
    ctx = await seed(app_role_db)
    _, sid = await product(app_role_db, ctx)
    before = await current_products(app_role_db, ctx, [sid])
    change = {"sku_id": str(sid), "field": "unit_price", "value": "100", "revision": before[0]["revision"]}
    with pytest.raises(ValueError):
        await apply_cleanup(app_role_db, ctx, [change], confirm=True)
    change.update(field="color", value="Blue")
    async def fail(*args, **kwargs):
        raise RuntimeError("audit unavailable")
    monkeypatch.setattr(audit, "record", fail)
    with pytest.raises(RuntimeError):
        await apply_cleanup(app_role_db, ctx, [change], confirm=True)
    assert (await current_products(app_role_db, ctx, [sid]))[0]["attributes"] == {}


async def test_cleanup_api_disabled_does_not_load_product_names(client, signed_in_workspace):
    _, headers = await signed_in_workspace("fashion")
    response = await client.post("/api/v1/ai/product-cleanup", headers=headers, json={"sku_ids": [str(uuid.uuid4())]})
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "disabled"
    invalid = await client.post("/api/v1/ai/product-cleanup/confirm", headers=headers, json={"confirm": True,
        "changes": [{"sku_id": str(uuid.uuid4()), "field": "unit_price", "value": "900", "revision": "revision"}]})
    assert invalid.status_code == 422


async def test_variant_category_conflicts_do_not_silently_overwrite_each_other(app_role_db):
    from app.services.llm.product_cleanup import current_products, apply_cleanup
    ctx = await seed(app_role_db)
    pid, first = await product(app_role_db, ctx)
    second = uuid.uuid4()
    async with app_role_db.session(str(ctx.tenant_id)) as s:
        await s.execute(text("INSERT INTO skus (id,tenant_id,industry,product_id,sku_code) VALUES (:s,:t,'fashion',:p,'CLEAN-B')"),
                        {"s": second, "t": ctx.tenant_id, "p": pid})
    products = await current_products(app_role_db, ctx, [first, second])
    changes = [{"sku_id": p["id"], "field": "category", "value": category, "revision": p["revision"]}
               for p, category in zip(products, ["Shirts", "Accessories"], strict=True)]
    with pytest.raises(ValueError, match="Conflicting"):
        await apply_cleanup(app_role_db, ctx, changes, confirm=True)
