"""Company trends use uploaded catalogue/sales, never industry stand-ins."""

from __future__ import annotations

import json
import uuid

from sqlalchemy import text


async def _catalogue(db, tenant, name="Cotton shirts", category="Shirts", code="SHIRT-M"):
    product, sku = uuid.uuid4(), uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO products (id,tenant_id,industry,name,category,status) "
            "VALUES (:p,:t,'fashion',:n,:c,'active')"
        ),
        {"p": product, "t": tenant, "n": name, "c": category},
    )
    await db.execute(
        text(
            "INSERT INTO skus (id,tenant_id,product_id,industry,sku_code) "
            "VALUES (:s,:t,:p,'fashion',:c)"
        ),
        {"s": sku, "p": product, "t": tenant, "c": code},
    )
    return product, sku


async def _sale(db, tenant, sku, date, units, location="shop"):
    await db.execute(
        text(
            "INSERT INTO historical_sales (tenant_id,sku_id,industry,sale_time,"
            "channel,units_sold,location) VALUES (:t,:s,'fashion',:d,'store',:u,:l)"
        ),
        {"t": tenant, "s": sku, "d": date, "u": units, "l": location},
    )


async def _signal(db, term, tenant=None, source="google_trends", **payload):
    await db.execute(
        text(
            "INSERT INTO trend_signals (id,tenant_id,industry,source,kind,series_key,"
            "category_tags,sku_tags,raw_value,normalized_score,confidence,captured_at,payload) "
            "VALUES (:id,:t,'fashion',CAST(:source AS trend_signal_source),'search_interest',:key,'{}','{}',"
            "72,0.44,0.8,now(),CAST(:payload AS jsonb))"
        ),
        {
            "id": uuid.uuid4(),
            "t": tenant,
            "source": source,
            "key": f"test:{uuid.uuid4()}:{term}",
            "payload": json.dumps({"product": term, "relative_search_interest": 72, **payload}),
        },
    )


async def test_empty_company_has_no_industry_product_or_signal_standins(
    client, signed_in_workspace, db_session
):
    _, headers = await signed_in_workspace()
    await _signal(db_session, "sneakers")
    await db_session.commit()
    response = await client.get("/api/v1/trends/company", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["catalogue"] == {"product_count": 0, "sku_count": 0}
    assert body["sales"]["status"] == "no_history"
    assert body["sales"]["current_units"] is None
    assert body["external"]["items"] == []


async def test_uploaded_sales_compare_equal_periods_and_ignore_other_tenants(
    client, signed_in_workspace, db_session
):
    from datetime import UTC, datetime

    tenant, headers = await signed_in_workspace()
    other, _ = await signed_in_workspace()
    product, sku = await _catalogue(db_session, tenant)
    _, alien_sku = await _catalogue(db_session, other, name="Alien", code="ALIEN")
    await _sale(db_session, tenant, sku, datetime(2026, 10, 26, tzinfo=UTC), 12)
    await _sale(db_session, tenant, sku, datetime(2026, 9, 30, tzinfo=UTC), 8)
    await _sale(db_session, tenant, sku, datetime(2026, 9, 10, tzinfo=UTC), 10)
    await _sale(db_session, other, alien_sku, datetime(2026, 10, 26, tzinfo=UTC), 999)
    await db_session.commit()
    r = await client.get(f"/api/v1/trends/company?product_id={product}&days=28", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["catalogue"] == {"product_count": 1, "sku_count": 1}
    assert body["period"]["end"] == "2026-10-26"
    assert body["sales"]["current_units"] == 20
    assert body["sales"]["previous_units"] == 10
    assert body["sales"]["change_pct"] == 100
    assert body["sales"]["leaders"][0]["sku_code"] == "SHIRT-M"
    assert sum(row["units"] for row in body["sales"]["series"]) == 20
    forbidden = await client.get(f"/api/v1/trends/company?sku_id={alien_sku}", headers=headers)
    assert forbidden.json()["sales"]["status"] == "no_history"


async def test_catalogue_options_search_and_paginate_without_cross_tenant_leaks(
    client, signed_in_workspace, db_session
):
    tenant, headers = await signed_in_workspace()
    other, _ = await signed_in_workspace()
    products = []
    for idx in range(4):
        product, _ = await _catalogue(db_session, tenant, name=f"Shirt {idx}", code=f"SHIRT-{idx}")
        products.append(product)
    await _catalogue(db_session, other, name="Shirt hidden", code="SHIRT-HIDDEN")
    await db_session.commit()
    r = await client.get(
        "/api/v1/trends/company/catalogue?kind=sku&q=SHIRT&limit=2&offset=2", headers=headers
    )
    assert r.status_code == 200, r.text
    assert r.json()["total"] == 4
    assert [x["sku_code"] for x in r.json()["items"]] == ["SHIRT-2", "SHIRT-3"]
    assert all(x["kind"] == "sku" for x in r.json()["items"])
    r = await client.get(
        f"/api/v1/trends/company/catalogue?kind=sku&product_id={products[0]}", headers=headers
    )
    assert r.json()["total"] == 1
    assert r.json()["items"][0]["sku_code"] == "SHIRT-0"


async def test_external_matches_actual_catalogue_without_making_up_district_scores(
    client, signed_in_workspace, db_session
):
    tenant, headers = await signed_in_workspace()
    other, _ = await signed_in_workspace()
    await _catalogue(db_session, tenant)
    await _signal(db_session, "cotton shirts", state="Telangana", city="Hyderabad")
    await _signal(db_session, "gaming laptops")
    await _signal(
        db_session, "cotton shirts", source="synthetic", state="Telangana", city="Hyderabad"
    )
    await _signal(db_session, "cotton shirts", synthetic=True, state="Telangana", city="Hyderabad")
    await _signal(db_session, "cotton shirts", tenant=other, state="Telangana")
    await db_session.commit()
    r = await client.get("/api/v1/trends/company?state=Telangana", headers=headers)
    items = r.json()["external"]["items"]
    assert len(items) == 1
    assert items[0]["matched_products"] == ["Cotton shirts"]
    assert items[0]["relative_interest"] == 72
    assert items[0]["geography_level"] == "city"
    assert items[0]["district"] is None
    r = await client.get(
        "/api/v1/trends/company?state=Telangana&district=Hyderabad", headers=headers
    )
    assert r.json()["external"]["items"] == []


async def test_geographic_sales_require_explicit_mapping_and_zero_prior_withholds_change(
    client, signed_in_workspace, db_session
):
    from datetime import UTC, datetime

    tenant, headers = await signed_in_workspace()
    _, sku = await _catalogue(db_session, tenant)
    await _sale(db_session, tenant, sku, datetime(2026, 10, 26, tzinfo=UTC), 7, " HyDeRaBaD ")
    await db_session.commit()
    r = await client.get(
        "/api/v1/trends/company?state=Telangana&district=Hyderabad", headers=headers
    )
    assert r.json()["sales"]["status"] == "unmapped_geography"
    await db_session.execute(
        text(
            "INSERT INTO locations (id,tenant_id,code,name,attributes) "
            "VALUES (:id,:t,'hyderabad','Hyderabad',CAST(:a AS jsonb))"
        ),
        {
            "id": uuid.uuid4(),
            "t": tenant,
            "a": json.dumps({"state": "Telangana", "district": "Hyderabad"}),
        },
    )
    await db_session.commit()
    r = await client.get(
        "/api/v1/trends/company?state=Telangana&district=Hyderabad", headers=headers
    )
    assert r.json()["sales"]["current_units"] == 7
    assert r.json()["sales"]["change_pct"] is None


def test_regional_provider_state_label_cannot_become_a_tier_three_city():
    from app.services.external_signals.regional_demand_connector import region_metadata

    assert region_metadata("Telangana") == {
        "state": "Telangana",
        "city": None,
        "district": None,
        "geography_level": "state",
        "tier": None,
    }
    assert region_metadata("Hyderabad")["state"] == "Telangana"
    assert region_metadata("Unmapped place")["geography_level"] == "unknown"
    assert region_metadata("Unmapped place")["tier"] is None


async def test_catalogue_collection_dedupes_bounds_and_persists_private_results(
    client,
    signed_in_workspace,
    db_session,
    monkeypatch,
    app_role_db,
):
    from datetime import UTC, datetime

    from app.services.company_trends import refresh_company_interest
    from app.services.external_signals.base import SignalSample
    from app.services.external_signals.regional_demand_connector import RegionalDemandConnector

    tenant, _ = await signed_in_workspace()
    for idx in range(12):
        await _catalogue(db_session, tenant, name=f"Shirt {idx}", code=f"SHIRT-{idx}")
    await _catalogue(db_session, tenant, name="Cotton tunic", category="", code="TUNIC")
    await db_session.commit()
    calls = []

    def fetch(_self, industry, keywords):
        calls.append(keywords)
        assert all(isinstance(category, str) and category for _, category in keywords)
        return [
            SignalSample(
                source="google_trends",
                kind="search_interest",
                series_key="test:private",
                industry=industry,
                captured_at=datetime.now(UTC),
                raw_value=75,
                normalized_score=0.5,
                payload={
                    "product": keywords[0][0],
                    "state": "Telangana",
                    "relative_search_interest": 75,
                },
            )
        ]

    monkeypatch.setattr(RegionalDemandConnector, "_fetch_distribution", fetch)
    db = app_role_db
    result = await refresh_company_interest(db, tenant, "fashion")
    assert result["status"] == "completed"
    assert len(calls) == 1
    assert 0 < len(calls[0]) <= 8
    assert len({term for term, _ in calls[0]}) == len(calls[0])
    rows = (
        await db_session.execute(
            text(
                "SELECT tenant_id,payload FROM trend_signals "
                "WHERE tenant_id=:t AND series_key='test:private'"
            ),
            {"t": tenant},
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].tenant_id == tenant
    assert rows[0].payload["catalogue_collection"] is True
    assert (await refresh_company_interest(db, tenant, "fashion"))["status"] == "fresh"
    assert len(calls) == 1
    async with db.session(str(tenant)) as locked:
        await locked.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
            {"key": f"company-interest:{tenant}:fashion"},
        )
        assert (await refresh_company_interest(db, tenant, "fashion"))["status"] == "running"
    assert len(calls) == 1


async def test_company_refresh_queues_only_this_workspace(client, signed_in_workspace):
    from unittest.mock import AsyncMock

    tenant, headers = await signed_in_workspace()
    app = client._transport.app
    original = app.state.arq
    queue = AsyncMock()
    app.state.arq = queue
    try:
        response = await client.post("/api/v1/trends/company/refresh", headers=headers)
        assert response.status_code == 202, response.text
        assert response.json()["status"] == "queued"
        args, kwargs = queue.enqueue_job.call_args
        assert args == ("run_company_trends", str(tenant), "fashion")
        assert str(tenant) in kwargs["_job_id"]
        queue.enqueue_job.return_value = None
        response = await client.post("/api/v1/trends/company/refresh", headers=headers)
        assert response.json()["status"] == "skipped"
        queue.enqueue_job.side_effect = ConnectionError("offline")
        response = await client.post("/api/v1/trends/company/refresh", headers=headers)
        assert response.status_code == 503
        app.state.arq = None
        response = await client.post("/api/v1/trends/company/refresh", headers=headers)
        assert response.json() == {"status": "queued", "execution": "local_background"}
    finally:
        app.state.arq = original
