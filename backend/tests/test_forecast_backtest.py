"""POST /forecasts/backtest — an explicit, leakage-free historical forecast (F02).

Production accuracy only scores forecasts that existed before their week began,
so "how would this have done last quarter?" needs its own, clearly labelled
path: the model sees only history before ``cutoff``.
"""

from __future__ import annotations

from datetime import date, timedelta

import httpx
import pytest
from sqlalchemy import text

from app.models.enums import IndustryCode
from app.routers import forecasts as forecasts_router
from app.services.integrations import file_import as fi


def _this_monday() -> date:
    today = date.today()
    return today - timedelta(days=today.weekday())


@pytest.fixture
def ml_calls(monkeypatch):
    calls: list[dict] = []

    async def fake_post(request, url, payload, headers, timeout):
        calls.append({"url": url, "payload": payload})
        return httpx.Response(200, json={"rows": [], "source": "chronos_zero_shot"},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(forecasts_router, "_post_to_ml", fake_post)
    return calls


async def test_backtest_sends_the_cutoff_and_forces_zero_shot(client, signed_in_workspace, ml_calls):
    _, headers = await signed_in_workspace()

    r = await client.post(
        "/api/v1/forecasts/backtest", headers=headers, json={"cutoff": "2026-08-31", "horizon": 8}
    )

    assert r.status_code == 200, r.text
    payload = ml_calls[0]["payload"]
    assert payload["history_end"] == "2026-08-31"
    assert payload["force_zero_shot"] is True
    assert payload["horizon"] == 8


@pytest.mark.parametrize(
    "cutoff",
    ["2026-08-30", "2026-09-01"],  # Sunday, Tuesday
)
async def test_cutoff_must_be_a_monday(client, signed_in_workspace, ml_calls, cutoff):
    _, headers = await signed_in_workspace()
    r = await client.post("/api/v1/forecasts/backtest", headers=headers, json={"cutoff": cutoff})
    assert r.status_code == 422
    assert ml_calls == []


async def test_cutoff_must_be_in_the_past(client, signed_in_workspace, ml_calls):
    _, headers = await signed_in_workspace()
    r = await client.post(
        "/api/v1/forecasts/backtest", headers=headers, json={"cutoff": _this_monday().isoformat()}
    )
    assert r.status_code == 422
    assert ml_calls == []


async def test_backtest_is_gated_on_duplicates(client, app_role_db, signed_in_workspace, ml_calls):
    tenant, headers = await signed_in_workspace()
    h, recs = fi.parse_table("s.csv", b"order_id,sku,date,quantity\nB-1,KURTI-M,2026-08-24,3")
    await fi.import_rows(db=app_role_db, tenant_id=tenant, industry=IndustryCode.fashion,
                         kind="sales", headers=h, records=recs)
    async with app_role_db.session(str(tenant)) as s:
        await s.execute(text(
            "INSERT INTO historical_sales (tenant_id, sku_id, industry, sale_time, channel, units_sold, "
            "gross_revenue, net_revenue, returns, in_stock, promo_flag, markdown_pct, record_key, metadata) "
            "SELECT tenant_id, sku_id, industry, sale_time, channel, units_sold, gross_revenue, "
            "net_revenue, returns, in_stock, promo_flag, markdown_pct, record_key, metadata "
            "FROM historical_sales"
        ))

    r = await client.post("/api/v1/forecasts/backtest", headers=headers, json={"cutoff": "2026-08-31"})

    assert r.status_code == 409
    assert ml_calls == []
