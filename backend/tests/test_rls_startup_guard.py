"""An unsuccessful inspection cannot establish tenant isolation."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.database import Database


def database_with_inspection(role=(False, False), forced=True, error=None):
    db = object.__new__(Database)
    conn = AsyncMock()
    conn.execute.return_value = MagicMock()
    conn.execute.return_value.first.return_value = role
    conn.scalar.return_value = forced
    if error:
        conn.execute.side_effect = error
    db._engine = MagicMock()
    db._engine.connect.return_value.__aenter__.return_value = conn
    return db


async def test_strict_inspection_error_aborts_startup():
    db = database_with_inspection(error=OSError("inspection unavailable"))
    with pytest.raises(RuntimeError, match="tenant isolation"):
        await db.assert_tenant_isolation_enforced(strict=True)


@pytest.mark.parametrize("role,forced", [(None, True), ((False, False), None)])
async def test_strict_missing_metadata_aborts_startup(role, forced):
    db = database_with_inspection(role, forced)
    with pytest.raises(RuntimeError, match="tenant isolation"):
        await db.assert_tenant_isolation_enforced(strict=True)


async def test_verified_unprivileged_role_can_start():
    await database_with_inspection().assert_tenant_isolation_enforced(strict=True)


async def test_development_inspection_failure_remains_warning_only():
    await database_with_inspection(error=OSError("unavailable")).assert_tenant_isolation_enforced(strict=False)


async def test_production_checks_isolation_before_starting_other_services(monkeypatch):
    from types import SimpleNamespace
    from fastapi import FastAPI
    from app import main

    db = AsyncMock(spec=Database)
    db.assert_tenant_isolation_enforced.side_effect = RuntimeError("tenant isolation unverified")
    monkeypatch.setattr(main, "Database", lambda settings: db)
    monkeypatch.setattr(main, "get_settings", lambda: SimpleNamespace(is_production=True, redis_url=None))
    monkeypatch.setattr(main, "configure_logging", lambda settings: None)
    redis = AsyncMock(side_effect=AssertionError("Services started before isolation verification"))
    monkeypatch.setattr(main, "_init_redis", redis)
    with pytest.raises(RuntimeError, match="tenant isolation"):
        async with main.lifespan(FastAPI()):
            pytest.fail("Startup succeeded without verified isolation")
    redis.assert_not_called()
    db.close.assert_awaited_once()
