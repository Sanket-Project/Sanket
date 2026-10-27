import uuid

import pytest
from sqlalchemy import text

from app.models.enums import IndustryCode
from app.services.llm.errors import AIError
from app.services.llm.policy import AIContext, PolicyStore


async def seed_workspace(db, *, industry="fashion"):
    tid, uid = uuid.uuid4(), uuid.uuid4()
    async with db.session(str(tid)) as session:
        await session.execute(text("""INSERT INTO tenants (id,slug,display_name,industry)
            VALUES (:id,:slug,'AI fixture',CAST(:industry AS industry_code))"""),
                              {"id": tid, "slug": f"ai-{tid.hex}", "industry": industry})
        await session.execute(text("""INSERT INTO users (id,tenant_id,email,full_name,role)
            VALUES (:id,:tid,:email,'AI fixture','owner')"""),
                              {"id": uid, "tid": tid, "email": f"ai-{uid.hex}@example.test"})
    return AIContext(tid, uid, IndustryCode(industry))


async def test_policy_isolation(app_role_db):
    a = await seed_workspace(app_role_db)
    b = await seed_workspace(app_role_db, industry="pharma")
    store = PolicyStore(app_role_db)
    await store.update(a, enabled=True, task_enabled=True, sharing="headers_only")
    assert (await store.load(a)).enabled
    assert not (await store.load(b)).enabled
    assert (await store.load(b)).sharing == "disabled"
    with pytest.raises(AIError, match="invalid_context"):
        await store.load(AIContext(b.tenant_id, a.user_id, b.industry))
    async with app_role_db.session(str(a.tenant_id)) as session:
        other = await session.scalar(text("SELECT settings FROM tenants WHERE id=:id"), {"id": b.tenant_id})
        assert other is None


async def test_policy_audit_failure_rolls_back(app_role_db, monkeypatch):
    from app.services import audit
    ctx = await seed_workspace(app_role_db)
    store = PolicyStore(app_role_db)

    async def fail(*args, **kwargs):
        raise RuntimeError("audit failed")

    monkeypatch.setattr(audit, "record", fail)
    with pytest.raises(RuntimeError):
        await store.update(ctx, enabled=True, task_enabled=True, sharing="redacted_samples")
    assert not (await store.load(ctx)).enabled


async def test_ai_token_meters_and_tenant_isolation(app_role_db):
    from app.models.billing import MeterKind
    from app.services import usage
    a = await seed_workspace(app_role_db)
    b = await seed_workspace(app_role_db)
    async with app_role_db.session(str(a.tenant_id)) as session:
        for meter in [MeterKind.llm_input_token, MeterKind.llm_output_token]:
            await usage.record(session, tenant_id=a.tenant_id, meter=meter, quantity=12,
                               idempotency_key=f"ai-meter-{uuid.uuid4().hex}", strict=True)
    async with app_role_db.session(str(b.tenant_id)) as session:
        assert await session.scalar(text("SELECT count(*) FROM usage_events WHERE tenant_id=:tid"),
                                    {"tid": a.tenant_id}) == 0
    from sqlalchemy.exc import DBAPIError
    with pytest.raises(DBAPIError):
        async with app_role_db.session(str(b.tenant_id)) as session:
            await usage.record(session, tenant_id=a.tenant_id, meter=MeterKind.llm_input_token,
                               quantity=1, strict=True)


async def test_usage_idempotency_across_transactions(app_role_db):
    from app.models.billing import MeterKind
    from app.services import usage
    ctx = await seed_workspace(app_role_db)
    key = f"ai-replay-{uuid.uuid4().hex}"
    for _ in range(2):
        async with app_role_db.session(str(ctx.tenant_id)) as session:
            await usage.record(session, tenant_id=ctx.tenant_id, meter=MeterKind.api_request,
                               quantity=1, idempotency_key=key, strict=True)
    async with app_role_db.session(str(ctx.tenant_id)) as session:
        assert await session.scalar(text("SELECT count(*) FROM usage_events WHERE idempotency_key=:key"),
                                    {"key": key}) == 1


async def test_telemetry_atomic_idempotent_and_scoped(app_role_db):
    from test_config import settings

    from app.services.llm.errors import TokenUsage
    from app.services.llm.policy import Policy
    from app.services.llm.telemetry import Telemetry
    ctx = await seed_workspace(app_role_db)
    other = await seed_workspace(app_role_db)
    telemetry = Telemetry(app_role_db, settings())
    attempt = uuid.uuid4()
    policy = Policy(True, True, "headers_only")
    for _ in range(2):
        await telemetry.record(ctx, attempt, "started", policy=policy)
        await telemetry.record(ctx, attempt, "finished", policy=policy, usage=TokenUsage(12, 8))
    async with app_role_db.session(str(ctx.tenant_id)) as session:
        assert await session.scalar(text("SELECT count(*) FROM audit_log WHERE request_id=:id"),
                                    {"id": str(attempt)}) == 2
        assert await session.scalar(text("SELECT sum(quantity) FROM usage_events WHERE tenant_id=:id"),
                                    {"id": ctx.tenant_id}) == 20
    async with app_role_db.session(str(other.tenant_id)) as session:
        assert await session.scalar(text("SELECT count(*) FROM audit_log WHERE request_id=:id"),
                                    {"id": str(attempt)}) == 0


async def test_telemetry_records_actual_registered_task(app_role_db):
    from dataclasses import replace
    from test_config import settings
    from app.services.llm.policy import Policy
    from app.services.llm.telemetry import Telemetry
    ctx = replace(await seed_workspace(app_role_db), task_name="planning_brief")
    attempt = uuid.uuid4()
    await Telemetry(app_role_db, settings()).record(ctx, attempt, "started", policy=Policy(True, True, "headers_only", True))
    async with app_role_db.session(str(ctx.tenant_id)) as session:
        metadata = await session.scalar(text("SELECT new_value FROM audit_log WHERE request_id=:id"), {"id": str(attempt)})
        assert metadata["task"] == "planning_brief"
        assert metadata["schema_version"] == "1"


async def test_telemetry_failure_rolls_back_pair(app_role_db, monkeypatch):
    from test_config import settings

    from app.services import audit
    from app.services.llm.errors import TokenUsage
    from app.services.llm.policy import Policy
    from app.services.llm.telemetry import Telemetry
    ctx = await seed_workspace(app_role_db)
    telemetry = Telemetry(app_role_db, settings())
    async def fail(*args, **kwargs):
        raise RuntimeError("private error")
    monkeypatch.setattr(audit, "record", fail)
    with pytest.raises(AIError, match="accounting_unavailable"):
        await telemetry.record(ctx, uuid.uuid4(), "finished", policy=Policy(True, True, "headers_only"),
                               usage=TokenUsage(12, 8))
    async with app_role_db.session(str(ctx.tenant_id)) as session:
        assert await session.scalar(text("SELECT count(*) FROM usage_events WHERE tenant_id=:id"),
                                    {"id": ctx.tenant_id}) == 0


async def test_policy_mutation_waits_for_inflight_actor_demotion(app_role_db):
    import asyncio
    ctx = await seed_workspace(app_role_db)
    store = PolicyStore(app_role_db)
    async with app_role_db.session(str(ctx.tenant_id)) as demotion:
        await demotion.execute(text("UPDATE users SET role='viewer' WHERE id=:id"), {"id": ctx.user_id})
        change = asyncio.create_task(store.update(ctx, enabled=True, task_enabled=True, sharing="redacted_samples"))
        await asyncio.sleep(0.1)
        assert not change.done(), "Policy changes must serialize with a current actor demotion"
    with pytest.raises(AIError, match="invalid_context"):
        await change
    assert not (await store.load(ctx)).enabled
