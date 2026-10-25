"""Re-importing sales must never inflate demand (audit F01).

Runs the real importer against PostgreSQL as ``sanket_app`` (RLS enforced),
using the audit's labelled synthetic fashion file and small hand-written CSVs.
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

from app.models.enums import IndustryCode
from app.services.integrations import file_import as fi

AUDIT_CSV = (
    Path(__file__).resolve().parents[2]
    / "docs/audit/2026-10-25-fashion-readiness/synthetic-training-sales.csv"
)


def _csv(body: str) -> tuple[list[str], list[dict]]:
    return fi.parse_table("sales.csv", body.strip().encode())


async def _import(db, tenant, body_or_table, **kw):
    headers, records = _csv(body_or_table) if isinstance(body_or_table, str) else body_or_table
    return await fi.import_rows(
        db=db,
        tenant_id=tenant,
        industry=IndustryCode.fashion,
        kind="sales",
        headers=headers,
        records=records,
        **kw,
    )


async def _totals(db, tenant) -> dict:
    async with db.session(str(tenant)) as s:
        r = (
            await s.execute(
                text(
                    "SELECT count(*) AS n, coalesce(sum(units_sold), 0) AS units, "
                    "coalesce(sum(gross_revenue), 0) AS revenue FROM historical_sales"
                )
            )
        ).one()
    return {"rows": r.n, "units": int(r.units), "revenue": Decimal(r.revenue)}


async def test_replaying_the_audit_file_changes_nothing(app_role_db, make_tenant):
    tenant = await make_tenant()
    table = fi.parse_table(AUDIT_CSV.name, AUDIT_CSV.read_bytes())

    first = await _import(app_role_db, tenant, table)
    after_first = await _totals(app_role_db, tenant)
    second = await _import(app_role_db, tenant, table)
    after_second = await _totals(app_role_db, tenant)

    assert first["rows_inserted"] == after_first["rows"] > 0
    assert second["rows_inserted"] == 0
    assert second["rows_updated"] == 0
    assert second["rows_unchanged"] == first["rows_inserted"]
    assert after_second == after_first


async def test_identical_lines_inside_one_file_are_two_sales(app_role_db, make_tenant):
    tenant = await make_tenant()
    body = """
sku,date,quantity,price,channel
KURTI-M,2026-08-24,2,1200,Boduppal
KURTI-M,2026-08-24,2,1200,Boduppal
"""
    await _import(app_role_db, tenant, body)
    await _import(app_role_db, tenant, body)
    assert (await _totals(app_role_db, tenant))["rows"] == 2


async def test_distinct_orders_with_same_sku_time_and_qty_stay_distinct(app_role_db, make_tenant):
    tenant = await make_tenant()
    body = """
order_id,sku,date,quantity,price
A-1,KURTI-M,2026-08-24,2,1200
B-1,KURTI-M,2026-08-24,2,1200
"""
    stats = await _import(app_role_db, tenant, body)
    assert stats["rows_inserted"] == 2
    assert (await _totals(app_role_db, tenant))["units"] == 4


async def test_corrected_order_line_updates_in_place(app_role_db, make_tenant):
    tenant = await make_tenant()
    await _import(app_role_db, tenant, "order_id,sku,date,quantity,price\nA-1,KURTI-M,2026-08-24,5,100")
    stats = await _import(
        app_role_db, tenant, "order_id,sku,date,quantity,price\nA-1,KURTI-M,2026-08-24,7,100"
    )

    assert stats["rows_updated"] == 1
    assert stats["rows_inserted"] == 0
    async with app_role_db.session(str(tenant)) as s:
        rows = (await s.execute(text("SELECT units_sold, gross_revenue, metadata FROM historical_sales"))).all()
    assert len(rows) == 1
    assert rows[0].units_sold == 7
    assert rows[0].gross_revenue == Decimal("700")
    assert rows[0].metadata["revision"] == 2


async def test_period_mode_correction_replaces_the_value(app_role_db, make_tenant):
    tenant = await make_tenant()
    await _import(app_role_db, tenant, "sku,date,quantity\nKURTI-M,2026-08-24,10", identity="period")
    stats = await _import(app_role_db, tenant, "sku,date,quantity\nKURTI-M,2026-08-24,12", identity="period")

    assert stats["identity_mode"] == "period"
    assert stats["rows_updated"] == 1
    totals = await _totals(app_role_db, tenant)
    assert totals["rows"] == 1
    assert totals["units"] == 12


async def test_period_mode_rejects_two_rows_for_the_same_key(app_role_db, make_tenant):
    tenant = await make_tenant()
    stats = await _import(
        app_role_db,
        tenant,
        "sku,date,quantity\nKURTI-M,2026-08-24,10\nKURTI-M,2026-08-24,11\nKURTI-L,2026-08-24,3",
        identity="period",
    )
    assert stats["rows_inserted"] == 1
    assert stats["rows_skipped"] == 2
    assert any("duplicate period row" in e for e in stats["errors"])


async def test_concurrent_uploads_of_the_same_file_insert_once(app_role_db, make_tenant):
    tenant = await make_tenant()
    body = "\n".join(
        ["order_id,sku,date,quantity"]
        + [f"C-{i},KURTI-M,2026-08-{(i % 20) + 1:02d},{i + 1}" for i in range(60)]
    )
    await asyncio.gather(_import(app_role_db, tenant, body), _import(app_role_db, tenant, body))
    totals = await _totals(app_role_db, tenant)
    assert totals["rows"] == 60
    assert totals["units"] == sum(range(1, 61))


async def test_failed_upload_leaves_nothing_and_a_retry_is_clean(app_role_db, make_tenant, monkeypatch):
    tenant = await make_tenant()
    body = "\n".join(["sku,date,quantity"] + [f"KURTI-M,2026-08-{d:02d},1" for d in range(1, 21)])
    real_insert = fi._insert_sale
    calls = {"n": 0}

    def _flaky_insert(session, **kw):
        calls["n"] += 1
        if calls["n"] == 11:
            raise RuntimeError("simulated failure half-way through the file")
        return real_insert(session, **kw)

    monkeypatch.setattr(fi, "_insert_sale", _flaky_insert)
    with pytest.raises(RuntimeError):
        await _import(app_role_db, tenant, body)
    assert (await _totals(app_role_db, tenant))["rows"] == 0

    monkeypatch.setattr(fi, "_insert_sale", real_insert)
    await _import(app_role_db, tenant, body)
    assert (await _totals(app_role_db, tenant))["rows"] == 20


async def test_partial_then_full_export_inserts_only_the_remainder(app_role_db, make_tenant):
    tenant = await make_tenant()
    rows = [f"P-{i},KURTI-M,2026-08-{i:02d},{i}" for i in range(1, 11)]
    await _import(app_role_db, tenant, "\n".join(["order_id,sku,date,quantity", *rows[:4]]))
    stats = await _import(app_role_db, tenant, "\n".join(["order_id,sku,date,quantity", *rows]))
    assert stats["rows_inserted"] == 6
    assert stats["rows_unchanged"] == 4
    assert (await _totals(app_role_db, tenant))["units"] == sum(range(1, 11))


async def test_import_identity_is_tenant_scoped(app_role_db, make_tenant):
    a, b = await make_tenant(), await make_tenant()
    body = "order_id,sku,date,quantity\nT-1,KURTI-M,2026-08-24,3"
    await _import(app_role_db, a, body)
    stats_b = await _import(app_role_db, b, body)

    assert stats_b["rows_inserted"] == 1  # tenant B's import is not "already seen"
    assert (await _totals(app_role_db, a))["rows"] == 1
    assert (await _totals(app_role_db, b))["rows"] == 1


async def test_replay_never_touches_rows_that_already_have_duplicate_copies(app_role_db, make_tenant):
    """Legacy duplicates (two rows, one key) are left for Data Quality to repair."""
    tenant = await make_tenant()
    body = "order_id,sku,date,quantity\nL-1,KURTI-M,2026-08-24,3"
    await _import(app_role_db, tenant, body)
    async with app_role_db.session(str(tenant)) as s:
        await s.execute(
            text(
                "INSERT INTO historical_sales (tenant_id, sku_id, industry, sale_time, channel, "
                "units_sold, record_key, metadata) SELECT tenant_id, sku_id, industry, sale_time, "
                "channel, units_sold, record_key, metadata FROM historical_sales"
            )
        )
    stats = await _import(app_role_db, tenant, body.replace(",3", ",9"))
    assert stats["rows_updated"] == 0
    assert any("duplicate" in w for w in stats["warnings"])
    assert (await _totals(app_role_db, tenant))["units"] == 6


def test_unknown_identity_mode_is_rejected():
    with pytest.raises(ValueError, match="identity"):
        asyncio.run(
            fi.import_rows(
                db=None,
                tenant_id=uuid.uuid4(),
                industry=IndustryCode.fashion,
                kind="sales",
                headers=["sku", "date", "quantity"],
                records=[{"sku": "A", "date": "2026-08-24", "quantity": "1"}],
                identity="bogus",
            )
        )
