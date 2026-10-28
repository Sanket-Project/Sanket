"""Round-trip only the new additive schema in the disposable test database."""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import text


async def test_communication_schema_roundtrip_preserves_existing_workspaces(
    app_role_db, make_tenant
):
    tenant = await make_tenant()
    backend = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env["MIGRATION_DATABASE_URL"] = env["DATABASE_URL"]
    try:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "0033"],
            cwd=backend,
            env=env,
            capture_output=True,
            text=True,
            timeout=40,
        )
        assert result.returncode == 0, result.stderr
        async with app_role_db.session(str(tenant)) as session:
            assert (
                await session.scalar(
                    text("SELECT count(*) FROM tenants WHERE id=:tid"), {"tid": tenant}
                )
                == 1
            )
            assert (
                await session.scalar(text("SELECT to_regclass('public.communication_preferences')"))
                is None
            )
    finally:
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=backend,
            env=env,
            capture_output=True,
            text=True,
            timeout=40,
        )
        assert result.returncode == 0, result.stderr
    async with app_role_db.session(str(tenant)) as session:
        assert await session.scalar(text("SELECT count(*) FROM communication_preferences")) == 0
        assert (
            await session.scalar(
                text(
                    "SELECT relforcerowsecurity FROM pg_class WHERE relname='communication_deliveries'"
                )
            )
            is True
        )
