"""V2 financial recognition, allocation, replay and projection regressions."""

import csv
import io
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

SAMPLES = Path(__file__).resolve().parents[2] / "docs/audit/2026-10-28-retail-v2/samples"


@pytest.fixture(autouse=True)
def application_role(client, app_role_db, monkeypatch):
    """All HTTP financial reads/writes use the real RLS application role."""
    monkeypatch.setattr(client._transport.app.state, "db", app_role_db)


async def seed_catalog(db, tenant):
    product = await db.scalar(
        text(
            "INSERT INTO products (id,tenant_id,industry,external_id,name,category,status,attributes) VALUES (gen_random_uuid(),:t,'fashion','DEMO-KUR-001','Demo Kurti','apparel','active','{}'::jsonb) RETURNING id"
        ),
        {"t": tenant},
    )
    await db.execute(
        text(
            "INSERT INTO skus (id,tenant_id,product_id,industry,sku_code,currency,attributes) VALUES (gen_random_uuid(),:t,:p,'fashion','DEMO-KUR-001-BLU-M','INR','{}'::jsonb)"
        ),
        {"t": tenant, "p": product},
    )
    await db.execute(
        text(
            "INSERT INTO locations (id,tenant_id,code,name,kind,is_active,attributes) VALUES (gen_random_uuid(),:t,'demo-hyd-store','Demo','store',true,'{}'::jsonb)"
        ),
        {"t": tenant},
    )
    await db.commit()


def content(kind, **changes):
    if not changes:
        return (SAMPLES / f"{kind}_v2_SAMPLE_ONLY.csv").read_bytes()
    reader = csv.DictReader(io.StringIO((SAMPLES / f"{kind}_v2_SAMPLE_ONLY.csv").read_text()))
    rows = list(reader)
    rows[0].update(changes)
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=reader.fieldnames)
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode()


async def post(client, headers, data):
    preview = await client.post(
        "/api/v1/integrations/v2/preview",
        headers=headers,
        files={"file": ("review.csv", data, "text/csv")},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["can_confirm"], preview.text
    result = await client.post(
        "/api/v1/integrations/v2/confirm",
        headers=headers,
        data={"preview_token": preview.json()["preview_token"]},
        files={"file": ("review.csv", data, "text/csv")},
    )
    assert result.status_code == 200, result.text
    return result.json()


@pytest.mark.asyncio
async def test_seeded_sale_projects_and_replay_does_not_duplicate(
    client, signed_in_workspace, db_session
):
    tenant, headers = await signed_in_workspace("fashion")
    await seed_catalog(db_session, tenant)
    first = await post(client, headers, content("sales"))
    assert first["inserted"] == 1
    second = await post(client, headers, content("sales"))
    assert second["skipped"] == 1
    count = await db_session.scalar(
        text("SELECT count(*) FROM historical_sales WHERE tenant_id=:t"), {"t": tenant}
    )
    assert count == 1


@pytest.mark.asyncio
async def test_return_does_not_restate_the_previous_days_sale(
    client, signed_in_workspace, db_session
):
    tenant, headers = await signed_in_workspace("fashion")
    await seed_catalog(db_session, tenant)
    await post(client, headers, content("sales"))
    await post(client, headers, content("returns"))
    original = await db_session.scalar(
        text(
            "SELECT sum(net_revenue) FROM historical_sales WHERE tenant_id=:t AND sale_time::date='2026-10-02'"
        ),
        {"t": tenant},
    )
    assert original == Decimal("1800.00"), "Oct 3 return retroactively reduced the Oct 2 sale"


@pytest.mark.asyncio
async def test_distinct_external_identities_do_not_collide_in_projection(
    client, signed_in_workspace, db_session
):
    tenant, headers = await signed_in_workspace("fashion")
    await seed_catalog(db_session, tenant)
    await post(client, headers, content("sales", source_system="REVIEW:A", transaction_id="B"))
    await post(client, headers, content("sales", source_system="REVIEW", transaction_id="A:B"))
    count = await db_session.scalar(
        text("SELECT count(*) FROM historical_sales WHERE tenant_id=:t"), {"t": tenant}
    )
    assert count == 2, (
        "Distinct source/transaction tuples collided in the colon-concatenated projection key"
    )


@pytest.mark.asyncio
async def test_partial_quantity_return_cannot_claim_almost_all_sale_value(
    client, signed_in_workspace, db_session
):
    tenant, headers = await signed_in_workspace("fashion")
    await seed_catalog(db_session, tenant)
    await post(client, headers, content("sales"))
    data = content(
        "returns", return_value_ex_tax="1700.00", tax_amount="85.00", refund_amount="1785.00"
    )
    preview = await client.post(
        "/api/v1/integrations/v2/preview",
        headers=headers,
        files={"file": ("review.csv", data, "text/csv")},
    )
    result = await client.post(
        "/api/v1/integrations/v2/confirm",
        headers=headers,
        data={"preview_token": preview.json()["preview_token"]},
        files={"file": ("review.csv", data, "text/csv")},
    )
    assert result.status_code == 400, (
        "One of two equally priced units was allowed to claim 1700 of 1800 net value"
    )
    assert (
        await db_session.scalar(
            text("SELECT count(*) FROM v2_return_events WHERE tenant_id=:t"), {"t": tenant}
        )
        == 0
    )
    assert (
        await db_session.scalar(
            text(
                "SELECT count(*) FROM event_identity_registry WHERE tenant_id=:t AND entity_kind='return'"
            ),
            {"t": tenant},
        )
        == 0
    )


async def test_credit_date_projection_and_replays(client, signed_in_workspace, db_session, monkeypatch):
    class ReportingDate(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 28, 12, tzinfo=UTC).astimezone(tz)

    monkeypatch.setattr("app.routers.sales_analytics.datetime", ReportingDate)
    tenant, headers = await signed_in_workspace("fashion")
    await seed_catalog(db_session, tenant)
    sale = content("sales", transaction_at="2026-09-30T12:00:00+05:30")
    await post(client, headers, sale)
    await post(client, headers, content("returns", status="draft"))
    assert (
        await db_session.scalar(
            text("SELECT count(*) FROM historical_sales WHERE tenant_id=:t"), {"t": tenant}
        )
        == 1
    )
    await post(client, headers, content("returns"))
    assert (await post(client, headers, content("returns")))["skipped"] == 1
    assert (await post(client, headers, sale))["skipped"] == 1
    rows = (
        (
            await db_session.execute(
                text("""
        SELECT sale_time::date AS day, sum(units_sold) AS units, sum(returns) AS returns,
               sum(gross_revenue) AS gross, sum(net_revenue) AS net
        FROM historical_sales WHERE tenant_id=:t GROUP BY 1 ORDER BY 1
    """),
                {"t": tenant},
            )
        )
        .mappings()
        .all()
    )
    assert [(str(r["day"]), r["units"], r["returns"], r["gross"], r["net"]) for r in rows] == [
        ("2026-09-30", 2, 0, Decimal("2000"), Decimal("1800")),
        ("2026-10-03", 0, 1, Decimal("0"), Decimal("-900")),
    ]
    series = await client.get(
        "/api/v1/analytics/sales/timeseries",
        headers=headers,
        params={"lookback_days": 730, "granularity": "day"},
    )
    assert series.status_code == 200, series.text
    days = {r["bucket"]: r for r in series.json()["series"]}
    assert days["2026-09-30"]["net_revenue"] == 1800
    assert days["2026-10-03"]["net_revenue"] == -900
    summary = await client.get("/api/v1/analytics/sales/summary", headers=headers)
    assert summary.status_code == 200, summary.text
    assert summary.json()["month"]["transactions"] == 0
    assert summary.json()["month"]["units_sold"] == 0
    assert summary.json()["month"]["returns"] == 1
    assert summary.json()["month"]["net_revenue"] == -900
    assert summary.json()["year"]["transactions"] == 1
    assert summary.json()["year"]["net_revenue"] == 900


@pytest.mark.parametrize("draft_first", [False, True])
async def test_concurrent_confirmations_project_once(
    client, signed_in_workspace, db_session, draft_first
):
    import asyncio

    tenant, headers = await signed_in_workspace("fashion")
    await seed_catalog(db_session, tenant)
    sales = await asyncio.gather(*[post(client, headers, content("sales")) for _ in range(2)])
    assert sum(r["inserted"] for r in sales) == 1
    if draft_first:
        await post(client, headers, content("returns", status="draft"))
    posted_returns = await asyncio.gather(*[post(client, headers, content("returns")) for _ in range(2)])
    assert sum(r["inserted"] for r in posted_returns) == 1
    assert (
        await db_session.scalar(
            text("SELECT count(*) FROM historical_sales WHERE tenant_id=:t"), {"t": tenant}
        )
        == 2
    )
    assert (
        await db_session.scalar(
            text("SELECT cumulative_returned_qty FROM v2_sales_events WHERE tenant_id=:t"),
            {"t": tenant},
        )
        == 1
    )


async def test_populated_projection_migration_repairs_collisions_and_preserves_v1(
    client, signed_in_workspace, db_session
):
    import importlib

    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    tenant, headers = await signed_in_workspace("fashion")
    await seed_catalog(db_session, tenant)
    await post(client, headers, content("sales", source_system="OLD:A", transaction_id="B"))
    await post(client, headers, content("sales", source_system="OLD", transaction_id="A:B"))
    await post(
        client,
        headers,
        content("returns", original_source_system="OLD:A", original_transaction_id="B"),
    )
    # Recreate the old faulty projection: one collided sale with the return
    # deducted from its original day; no separate credit, plus an unrelated V1 row.
    await db_session.execute(text("DELETE FROM historical_sales WHERE tenant_id=:t"), {"t": tenant})
    await db_session.execute(
        text("""
        INSERT INTO historical_sales (tenant_id, sku_id, industry, sale_time, units_sold,
                                      gross_revenue, net_revenue, returns, record_key, metadata)
        SELECT :t, s.id, 'fashion', '2026-10-02'::timestamptz, 2, 2000, 900, 1,
               'v2:OLD:A:B:LINE-1', jsonb_build_object('source','retail_v2','event_id',e.id::text)
        FROM v2_sales_events e JOIN skus s ON s.tenant_id=e.tenant_id AND s.sku_code=e.sku_code
        WHERE e.tenant_id=:t AND e.source_system='OLD:A'
    """),
        {"t": tenant},
    )
    await db_session.execute(
        text("""
        INSERT INTO historical_sales (tenant_id, sku_id, industry, sale_time, units_sold,
                                      gross_revenue, net_revenue, returns, record_key, metadata)
        SELECT :t, id, 'fashion', '2026-10-01'::timestamptz, 1, 123, 123, 0, 'v1:untouched', '{}'
        FROM skus WHERE tenant_id=:t
    """),
        {"t": tenant},
    )
    await db_session.commit()
    spec = importlib.util.spec_from_file_location(
        "projection_migration",
        Path(__file__).resolve().parents[1]
        / "alembic/versions/0038_retail_v2_dated_projections.py",
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    connection = await db_session.connection()

    def upgrade(sync_connection):
        with Operations.context(MigrationContext.configure(sync_connection)):
            migration.upgrade()

    await connection.run_sync(upgrade)
    await db_session.commit()
    rows = (
        await db_session.execute(
            text("""
        SELECT record_key, units_sold, net_revenue, returns FROM historical_sales
        WHERE tenant_id=:t ORDER BY record_key
    """),
            {"t": tenant},
        )
    ).all()
    assert len(rows) == 4
    assert sum(r.net_revenue for r in rows) == Decimal("2823")
    assert sum(r.returns for r in rows) == 1
    assert [r.net_revenue for r in rows if r.record_key == "v1:untouched"] == [Decimal("123")]
    days = (
        await db_session.execute(
            text("""
        SELECT sale_time::date AS day, sum(net_revenue) AS net FROM historical_sales
        WHERE tenant_id=:t GROUP BY 1 ORDER BY 1
    """),
            {"t": tenant},
        )
    ).all()
    assert [(str(r.day), r.net) for r in days] == [
        ("2026-10-01", Decimal("123")),
        ("2026-10-02", Decimal("3600")),
        ("2026-10-03", Decimal("-900")),
    ]
    await db_session.commit()
    await post(client, headers, content("sales", source_system="OLD:A", transaction_id="B"))
    await post(
        client,
        headers,
        content("returns", original_source_system="OLD:A", original_transaction_id="B"),
    )
    assert (
        await db_session.scalar(
            text("SELECT count(*) FROM historical_sales WHERE tenant_id=:t"), {"t": tenant}
        )
        == 4
    )
