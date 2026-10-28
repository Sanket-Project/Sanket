"""Gross sales exclude return-only events, but keep sales with aggregate returns."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.models.enums import IndustryCode
from app.models.sales import HistoricalSale
from tests.test_sales_currency import _sku


@pytest.mark.parametrize("endpoint", ["summary", "timeseries", "top-products?period=year", "branches"])
async def test_before_returns_across_analytics(client, db_session, signed_in_workspace, endpoint):
    tenant, headers = await signed_in_workspace()
    sku = await _sku(db_session, tenant, "RETURN-TEST", "INR")
    # Legacy uploads encode standalone returns as zero sales units, returned units,
    # and a negative amount. Aggregate rows can contain both sales and returns.
    for units, returned, gross, net, metadata in [
        (10, 2, "1000", "800", {}),
        (0, 1, "-100", "-100", {}),
        (0, 1, "0", "-100", {"event_kind": "return"}),
    ]:
        db_session.add(HistoricalSale(tenant_id=tenant, sku_id=sku, industry=IndustryCode.fashion,
            sale_time=datetime.now(UTC) - timedelta(minutes=1), channel="pos", location="warehouse-a",
            units_sold=units, returns=returned, gross_revenue=Decimal(gross),
            net_revenue=Decimal(net), metadata_=metadata))
    await db_session.commit()
    response = await client.get(f"/api/v1/analytics/sales/{endpoint}", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    row = (data["year"] if endpoint == "summary" else
           next(r for r in data["series"] if r["units_sold"]) if endpoint == "timeseries" else
           data["products"][0] if endpoint.startswith("top-products") else data["branches"][0])
    assert row["gross_revenue"] == 1000
    assert row["units_sold"] == 10
    if endpoint in {"summary", "timeseries"}:
        assert row["net_revenue"] == 600
    if endpoint == "summary":
        assert row["transactions"] == 1
        assert row["returns"] == 4
