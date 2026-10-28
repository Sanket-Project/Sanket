"""Bounded stock browsing without silently dropping positions after row 500."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from app.services.inventory_overview import inventory_overview


async def seed_stock(session, tenant, count=1):
    product = uuid.uuid4()
    await session.execute(text(
        "INSERT INTO products (id, tenant_id, industry, name, category) "
        "VALUES (:p,:t,'fashion','Linen shirt','Shirts')"
    ), {"p": product, "t": tenant})
    ids = [uuid.uuid4() for _ in range(count)]
    await session.execute(text(
        "INSERT INTO skus (id, tenant_id, product_id, industry, sku_code) "
        "VALUES (:s,:t,:p,'fashion',:code)"
    ), [{"s": sid, "t": tenant, "p": product, "code": f"SHIRT-{i:04}"} for i, sid in enumerate(ids)])
    await session.execute(text(
        "INSERT INTO inventory_levels (tenant_id,sku_id,industry,location,on_hand_units,reserved_units,inbound_units) "
        "VALUES (:t,:s,'fashion',:l,10,2,3)"
    ), [{"t": tenant, "s": sid, "l": loc} for sid in ids for loc in ("Hyderabad", "Warangal")])
    return ids


async def test_overview_pages_whole_skus_and_keeps_exact_counts_past_500(
    db_session, app_role_db, make_tenant
):
    tenant = await make_tenant()
    await seed_stock(db_session, tenant, 260)
    other = await make_tenant()
    await seed_stock(db_session, other, 2)
    await db_session.commit()
    async with app_role_db.session(str(tenant)) as session:
        page = await inventory_overview(session, tenant_id=tenant, industry="fashion", offset=250, limit=10)
    assert page["total_skus"] == 260
    assert page["total_positions"] == 520
    assert len(page["skus"]) == 10
    assert page["skus"][0]["sku_code"] == "SHIRT-0250"
    assert len(page["levels"]) == 20  # Never split one SKU between pages.
    assert {x["sku_id"] for x in page["coverage"]["skus"]} == {x["sku_id"] for x in page["skus"]}
    assert page["locations"] == ["Hyderabad", "Warangal"]
    assert page["totals"]["available_units"] == 4160


async def test_overview_searches_product_and_filters_store_before_pagination(
    db_session, app_role_db, make_tenant
):
    tenant = await make_tenant()
    await seed_stock(db_session, tenant, 3)
    await db_session.commit()
    async with app_role_db.session(str(tenant)) as session:
        page = await inventory_overview(session, tenant_id=tenant, industry="fashion", search="linen",
                                        location="Hyderabad", offset=0, limit=1)
        absent = await inventory_overview(session, tenant_id=tenant, industry="fashion", search="nonexistent",
                                          offset=0, limit=10)
    assert page["total_skus"] == 3
    assert page["total_positions"] == 3
    assert len(page["levels"]) == 1
    assert page["levels"][0]["location"] == "Hyderabad"
    assert page["skus"][0]["product_name"] == "Linen shirt"
    assert absent["total_skus"] == 0 and absent["coverage"]["skus"] == []


async def test_coverage_sku_filter_does_not_fetch_other_stock(
    db_session, app_role_db, make_tenant
):
    from app.services.coverage import coverage

    tenant = await make_tenant()
    ids = await seed_stock(db_session, tenant, 2)
    await db_session.commit()
    async with app_role_db.session(str(tenant)) as session:
        page = await coverage(session, tenant_id=tenant, industry="fashion", sku_ids=[ids[1]])
        empty = await coverage(session, tenant_id=tenant, industry="fashion", sku_ids=[])
    assert [x["sku_id"] for x in page["skus"]] == [str(ids[1])]
    assert empty["skus"] == []


async def test_overview_returns_only_current_page_location_recommendations(
    db_session, app_role_db, make_tenant
):
    tenant = await make_tenant()
    ids = await seed_stock(db_session, tenant, 2)
    location = uuid.uuid4()
    await db_session.execute(text(
        "INSERT INTO locations (id,tenant_id,code,name) VALUES (:l,:t,'hyderabad','Hyderabad')"
    ), {"l": location, "t": tenant})
    for sid in ids:
        await db_session.execute(text(
            "INSERT INTO recommendations (tenant_id,industry,sku_id,location_id,kind,status,headline) "
            "VALUES (:t,'fashion',:s,:l,'purchase_order','open','Order for Hyderabad')"
        ), {"t": tenant, "s": sid, "l": location})
    await db_session.commit()
    async with app_role_db.session(str(tenant)) as session:
        page = await inventory_overview(session, tenant_id=tenant, industry="fashion", limit=1)
    assert len(page["recommendations"]) == 1
    assert page["recommendations"][0]["sku_id"] == str(ids[0])
    assert page["recommendations"][0]["location"] == "hyderabad"


async def test_page_coverage_bounds_auxiliary_forecast_and_transfer_reads(
    db_session, app_role_db, make_tenant, monkeypatch
):
    from app.services.coverage import coverage

    tenant = await make_tenant()
    ids = await seed_stock(db_session, tenant, 2)
    await db_session.execute(text(
        "INSERT INTO forecast_runs (tenant_id,industry,model_stack,horizon_weeks,granularity,status,completed_at,metrics) "
        "VALUES (:t,'fashion',ARRAY['chronos_zero_shot'],8,'weekly','completed',:now,CAST(:m AS jsonb))"
    ), {"t": tenant, "now": datetime.now(UTC), "m": '{"mode":"zero_shot"}'})
    await db_session.commit()
    captured = []
    async with app_role_db.session(str(tenant)) as session:
        execute = session.execute
        async def recording_execute(statement, *args, **kwargs):
            captured.append(str(statement))
            return await execute(statement, *args, **kwargs)
        monkeypatch.setattr(session, "execute", recording_execute)
        await coverage(session, tenant_id=tenant, industry="fashion", sku_ids=[ids[0]])
    transfer_sql = next(sql for sql in captured if "FROM recommendations r" in sql)
    forecast_sql = next(sql for sql in captured if "FROM location_forecast_results f" in sql)
    assert "r.sku_id = ANY" in transfer_sql
    assert "f.sku_id = ANY" in forecast_sql


async def test_overview_excludes_stock_linked_to_another_industry_sku_or_product(
    db_session, app_role_db, make_tenant
):
    tenant = await make_tenant()
    ids = await seed_stock(db_session, tenant)
    await db_session.execute(text("UPDATE skus SET industry='electronics' WHERE id=:s"), {"s": ids[0]})
    await db_session.commit()
    async with app_role_db.session(str(tenant)) as session:
        page = await inventory_overview(session, tenant_id=tenant, industry="fashion")
    assert page["total_skus"] == 0
    await db_session.execute(text("UPDATE skus SET industry='fashion' WHERE id=:s"), {"s": ids[0]})
    await db_session.execute(text("UPDATE products SET industry='electronics' WHERE tenant_id=:t"), {"t": tenant})
    await db_session.commit()
    async with app_role_db.session(str(tenant)) as session:
        page = await inventory_overview(session, tenant_id=tenant, industry="fashion")
    assert page["total_skus"] == 0
