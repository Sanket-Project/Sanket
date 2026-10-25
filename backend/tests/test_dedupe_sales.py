"""Duplicate-sales detection and repair (audit F12).

The old repair 500'd on PostgreSQL 16 (``min(uuid)``) and would have merged
genuinely different sales that merely shared SKU, time and quantity. Duplicates
are now provable — rows sharing a ``record_key`` — and the repair only removes
identical copies. Everything here runs as ``sanket_app`` under RLS.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from app.models.enums import IndustryCode
from app.services import data_quality_audit as dqa
from app.services.integrations import file_import as fi

_FILE = """
order_id,sku,date,quantity,price
D-1,KURTI-M,2026-08-24,3,100
D-2,KURTI-L,2026-08-24,4,100
D-3,GOWN-M,2026-08-31,5,200
"""


async def _import(db, tenant, body=_FILE):
    headers, records = fi.parse_table("s.csv", body.strip().encode())
    return await fi.import_rows(
        db=db, tenant_id=tenant, industry=IndustryCode.fashion, kind="sales",
        headers=headers, records=records,
    )


async def _replay_like_before_the_fix(db, tenant):
    """Copy every row once, exactly as a pre-fix second upload did (INSERT only)."""
    async with db.session(str(tenant)) as s:
        await s.execute(
            text(
                "INSERT INTO historical_sales (tenant_id, sku_id, industry, sale_time, channel, "
                "region, location, units_sold, gross_revenue, net_revenue, returns, in_stock, "
                "promo_flag, markdown_pct, record_key, metadata) "
                "SELECT tenant_id, sku_id, industry, sale_time, channel, region, location, "
                "units_sold, gross_revenue, net_revenue, returns, in_stock, promo_flag, "
                "markdown_pct, record_key, "
                "metadata || jsonb_build_object('upload_id', 'replayed') FROM historical_sales"
            )
        )


async def _rows(db, tenant):
    async with db.session(str(tenant)) as s:
        return (
            await s.execute(text("SELECT id, record_key, units_sold FROM historical_sales"))
        ).all()


async def _fix(db, tenant, *, confirm: bool):
    async with db.session(str(tenant)) as s:
        return await dqa.apply_fix(
            s, tenant_id=tenant, industry="fashion", action="dedupe_sales", dry_run=not confirm
        )


async def test_preview_reports_the_repair_without_changing_anything(app_role_db, make_tenant):
    tenant = await make_tenant()
    await _import(app_role_db, tenant)
    await _replay_like_before_the_fix(app_role_db, tenant)

    preview = await _fix(app_role_db, tenant, confirm=False)

    assert preview["dry_run"] is True
    assert preview["applied"] is False
    assert preview["rows_affected"] == 3
    assert preview["groups_removable"] == 3
    assert preview["groups_conflicting"] == 0
    assert preview["units_removed"] == 12
    assert "identical" in preview["survivor_rule"]
    assert len(await _rows(app_role_db, tenant)) == 6


async def test_repair_keeps_exactly_one_copy_of_each_sale(app_role_db, make_tenant):
    tenant = await make_tenant()
    await _import(app_role_db, tenant)
    await _replay_like_before_the_fix(app_role_db, tenant)
    before = await _rows(app_role_db, tenant)
    expected_survivors = {}
    for r in before:
        current = expected_survivors.get(r.record_key)
        if current is None or str(r.id) < current:
            expected_survivors[r.record_key] = str(r.id)

    result = await _fix(app_role_db, tenant, confirm=True)
    after = await _rows(app_role_db, tenant)

    assert result["applied"] is True
    assert result["rows_affected"] == 3
    assert sorted(r.units_sold for r in after) == [3, 4, 5]
    assert {str(r.id) for r in after} == set(expected_survivors.values())


async def test_identical_lines_from_one_file_are_not_duplicates(app_role_db, make_tenant):
    tenant = await make_tenant()
    await _import(app_role_db, tenant, "sku,date,quantity\nKURTI-M,2026-08-24,2\nKURTI-M,2026-08-24,2")

    preview = await _fix(app_role_db, tenant, confirm=True)

    assert preview["rows_affected"] == 0
    assert len(await _rows(app_role_db, tenant)) == 2


async def test_copies_that_disagree_are_reported_and_never_deleted(app_role_db, make_tenant):
    tenant = await make_tenant()
    await _import(app_role_db, tenant)
    async with app_role_db.session(str(tenant)) as s:
        await s.execute(
            text(
                "INSERT INTO historical_sales (tenant_id, sku_id, industry, sale_time, channel, "
                "units_sold, record_key, metadata) SELECT tenant_id, sku_id, industry, sale_time, "
                "channel, units_sold + 9, record_key, metadata FROM historical_sales "
                "WHERE metadata->>'order_id' = 'D-1'"
            )
        )

    result = await _fix(app_role_db, tenant, confirm=True)

    assert result["groups_conflicting"] == 1
    assert result["rows_affected"] == 0
    assert len(await _rows(app_role_db, tenant)) == 4


async def test_repair_only_touches_the_callers_tenant(app_role_db, make_tenant):
    a, b = await make_tenant(), await make_tenant()
    for t in (a, b):
        await _import(app_role_db, t)
        await _replay_like_before_the_fix(app_role_db, t)

    await _fix(app_role_db, a, confirm=True)

    assert len(await _rows(app_role_db, a)) == 3
    assert len(await _rows(app_role_db, b)) == 6


async def test_repair_rolls_back_with_its_transaction(app_role_db, make_tenant):
    tenant = await make_tenant()
    await _import(app_role_db, tenant)
    await _replay_like_before_the_fix(app_role_db, tenant)

    async def _repair_then_fail() -> None:
        async with app_role_db.session(str(tenant)) as s:
            await dqa.apply_fix(
                s, tenant_id=tenant, industry="fashion", action="dedupe_sales", dry_run=False
            )
            raise RuntimeError("caller failed after the repair")

    with pytest.raises(RuntimeError):
        await _repair_then_fail()

    assert len(await _rows(app_role_db, tenant)) == 6


async def test_repair_refuses_to_run_without_a_tenant_scope(app_role_db):
    with pytest.raises(Exception, match="requires app.current_tenant_id"):
        async with app_role_db.session(None) as s:
            await s.execute(text("SELECT * FROM sanket_dedupe_sales('fashion', false)"))


async def test_report_counts_confirmed_and_possible_duplicates(app_role_db, make_tenant):
    tenant = await make_tenant()
    await _import(app_role_db, tenant)
    await _replay_like_before_the_fix(app_role_db, tenant)
    async with app_role_db.session(str(tenant)) as s:
        # Two unkeyed, fully identical rows from a source that does not key its sales.
        sku = await s.scalar(text("SELECT sku_id FROM historical_sales LIMIT 1"))
        for _ in range(2):
            await s.execute(
                text(
                    "INSERT INTO historical_sales (tenant_id, sku_id, industry, sale_time, channel, "
                    "units_sold, metadata) VALUES (:t, :s, 'fashion', '2026-07-01', 'pos', 1, "
                    "'{\"source\": \"manual\"}')"
                ),
                {"t": str(tenant), "s": str(sku)},
            )
        report = await dqa.audit(s, tenant_id=tenant, industry="fashion")
        extra = await dqa.confirmed_duplicate_count(s, tenant_id=tenant, industry="fashion")

    findings = {f["key"]: f for f in report["findings"]}
    assert extra == 3
    assert findings["duplicate_sales_rows"]["count"] == 3
    assert findings["duplicate_sales_rows"]["severity"] == "critical"
    assert findings["duplicate_sales_rows"]["autofix"] == "dedupe_sales"
    assert findings["possible_duplicate_sales"]["count"] == 1
    assert findings["possible_duplicate_sales"]["autofix"] is None


async def test_fix_endpoint_preview_no_longer_500s(client, db_session, test_tenant_id):
    """Regression for the audit's POST /data-quality/fix 500 (min(uuid))."""
    from app.config import get_settings
    from app.core.security import hash_password

    email = f"dq-{uuid.uuid4().hex[:8]}@test.com"
    await db_session.execute(
        text(
            "INSERT INTO users (id, tenant_id, email, password_hash, full_name, role, "
            "active_industry, is_active) VALUES (:id, :t, :e, :h, 'DQ', 'admin', 'fashion', TRUE)"
        ),
        {"id": str(uuid.uuid4()), "t": str(test_tenant_id), "e": email,
         "h": hash_password("GoodPass123!", get_settings())},
    )
    await db_session.commit()
    login = await client.post(
        "/api/v1/auth/dev-login",
        json={"email": email, "password": "GoodPass123!", "tenant_slug": "test-tenant"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    r = await client.post(
        "/api/v1/data-quality/fix", headers=headers, json={"action": "dedupe_sales", "confirm": False}
    )

    assert r.status_code == 200, r.text
    assert r.json()["dry_run"] is True


async def test_confirmed_repair_is_recorded_in_the_audit_log(client, db_session, test_tenant_id):
    from app.config import get_settings
    from app.core.security import hash_password

    email = f"dq-audit-{uuid.uuid4().hex[:8]}@test.com"
    await db_session.execute(
        text(
            "INSERT INTO users (id, tenant_id, email, password_hash, full_name, role, "
            "active_industry, is_active) VALUES (:id, :t, :e, :h, 'DQ', 'admin', 'fashion', TRUE)"
        ),
        {"id": str(uuid.uuid4()), "t": str(test_tenant_id), "e": email,
         "h": hash_password("GoodPass123!", get_settings())},
    )
    await db_session.commit()
    login = await client.post(
        "/api/v1/auth/dev-login",
        json={"email": email, "password": "GoodPass123!", "tenant_slug": "test-tenant"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    r = await client.post(
        "/api/v1/data-quality/fix", headers=headers, json={"action": "dedupe_sales", "confirm": True}
    )
    assert r.status_code == 200, r.text

    logged = await db_session.scalar(
        text(
            "SELECT count(*) FROM audit_log WHERE tenant_id = :t AND action = 'data_quality.fix' "
            "AND new_value->>'action' = 'dedupe_sales'"
        ),
        {"t": str(test_tenant_id)},
    )
    assert logged >= 1
