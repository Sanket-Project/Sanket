"""location_forecast_results: partitioned, RLS-isolated, maintained (spec §4.3)."""
from __future__ import annotations

import uuid

from sqlalchemy import text


async def test_partitioned_and_maintained(db_session):
    kind = await db_session.scalar(text(
        "SELECT c.relkind::text FROM pg_class c WHERE c.relname = 'location_forecast_results'"))
    assert kind == "p"
    parents = (await db_session.execute(
        text("SELECT parent FROM sanket_maintain_partitions()"))).scalars().all()
    assert {"historical_sales", "forecast_results", "trend_signals",
            "location_forecast_results"} <= set(parents)


async def test_rls_isolated(db_session, app_role_db, make_tenant):
    a, b = await make_tenant(), await make_tenant()
    for t in (a, b):
        run = uuid.uuid4()
        await db_session.execute(text(
            "INSERT INTO forecast_runs (id, tenant_id, industry, model_stack, horizon_weeks, "
            "granularity, status) VALUES (:r, :t, 'fashion', ARRAY['x'], 4, 'weekly', 'completed')"),
            {"r": str(run), "t": str(t)})
        await db_session.execute(text(
            "INSERT INTO location_forecast_results (tenant_id, run_id, sku_id, location_id, "
            "forecast_date, p10, p50, p90, share, share_basis, method) VALUES "
            "(:t, :r, gen_random_uuid(), gen_random_uuid(), current_date, 1, 2, 3, 0.5, "
            "'sku_history', 'share_split_v1')"), {"t": str(t), "r": str(run)})
    await db_session.commit()
    async with app_role_db.session(str(a)) as s:
        n = await s.scalar(text("SELECT count(*) FROM location_forecast_results"))
    assert n == 1
