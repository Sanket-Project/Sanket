"""The WhatsApp digest follows the queue's rules (code review of deep audit F2/F3).

It counted open recommendations past their expiry, and added only the valued
orders into "Total at stake" while presenting it as the whole.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.services.notifications import digest as digest_svc
from app.services.notifications.whatsapp import WhatsAppConfig


async def _sku(db, tenant, code):
    pid, sid = uuid.uuid4(), uuid.uuid4()
    await db.execute(
        text("INSERT INTO products (id, tenant_id, industry, name, category, status) "
             "VALUES (:p, :t, 'fashion', 'Kurti', 'Kurtis', 'active')"),
        {"p": str(pid), "t": str(tenant)},
    )
    await db.execute(
        text("INSERT INTO skus (id, tenant_id, product_id, industry, sku_code) "
             "VALUES (:s, :t, :p, 'fashion', :c)"),
        {"s": str(sid), "t": str(tenant), "p": str(pid), "c": code},
    )
    return sid


async def _rec(db, tenant, sku, *, expires_at, revenue):
    await db.execute(
        text("INSERT INTO recommendations (id, tenant_id, industry, sku_id, kind, status, urgency, "
             "headline, recommended_units, confidence, economics, expires_at) VALUES (:r, :t, "
             "'fashion', :s, 'purchase_order', 'open', 'high', 'Order', 10, 80, CAST(:e AS jsonb), :x)"),
        {"r": str(uuid.uuid4()), "t": str(tenant), "s": str(sku), "x": expires_at,
         "e": '{"revenue_protected": %s}' % ("null" if revenue is None else revenue)},
    )


async def _build(app_role_db, tenant):
    async with app_role_db.session(str(tenant)) as s:
        return await digest_svc.build_digest(
            s, tenant_id=tenant, tenant_name="Synthetic", industry="fashion", config=WhatsAppConfig()
        )


async def test_expired_recommendations_are_left_out(app_role_db, make_tenant, db_session):
    tenant = await make_tenant("fashion")
    now = datetime.now(UTC)
    await _rec(db_session, tenant, await _sku(db_session, tenant, "DG-LIVE"),
               expires_at=now + timedelta(days=3), revenue=1000)
    await _rec(db_session, tenant, await _sku(db_session, tenant, "DG-OLD"),
               expires_at=now - timedelta(days=3), revenue=5000)
    await db_session.commit()

    digest = await _build(app_role_db, tenant)

    assert [item.sku_code for item in digest.items] == ["DG-LIVE"]


async def test_unvalued_orders_withhold_the_total(app_role_db, make_tenant, db_session):
    tenant = await make_tenant("fashion")
    now = datetime.now(UTC)
    await _rec(db_session, tenant, await _sku(db_session, tenant, "DG-VALUED"),
               expires_at=now + timedelta(days=3), revenue=1000)
    await _rec(db_session, tenant, await _sku(db_session, tenant, "DG-UNVALUED"),
               expires_at=now + timedelta(days=3), revenue=None)
    await db_session.commit()

    digest = await _build(app_role_db, tenant)
    body = digest_svc.render_text(digest)

    assert digest.unvalued == 1
    assert "Total at stake" not in body
    assert "1 order has no recorded value" in body
    assert digest.as_dict()["total_value"] is None
    assert digest.as_dict()["unvalued"] == 1
