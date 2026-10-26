"""A forecast run is not silently truncated to 50 SKUs (spec §2, Phase 0)."""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import text

from app.schemas.trends import HybridForecastRequest
from app.services import hybrid_forecast


async def _skus(db, tenant, n):
    pid = uuid.uuid4()
    await db.execute(
        text("INSERT INTO products (id, tenant_id, industry, name, category, status) "
             "VALUES (:p, :t, 'fashion', 'Kurti', 'Kurtis', 'active')"),
        {"p": str(pid), "t": str(tenant)},
    )
    ids = []
    for i in range(n):
        sid = uuid.uuid4()
        ids.append(sid)
        await db.execute(
            text("INSERT INTO skus (id, tenant_id, product_id, industry, sku_code) "
                 "VALUES (:s, :t, :p, 'fashion', :c)"),
            {"s": str(sid), "t": str(tenant), "p": str(pid), "c": f"SKU-{i:03d}"},
        )
    return ids


async def test_run_keeps_more_than_fifty_skus(db_session, app_role_db, make_tenant, monkeypatch):
    tenant = await make_tenant()
    ids = await _skus(db_session, tenant, 60)
    await db_session.commit()

    async def fake_baseline(tenant_id, industry, horizon_weeks, http_client=None):
        start = date(2026, 10, 26)
        return {"source": "zero_shot", "rows": [
            {"sku_id": str(s), "forecast_date": (start + timedelta(weeks=w)).isoformat(),
             "p10": 1.0, "p50": 2.0, "p90": 3.0}
            for s in ids for w in range(4)
        ]}

    monkeypatch.setattr(hybrid_forecast, "_fetch_ml_baseline", fake_baseline)
    result = await hybrid_forecast.compute_hybrid_forecast(
        db=app_role_db, http_client=None, realtime=None, run_id=uuid.uuid4(),
        tenant_id=tenant, industry_code="fashion",
        body=HybridForecastRequest(horizon_weeks=4, include_alerts=False),
    )
    assert len(result.out.series) == 60
