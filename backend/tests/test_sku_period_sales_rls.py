import uuid
from datetime import date

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from test_import_profiles_rls import workspace


async def sku(db, tid):
    pid, sid = uuid.uuid4(), uuid.uuid4()
    async with db.session(str(tid)) as s:
        await s.execute(text("""INSERT INTO products (id,tenant_id,industry,name,category,status,attributes)
            VALUES (:p,:t,'fashion','P','C','active','{}')"""), {"p": pid, "t": tid})
        await s.execute(text("""INSERT INTO skus (id,tenant_id,product_id,industry,sku_code,currency,moq,
            safety_stock,reorder_point,attributes,is_active)
            VALUES (:s,:t,:p,'fashion','A-1','INR',1,0,0,'{}',true)"""), {"s": sid, "t": tid, "p": pid})
    return sid


INSERT = text("""INSERT INTO sku_period_sales (tenant_id,sku_id,location,period_start,period_end,units,source)
    VALUES (:t,:s,'ALWAL',:a,:b,:u,'smart_import')""")


async def test_period_sales_isolated_between_tenants(app_role_db):
    a, b = await workspace(app_role_db), await workspace(app_role_db)
    sid = await sku(app_role_db, a)
    async with app_role_db.session(str(a)) as s:
        await s.execute(INSERT, {"t": a, "s": sid, "a": date(2026, 1, 1), "b": date(2026, 10, 25), "u": 22})
    async with app_role_db.session(str(b)) as s:
        assert await s.scalar(text("SELECT count(*) FROM sku_period_sales")) == 0
    with pytest.raises(DBAPIError):
        async with app_role_db.session(str(b)) as s:
            await s.execute(INSERT, {"t": a, "s": sid, "a": date(2026, 1, 1), "b": date(2026, 2, 1), "u": 1})


async def test_period_sales_rejects_reversed_period(app_role_db):
    tid = await workspace(app_role_db)
    sid = await sku(app_role_db, tid)
    with pytest.raises(DBAPIError):
        async with app_role_db.session(str(tid)) as s:
            await s.execute(INSERT, {"t": tid, "s": sid, "a": date(2026, 10, 25), "b": date(2026, 1, 1), "u": 1})


async def test_period_sales_keeps_net_returns(app_role_db):
    """Net units can be negative when a period's returns exceed its sales."""
    tid = await workspace(app_role_db)
    sid = await sku(app_role_db, tid)
    async with app_role_db.session(str(tid)) as s:
        await s.execute(INSERT, {"t": tid, "s": sid, "a": date(2026, 1, 1), "b": date(2026, 1, 2), "u": -1})
        assert await s.scalar(text("SELECT units FROM sku_period_sales")) == -1


async def test_period_sales_one_row_per_sku_location_period(app_role_db):
    tid = await workspace(app_role_db)
    sid = await sku(app_role_db, tid)
    async with app_role_db.session(str(tid)) as s:
        await s.execute(INSERT, {"t": tid, "s": sid, "a": date(2026, 1, 1), "b": date(2026, 10, 25), "u": 22})
    with pytest.raises(DBAPIError):
        async with app_role_db.session(str(tid)) as s:
            await s.execute(INSERT, {"t": tid, "s": sid, "a": date(2026, 1, 1), "b": date(2026, 10, 25), "u": 5})
