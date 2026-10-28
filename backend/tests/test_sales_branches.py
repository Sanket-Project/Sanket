"""Branch comparisons use explicit sale locations and preserve tenant boundaries."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.models.enums import IndustryCode
from app.models.sales import HistoricalSale
from tests.test_sales_currency import _sku


async def test_branches_group_locations_and_separate_currencies(client, db_session, signed_in_workspace):
    tenant, headers = await signed_in_workspace()
    other, _ = await signed_in_workspace()
    inr = await _sku(db_session, tenant, "BR-INR", "INR")
    usd = await _sku(db_session, tenant, "BR-USD", "USD")
    foreign = await _sku(db_session, other, "PRIVATE", "INR")
    now = datetime.now(UTC) - timedelta(minutes=5)
    for tid, sku, location, units, amount, when in [
        (tenant, inr, " North ", 2, 1000, now),
        (tenant, inr, "North", 1, 500, now),
        (tenant, usd, "North", 1, 50, now),
        (tenant, inr, "South", 3, 700, now),
        (tenant, inr, None, 1, 100, now),
        (tenant, inr, "  ", 1, 100, now),
        (tenant, inr, "Old", 1, 100, now - timedelta(days=400)),
        (other, foreign, "Private branch", 99, 99999, now),
    ]:
        db_session.add(HistoricalSale(tenant_id=tid, sku_id=sku, industry=IndustryCode.fashion,
            sale_time=when, channel="pos", location=location, units_sold=units,
            gross_revenue=Decimal(amount), net_revenue=Decimal(amount), returns=0))
    await db_session.commit()
    response = await client.get("/api/v1/analytics/sales/branches?lookback_days=30", headers=headers)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["unassigned_records"] == 2
    branches = {row["name"]: row for row in data["branches"]}
    assert set(branches) == {"North", "South"}
    assert branches["North"]["units_sold"] == 4
    assert branches["North"]["gross_revenue"] is None
    assert branches["North"]["revenue_by_currency"] == {"INR": 1500.0, "USD": 50.0}
    assert branches["South"]["gross_revenue"] == 700


async def test_no_named_locations_returns_no_branches(client, db_session, signed_in_workspace):
    tenant, headers = await signed_in_workspace()
    sku = await _sku(db_session, tenant, "NO-BRANCH", "INR")
    db_session.add(HistoricalSale(tenant_id=tenant, sku_id=sku, industry=IndustryCode.fashion,
        sale_time=datetime.now(UTC), channel="pos", region="Mumbai", units_sold=1, returns=0))
    await db_session.commit()
    response = await client.get("/api/v1/analytics/sales/branches", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["branches"] == []
    assert response.json()["unassigned_records"] == 1


async def test_branch_missing_amount_is_not_zero_but_explicit_zero_keeps_currency(client, db_session, signed_in_workspace):
    tenant, headers = await signed_in_workspace()
    sku = await _sku(db_session, tenant, "MISSING-AMOUNT", "INR")
    usd = await _sku(db_session, tenant, "PARTIAL-AMOUNT", "USD")
    for location, amount in [("Missing", None), ("Zero", Decimal(0)), ("Partial", None)]:
        db_session.add(HistoricalSale(tenant_id=tenant, sku_id=sku, industry=IndustryCode.fashion,
            sale_time=datetime.now(UTC), channel="pos", location=location, units_sold=1,
            gross_revenue=amount, net_revenue=amount, returns=0))
    db_session.add(HistoricalSale(tenant_id=tenant, sku_id=usd, industry=IndustryCode.fashion,
        sale_time=datetime.now(UTC), channel="pos", location="Partial", units_sold=1,
        gross_revenue=Decimal(10), net_revenue=Decimal(10), returns=0))
    await db_session.commit()
    data = (await client.get("/api/v1/analytics/sales/branches", headers=headers)).json()
    branches = {row["name"]: row for row in data["branches"]}
    assert branches["Missing"]["gross_revenue"] is None
    assert branches["Missing"]["revenue_by_currency"] == {}
    assert branches["Zero"]["gross_revenue"] == 0
    assert branches["Zero"]["currency"] == "INR"
    assert branches["Partial"]["gross_revenue"] is None
    assert branches["Partial"]["revenue_by_currency"] == {}
