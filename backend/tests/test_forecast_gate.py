"""Forecasting is refused while confirmed duplicate sales exist (audit F01).

The audit's duplicated workspace forecast from doubled history (97.45% WAPE)
while Data Quality already knew the history was corrupt. Generating a forecast,
a hybrid run, or a decision refresh now stops with 409 until the copies are
removed. The ML service is unreachable in tests (conftest), so a request that
passes the gate fails afterwards with 503 — proving the gate runs first.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.models.enums import IndustryCode
from app.services.integrations import file_import as fi


async def _import_and_duplicate(app_role_db, tenant) -> None:
    headers, records = fi.parse_table(
        "s.csv", b"order_id,sku,date,quantity\nG-1,KURTI-M,2026-08-24,3\nG-2,KURTI-L,2026-08-24,4"
    )
    await fi.import_rows(
        db=app_role_db, tenant_id=tenant, industry=IndustryCode.fashion, kind="sales",
        headers=headers, records=records,
    )
    async with app_role_db.session(str(tenant)) as s:
        await s.execute(
            text(
                "INSERT INTO historical_sales (tenant_id, sku_id, industry, sale_time, channel, "
                "units_sold, gross_revenue, net_revenue, returns, in_stock, promo_flag, "
                "markdown_pct, record_key, metadata) SELECT tenant_id, sku_id, industry, sale_time, "
                "channel, units_sold, gross_revenue, net_revenue, returns, in_stock, promo_flag, "
                "markdown_pct, record_key, metadata FROM historical_sales"
            )
        )


@pytest.mark.parametrize(
    ("path", "body"),
    [
        ("/api/v1/forecasts/generate", {"horizon": 8}),
        ("/api/v1/forecast/hybrid/runs", {"horizon_weeks": 8}),
        ("/api/v1/decisions/refresh", None),
    ],
)
async def test_forecasting_paths_refuse_duplicated_history(
    client, app_role_db, signed_in_workspace, path, body
):
    tenant, headers = await signed_in_workspace()
    await _import_and_duplicate(app_role_db, tenant)

    r = await client.post(path, headers=headers, json=body)

    assert r.status_code == 409, r.text
    assert "2 duplicate sales rows" in r.json()["detail"]
    assert "Data Quality" in r.json()["detail"]


async def test_gate_lifts_once_duplicates_are_removed(client, app_role_db, signed_in_workspace):
    tenant, headers = await signed_in_workspace()
    await _import_and_duplicate(app_role_db, tenant)
    fix = await client.post(
        "/api/v1/data-quality/fix", headers=headers, json={"action": "dedupe_sales", "confirm": True}
    )
    assert fix.json()["rows_affected"] == 2

    r = await client.post("/api/v1/forecasts/generate", headers=headers, json={"horizon": 8})

    assert r.status_code == 503  # past the gate; the (unreachable) ML service is next


async def test_clean_history_is_not_gated(client, app_role_db, signed_in_workspace):
    tenant, headers = await signed_in_workspace()
    headers_csv, records = fi.parse_table("s.csv", b"sku,date,quantity\nKURTI-M,2026-08-24,3")
    await fi.import_rows(
        db=app_role_db, tenant_id=tenant, industry=IndustryCode.fashion, kind="sales",
        headers=headers_csv, records=records,
    )

    r = await client.post("/api/v1/decisions/refresh", headers=headers)

    assert r.status_code == 200, r.text
