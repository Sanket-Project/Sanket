import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError


async def workspace(db):
    tid = uuid.uuid4()
    async with db.session(str(tid)) as session:
        await session.execute(text("INSERT INTO tenants (id,slug,display_name,industry) VALUES (:t,:s,'Import test','fashion')"),
                              {"t": tid, "s": f"import-{tid.hex}"})
    return tid


async def test_profiles_isolated_and_conflicting_revision_rejected(app_role_db):
    from app.services.integrations.import_profiles import load_profile, save_profile
    a, b = await workspace(app_role_db), await workspace(app_role_db)
    async with app_role_db.session(str(a)) as session:
        await save_profile(session, a, "sales", "a" * 64, {"quantity": "c1"}, {"c1": "integer"}, expected_revision=0)
    async with app_role_db.session(str(b)) as session:
        assert await load_profile(session, b, "sales", "a" * 64) is None
        assert await load_profile(session, a, "sales", "a" * 64) is None
    async with app_role_db.session(str(a)) as session:
        profile = await load_profile(session, a, "sales", "a" * 64)
        assert profile["revision"] == 1
        assert profile["mapping"] == {"quantity": "c1"}
        assert await load_profile(session, a, "inventory", "a" * 64) is None
        with pytest.raises(ValueError, match="changed"):
            await save_profile(session, a, "sales", "a" * 64, {"quantity": "c2"}, {}, expected_revision=0)
    with pytest.raises(DBAPIError):
        async with app_role_db.session(str(b)) as session:
            await save_profile(session, a, "sales", "b" * 64, {}, {}, expected_revision=0)


async def test_profile_write_rolls_back_with_import_transaction(app_role_db):
    from app.services.integrations.import_profiles import load_profile, save_profile
    tid = await workspace(app_role_db)
    with pytest.raises(RuntimeError):
        async with app_role_db.session(str(tid)) as session:
            await save_profile(session, tid, "sales", "c" * 64, {}, {}, expected_revision=0)
            raise RuntimeError("business write failed")
    async with app_role_db.session(str(tid)) as session:
        assert await load_profile(session, tid, "sales", "c" * 64) is None


async def test_profile_management_requires_admin_and_rejects_foreign_ids(app_role_db):
    from app.services.integrations.import_profiles import save_profile, list_profiles, manage_profile
    from test_import_confirmation import seed
    ctx = await seed(app_role_db)
    other = await seed(app_role_db)
    async with app_role_db.session(str(ctx.tenant_id)) as s:
        await save_profile(s, ctx.tenant_id, "sales", "e" * 64, {}, {}, expected_revision=0)
    profile = (await list_profiles(app_role_db, ctx))[0]
    with pytest.raises(ValueError):
        await manage_profile(app_role_db, other, profile["id"], expected_revision=1, disabled=True)
    await manage_profile(app_role_db, ctx, profile["id"], expected_revision=1, disabled=True)
    assert (await list_profiles(app_role_db, ctx))[0]["disabled"] is True
    await manage_profile(app_role_db, ctx, profile["id"], expected_revision=2, disabled=None)
    assert not await list_profiles(app_role_db, ctx)
