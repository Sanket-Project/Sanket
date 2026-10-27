import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from test_import_confirmation import seed


async def future_sale(db, ctx):
    async with db.session(str(ctx.tenant_id)) as s:
        await s.execute(text("""INSERT INTO historical_sales
            (id,tenant_id,sku_id,industry,sale_time,channel,units_sold)
            VALUES (:id,:tid,:sku,'fashion',:when,'test',2)"""),
            {"id": uuid.uuid4(), "tid": ctx.tenant_id, "sku": uuid.uuid4(), "when": datetime.now(UTC) + timedelta(days=1)})


async def test_quality_fix_preview_rejects_stale_record_set(app_role_db):
    from app.services.llm.quality_review import preview_fix, confirm_fix
    ctx = await seed(app_role_db)
    await future_sale(app_role_db, ctx)
    preview = await preview_fix(app_role_db, ctx, "test-key-32-characters-long-123456", "drop_future_sales")
    assert preview["rows_affected"] == 1
    await future_sale(app_role_db, ctx)
    with pytest.raises(ValueError, match="changed"):
        await confirm_fix(app_role_db, ctx, "test-key-32-characters-long-123456", "drop_future_sales", preview["preview_token"])
    async with app_role_db.session(str(ctx.tenant_id)) as s:
        assert await s.scalar(text("SELECT count(*) FROM historical_sales WHERE tenant_id=:t"), {"t": ctx.tenant_id}) == 2


async def test_confirmed_future_sale_repair_uses_rls_role_and_atomic_audit(app_role_db, monkeypatch):
    from app.services.llm.quality_review import preview_fix, confirm_fix
    from app.services import audit
    ctx = await seed(app_role_db)
    await future_sale(app_role_db, ctx)
    other = await seed(app_role_db)
    await future_sale(app_role_db, other)
    secret = "test-key-32-characters-long-123456"
    preview = await preview_fix(app_role_db, ctx, secret, "drop_future_sales")
    result = await confirm_fix(app_role_db, ctx, secret, "drop_future_sales", preview["preview_token"])
    assert result["rows_affected"] == 1
    assert result["applied"]
    with pytest.raises(ValueError):
        await confirm_fix(app_role_db, other, secret, "drop_future_sales", preview["preview_token"])
    async with app_role_db.session(str(other.tenant_id)) as s:
        assert await s.scalar(text("SELECT count(*) FROM historical_sales WHERE tenant_id=:t"), {"t": other.tenant_id}) == 1
        assert not await s.scalar(text("SELECT has_table_privilege(current_user,'historical_sales','DELETE')"))
        assert not await s.scalar(text("SELECT rolsuper OR rolbypassrls OR rolcanlogin FROM pg_roles WHERE rolname='sanket_sales_repair'"))


async def test_repair_audit_failure_rolls_back_deletions(app_role_db, monkeypatch):
    from app.services.llm.quality_review import preview_fix, confirm_fix
    from app.services import audit
    ctx = await seed(app_role_db)
    await future_sale(app_role_db, ctx)
    secret = "test-key-32-characters-long-123456"
    preview = await preview_fix(app_role_db, ctx, secret, "drop_future_sales")
    async def fail(*args, **kwargs):
        raise RuntimeError("audit write failed")
    monkeypatch.setattr(audit, "record", fail)
    with pytest.raises(RuntimeError):
        await confirm_fix(app_role_db, ctx, secret, "drop_future_sales", preview["preview_token"])
    async with app_role_db.session(str(ctx.tenant_id)) as s:
        assert await s.scalar(text("SELECT count(*) FROM historical_sales WHERE tenant_id=:t"), {"t": ctx.tenant_id}) == 1
