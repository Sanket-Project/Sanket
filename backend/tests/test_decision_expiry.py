"""Recommendation expiry is enforced by the server, not just recorded (deep audit F2).

``persist_decisions`` stamps every recommendation with ``expires_at``; before
this fix nothing read it, so a recommendation built from month-old inputs could
still be accepted and counted in the ROI ledger. Each test uses its own
synthetic workspace so no live recommendation is touched.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import text


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


async def _open_rec(db, tenant, sku, expires_at):
    rid = uuid.uuid4()
    await db.execute(
        text("INSERT INTO recommendations (id, tenant_id, industry, sku_id, kind, status, urgency, "
             "headline, recommended_units, expires_at) VALUES (:r, :t, 'fashion', :s, "
             "'purchase_order', 'open', 'high', 'Raise a purchase order for 10 units', 10, :e)"),
        {"r": str(rid), "t": str(tenant), "s": str(sku), "e": expires_at},
    )
    return str(rid)


@pytest.fixture
async def queue(signed_in_workspace, db_session):
    tenant, headers = await signed_in_workspace("fashion")
    now = datetime.now(UTC)
    expired = await _open_rec(db_session, tenant, await _sku(db_session, tenant, "EXP-OLD"),
                              now - timedelta(days=30))
    live = await _open_rec(db_session, tenant, await _sku(db_session, tenant, "EXP-LIVE"),
                           now + timedelta(days=1))
    await db_session.commit()
    return SimpleNamespace(headers=headers, expired=expired, live=live)


async def test_open_queue_excludes_time_expired_recommendations(client, queue):
    r = await client.get("/api/v1/decisions?status=open", headers=queue.headers)
    assert r.status_code == 200, r.text
    ids = {d["id"] for d in r.json()["decisions"]}
    assert queue.live in ids
    assert queue.expired not in ids


async def test_expired_filter_includes_open_rows_past_their_expiry(client, queue):
    r = await client.get("/api/v1/decisions?status=expired", headers=queue.headers)
    assert r.status_code == 200, r.text
    rows = {d["id"]: d for d in r.json()["decisions"]}
    assert queue.expired in rows
    assert rows[queue.expired]["status"] == "expired"
    assert rows[queue.expired]["expired"] is True


async def test_accepting_an_expired_recommendation_is_rejected(client, queue, db_session):
    r = await client.post(f"/api/v1/decisions/{queue.expired}/accept", json={}, headers=queue.headers)
    assert r.status_code == 409, r.text
    assert "expired" in r.json()["detail"].lower()
    assert "recompute" in r.json()["detail"].lower()
    status = await db_session.scalar(
        text("SELECT status::text FROM recommendations WHERE id = :i"), {"i": queue.expired}
    )
    assert status == "open"  # nothing recorded in the ROI ledger


async def test_accepting_a_live_recommendation_still_works(client, queue):
    r = await client.post(f"/api/v1/decisions/{queue.live}/accept", json={}, headers=queue.headers)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "accepted"


def test_expiry_boundary_is_inclusive():
    from app.routers.decisions import is_expired

    now = datetime(2026, 10, 26, 9, tzinfo=UTC)
    assert is_expired(SimpleNamespace(expires_at=now), now)
    assert is_expired(SimpleNamespace(expires_at=now - timedelta(seconds=1)), now)
    assert not is_expired(SimpleNamespace(expires_at=now + timedelta(seconds=1)), now)
    assert not is_expired(SimpleNamespace(expires_at=None), now)
