import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import text
from test_rls import seed_workspace


async def test_additive_downgrade_preserves_usage(app_role_db):
    from app.models.billing import MeterKind
    from app.services import usage
    ctx = await seed_workspace(app_role_db)
    async with app_role_db.session(str(ctx.tenant_id)) as session:
        await usage.record(session, tenant_id=ctx.tenant_id, meter=MeterKind.llm_input_token,
                           quantity=7, strict=True)
    backend = Path(__file__).resolve().parents[2]
    env = dict(os.environ)
    env["MIGRATION_DATABASE_URL"] = env["DATABASE_URL"]
    try:
        result = subprocess.run([sys.executable, "-m", "alembic", "downgrade", "0029"],
                                cwd=backend, env=env, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
        async with app_role_db.session(str(ctx.tenant_id)) as session:
            assert await session.scalar(text("SELECT sum(quantity) FROM usage_events")) == 7
            await usage.record(session, tenant_id=ctx.tenant_id, meter=MeterKind.api_request,
                               quantity=1, strict=True)
    finally:
        result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                                cwd=backend, env=env, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
