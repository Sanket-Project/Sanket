"""HTTP contract for replay-safe sales ingestion (F01): file upload and push ingest."""

from __future__ import annotations

import uuid

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.security import hash_password
from app.routers.integrations_hub import _hash_token


async def _login(client: AsyncClient, db: AsyncSession, tenant_id: uuid.UUID) -> dict[str, str]:
    email = f"replay-{uuid.uuid4().hex[:8]}@test.com"
    await db.execute(
        text(
            "INSERT INTO users (id, tenant_id, email, password_hash, full_name, role, "
            "active_industry, is_active) VALUES (:id, :tid, :email, :hash, 'Replay Test', "
            "'admin', 'fashion', TRUE)"
        ),
        {
            "id": str(uuid.uuid4()),
            "tid": str(tenant_id),
            "email": email,
            "hash": hash_password("GoodPass123!", get_settings()),
        },
    )
    await db.commit()
    r = await client.post(
        "/api/v1/auth/dev-login",
        json={"email": email, "password": "GoodPass123!", "tenant_slug": "test-tenant"},
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


async def test_upload_reports_replays_and_accepts_period_identity(client, db_session, test_tenant_id):
    headers = await _login(client, db_session, test_tenant_id)
    sku = f"REPLAY-{uuid.uuid4().hex[:6]}"
    body = f"sku,date,quantity\n{sku},2026-08-24,10\n{sku},2026-08-31,4\n".encode()

    def _post(identity: str):
        return client.post(
            "/api/v1/integrations/upload",
            headers=headers,
            data={"kind": "sales", "identity": identity},
            files={"file": ("weekly.csv", body, "text/csv")},
        )

    first = await _post("period")
    second = await _post("period")

    assert first.status_code == 200, first.text
    assert first.json()["identity_mode"] == "period"
    assert first.json()["rows_inserted"] == 2
    assert second.json()["rows_inserted"] == 0
    assert second.json()["rows_unchanged"] == 2


async def test_upload_rejects_unknown_identity_mode(client, db_session, test_tenant_id):
    headers = await _login(client, db_session, test_tenant_id)
    r = await client.post(
        "/api/v1/integrations/upload",
        headers=headers,
        data={"kind": "sales", "identity": "guess"},
        files={"file": ("x.csv", b"sku,date,quantity\nA,2026-08-24,1\n", "text/csv")},
    )
    assert r.status_code == 422


async def test_push_ingest_is_replay_safe(client, db_session, test_tenant_id):
    token = f"push-{uuid.uuid4().hex}"
    await db_session.execute(
        text(
            "INSERT INTO integration_connections (id, tenant_id, provider, status, target_industry, "
            "state, last_sync_stats) VALUES (:id, :tid, 'webhooks', 'connected', 'fashion', "
            "CAST(:state AS jsonb), '{}')"
        ),
        {
            "id": str(uuid.uuid4()),
            "tid": str(test_tenant_id),
            "state": f'{{"config": {{"push_token_sha256": "{_hash_token(token)}"}}, "credentials_enc": {{}}}}',
        },
    )
    await db_session.commit()
    sku = f"PUSH-{uuid.uuid4().hex[:6]}"
    events = {
        "events": [
            {"order_id": "W-1", "sku": sku, "quantity": 2, "timestamp": "2026-08-24T10:00:00Z"},
            {"order_id": "W-2", "sku": sku, "quantity": 2, "timestamp": "2026-08-24T10:00:00Z"},
            {"sku": sku, "quantity": 1, "timestamp": "2026-08-25T10:00:00Z"},
        ]
    }

    first = await client.post("/api/v1/integrations/ingest", headers={"X-Sanket-Token": token}, json=events)
    replay = await client.post("/api/v1/integrations/ingest", headers={"X-Sanket-Token": token}, json=events)

    assert first.status_code == 200, first.text
    assert first.json()["accepted"] == 3
    assert replay.json()["accepted"] == 0
    assert replay.json()["unchanged"] == 3
    units = await db_session.scalar(
        text(
            "SELECT sum(h.units_sold) FROM historical_sales h JOIN skus s ON s.id = h.sku_id "
            "WHERE h.tenant_id = :t AND s.sku_code = :code"
        ),
        {"t": test_tenant_id, "code": sku},
    )
    assert units == 5
