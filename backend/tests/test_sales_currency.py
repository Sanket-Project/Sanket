"""Revenue carries its currency; different currencies are never added together (F03).

The INR sales screen showed 83x the API total because nothing said the API's
numbers were already rupees. Every revenue figure now names its currency, and a
workspace selling in more than one gets per-currency totals instead of a sum.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import text

from app.models.enums import IndustryCode
from app.services.integrations import file_import as fi


async def _sku(db, tenant, code, currency):
    pid, sid = uuid.uuid4(), uuid.uuid4()
    await db.execute(
        text("INSERT INTO products (id, tenant_id, industry, name, category, status) "
             "VALUES (:p, :t, 'fashion', :n, 'Kurtis', 'active')"),
        {"p": str(pid), "t": str(tenant), "n": f"{code} product"},
    )
    await db.execute(
        text("INSERT INTO skus (id, tenant_id, product_id, industry, sku_code, currency) "
             "VALUES (:s, :t, :p, 'fashion', :c, :cur)"),
        {"s": str(sid), "t": str(tenant), "p": str(pid), "c": code, "cur": currency},
    )
    return sid


async def _sale(db, tenant, sku, units, gross):
    await db.execute(
        text("INSERT INTO historical_sales (tenant_id, sku_id, industry, sale_time, channel, "
             "units_sold, gross_revenue, net_revenue) VALUES (:t, :s, 'fashion', :w, 'pos', :u, :g, :g)"),
        {"t": str(tenant), "s": str(sku), "u": units, "g": Decimal(gross),
         "w": datetime.now(UTC) - timedelta(minutes=5)},
    )


async def test_single_currency_totals_are_returned_as_that_currency(client, db_session, signed_in_workspace):
    tenant, headers = await signed_in_workspace()
    sku = await _sku(db_session, tenant, "KURTI-M", "INR")
    await _sale(db_session, tenant, sku, 3, "13091162")
    await db_session.commit()

    summary = (await client.get("/api/v1/analytics/sales/summary", headers=headers)).json()
    top = (await client.get("/api/v1/analytics/sales/top-products?period=year", headers=headers)).json()

    assert summary["currency"] == "INR"
    assert summary["year"]["currency"] == "INR"
    assert summary["year"]["gross_revenue"] == 13091162.0
    assert top["products"][0]["currency"] == "INR"
    assert top["products"][0]["gross_revenue"] == 13091162.0


async def test_mixed_currencies_are_reported_per_currency_never_summed(client, db_session, signed_in_workspace):
    tenant, headers = await signed_in_workspace()
    inr = await _sku(db_session, tenant, "KURTI-M", "INR")
    usd = await _sku(db_session, tenant, "EXPORT-1", "USD")
    await _sale(db_session, tenant, inr, 2, "1000")
    await _sale(db_session, tenant, usd, 1, "50")
    await db_session.commit()

    summary = (await client.get("/api/v1/analytics/sales/summary", headers=headers)).json()
    series = (await client.get("/api/v1/analytics/sales/timeseries?lookback_days=2", headers=headers)).json()

    assert summary["currency"] is None
    assert summary["currencies"] == ["INR", "USD"]
    assert summary["year"]["gross_revenue"] is None
    assert summary["year"]["revenue_by_currency"] == {"INR": 1000.0, "USD": 50.0}
    assert summary["year"]["units_sold"] == 3  # units add up; money does not
    assert summary["year"]["revenue_delta"] is None
    today = series["series"][-1]
    assert series["currency"] is None
    assert today["gross_revenue"] is None
    assert today["revenue_by_currency"] == {"INR": 1000.0, "USD": 50.0}


async def _import(db, tenant, body, **kw):
    headers, records = fi.parse_table("s.csv", body.strip().encode())
    return await fi.import_rows(db=db, tenant_id=tenant, industry=IndustryCode.fashion,
                                kind="sales", headers=headers, records=records, **kw)


async def _currency_of(db, tenant, code):
    async with db.session(str(tenant)) as s:
        return await s.scalar(text("SELECT currency FROM skus WHERE sku_code = :c"), {"c": code})


async def test_upload_currency_is_applied_to_new_skus(app_role_db, make_tenant):
    tenant = await make_tenant()
    stats = await _import(app_role_db, tenant, "sku,date,quantity,price\nNEW-1,2026-08-24,2,500",
                          currency="INR")
    assert stats["warnings"] == []
    assert await _currency_of(app_role_db, tenant, "NEW-1") == "INR"


async def test_workspace_currency_is_the_default(app_role_db, db_session, make_tenant):
    tenant = await make_tenant()
    await db_session.execute(
        text("UPDATE tenants SET settings = jsonb_set(settings, '{currency}', '\"INR\"') WHERE id = :t"),
        {"t": str(tenant)},
    )
    await db_session.commit()
    await _import(app_role_db, tenant, "sku,date,quantity,price\nNEW-2,2026-08-24,2,500")
    assert await _currency_of(app_role_db, tenant, "NEW-2") == "INR"


async def test_unspecified_currency_is_flagged_not_silently_assumed(app_role_db, make_tenant):
    tenant = await make_tenant()
    stats = await _import(app_role_db, tenant, "sku,date,quantity,price\nNEW-3,2026-08-24,2,500")
    assert any("currency" in w for w in stats["warnings"])


async def test_a_row_in_another_currency_than_its_sku_is_rejected(app_role_db, make_tenant):
    tenant = await make_tenant()
    await _import(app_role_db, tenant, "sku,date,quantity,price\nNEW-4,2026-08-24,2,500", currency="INR")
    stats = await _import(
        app_role_db, tenant, "sku,date,quantity,price,currency\nNEW-4,2026-08-31,1,9,USD"
    )
    assert stats["rows_inserted"] == 0
    assert any("USD" in e and "INR" in e for e in stats["errors"])


async def test_explicit_upload_currency_must_match_an_existing_sku(app_role_db, make_tenant):
    tenant = await make_tenant()
    await _import(app_role_db, tenant, "sku,date,quantity,price\nEXISTING-USD,2026-08-24,2,9", currency="USD")
    stats = await _import(
        app_role_db, tenant, "sku,date,quantity,price\nEXISTING-USD,2026-08-31,1,500", currency="INR"
    )
    assert stats["rows_inserted"] == 0
    assert stats["rows_skipped"] == 1
    assert any("USD" in e and "INR" in e for e in stats["errors"])
    assert await _currency_of(app_role_db, tenant, "EXISTING-USD") == "USD"


async def test_workspace_default_does_not_redeclare_existing_sku_currency(app_role_db, db_session, make_tenant):
    tenant = await make_tenant()
    await _import(app_role_db, tenant, "sku,date,quantity,price\nEXISTING-USD,2026-08-24,2,9", currency="USD")
    await db_session.execute(
        text("UPDATE tenants SET settings = jsonb_set(settings, '{currency}', '\"INR\"') WHERE id = :t"),
        {"t": str(tenant)},
    )
    await db_session.commit()
    stats = await _import(app_role_db, tenant, "sku,date,quantity,price\nEXISTING-USD,2026-08-31,1,9")
    assert stats["rows_inserted"] == 1
    assert stats["errors"] == []
    assert await _currency_of(app_role_db, tenant, "EXISTING-USD") == "USD"


async def test_sku_created_without_a_currency_takes_the_workspace_currency(
    client, db_session, signed_in_workspace
):
    tenant, headers = await signed_in_workspace()
    await db_session.execute(
        text("UPDATE tenants SET settings = jsonb_set(settings, '{currency}', '\"INR\"') WHERE id = :t"),
        {"t": str(tenant)},
    )
    await db_session.commit()
    product = await client.post(
        "/api/v1/products", headers=headers, json={"name": "Kurti (synthetic)", "category": "Kurtis"}
    )

    created = await client.post(
        f"/api/v1/skus/{product.json()['id']}/skus", headers=headers, json={"sku_code": "K-INR"}
    )
    explicit = await client.post(
        f"/api/v1/skus/{product.json()['id']}/skus", headers=headers,
        json={"sku_code": "K-USD", "currency": "USD"},
    )

    assert created.status_code == 201, created.text
    assert created.json()["currency"] == "INR"
    assert explicit.json()["currency"] == "USD"
