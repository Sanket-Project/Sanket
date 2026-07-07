# ruff: noqa: S106
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.security import hash_password
from app.models.webhook import WebhookDelivery, WebhookEndpoint, WebhookEventType
from app.services import webhooks

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def cleanup_webhooks(db_session: AsyncSession) -> None:
    await db_session.execute(text("DELETE FROM webhook_deliveries"))
    await db_session.execute(text("DELETE FROM webhook_endpoints"))
    await db_session.commit()


def _mock_response(status_code: int, text: str = "") -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.text = text
    return resp


async def _seed_user(
    db: AsyncSession, tenant_id: uuid.UUID, email: str, password: str, role: str = "admin"
) -> uuid.UUID:
    user_id = uuid.uuid4()
    settings = get_settings()
    await db.execute(
        text(
            """
            INSERT INTO users (id, tenant_id, email, password_hash,
                               full_name, role, active_industry, is_active)
            VALUES (:id, :tid, :email, :hash, 'Test User',
                    :role, 'fashion', TRUE)
            """
        ),
        {
            "id": str(user_id),
            "tid": str(tenant_id),
            "email": email,
            "hash": hash_password(password, settings),
            "role": role,
        },
    )
    await db.commit()
    return user_id


async def test_dispatch_creates_deliveries_and_attempts_immediate_delivery(
    db_session: AsyncSession, test_tenant_id: uuid.UUID
) -> None:
    # 1. Setup active webhook endpoint for the tenant
    endpoint_id = uuid.uuid4()
    endpoint = WebhookEndpoint(
        id=endpoint_id,
        tenant_id=test_tenant_id,
        url="https://example.com/webhook-receiver",
        secret="whsec_12345testsecret",
        enabled_events=[WebhookEventType.forecast_run_completed.value],
        is_active=True,
    )
    db_session.add(endpoint)
    await db_session.commit()

    # 2. Mock the http post method to succeed (200 OK)
    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = _mock_response(200, "Success")

        payload = {"forecast_id": str(uuid.uuid4()), "status": "completed"}
        num_attempted = await webhooks.dispatch(
            db_session,
            tenant_id=test_tenant_id,
            event_type=WebhookEventType.forecast_run_completed,
            payload=payload,
        )

        assert num_attempted == 1
        mock_post.assert_called_once()

        # Check webhook deliveries table
        result = await db_session.execute(
            select(WebhookDelivery).where(WebhookDelivery.endpoint_id == endpoint_id)
        )
        deliveries = result.scalars().all()
        assert len(deliveries) == 1
        d = deliveries[0]
        assert d.status == "succeeded"
        assert d.response_status == 200
        assert d.response_body == "Success"
        assert d.attempt_count == 1
        assert d.delivered_at is not None


async def test_dispatch_does_not_queue_for_inactive_endpoints(
    db_session: AsyncSession, test_tenant_id: uuid.UUID
) -> None:
    endpoint_id = uuid.uuid4()
    endpoint = WebhookEndpoint(
        id=endpoint_id,
        tenant_id=test_tenant_id,
        url="https://example.com/webhook-inactive",
        secret="whsec_inactive",
        enabled_events=[WebhookEventType.forecast_run_completed.value],
        is_active=False,
    )
    db_session.add(endpoint)
    await db_session.commit()

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = _mock_response(200, "Should not be called")
        num_attempted = await webhooks.dispatch(
            db_session,
            tenant_id=test_tenant_id,
            event_type=WebhookEventType.forecast_run_completed,
            payload={"test": "data"},
        )
        assert num_attempted == 0
        mock_post.assert_not_called()

        # Check no deliveries
        result = await db_session.execute(
            select(WebhookDelivery).where(WebhookDelivery.endpoint_id == endpoint_id)
        )
        assert len(result.scalars().all()) == 0


async def test_try_deliver_schedules_retry_on_failure(
    db_session: AsyncSession, test_tenant_id: uuid.UUID
) -> None:
    endpoint_id = uuid.uuid4()
    endpoint = WebhookEndpoint(
        id=endpoint_id,
        tenant_id=test_tenant_id,
        url="https://example.com/webhook-fail",
        secret="whsec_fail",
        enabled_events=[WebhookEventType.forecast_run_failed.value],
        is_active=True,
    )
    db_session.add(endpoint)
    await db_session.commit()

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = _mock_response(502, "Bad Gateway")

        num_attempted = await webhooks.dispatch(
            db_session,
            tenant_id=test_tenant_id,
            event_type=WebhookEventType.forecast_run_failed,
            payload={"error": "db_down"},
        )
        assert num_attempted == 1

        result = await db_session.execute(
            select(WebhookDelivery).where(WebhookDelivery.endpoint_id == endpoint_id)
        )
        d = result.scalars().one()
        assert d.status == "pending"
        assert d.response_status == 502
        assert d.response_body == "Bad Gateway"
        assert d.attempt_count == 1
        assert d.next_retry_at is not None


async def test_retry_worker_tick_selective_processing(
    db_session: AsyncSession, test_tenant_id: uuid.UUID
) -> None:
    ep1_id = uuid.uuid4()
    ep1 = WebhookEndpoint(
        id=ep1_id,
        tenant_id=test_tenant_id,
        url="https://example.com/endpoint1",
        secret="whsec_ep1",
        enabled_events=[WebhookEventType.signal_validated.value],
        is_active=True,
    )
    ep2_id = uuid.uuid4()
    ep2 = WebhookEndpoint(
        id=ep2_id,
        tenant_id=test_tenant_id,
        url="https://example.com/endpoint2",
        secret="whsec_ep2",
        enabled_events=[WebhookEventType.signal_validated.value],
        is_active=True,
    )
    db_session.add_all([ep1, ep2])
    await db_session.commit()

    # Create two pending webhook deliveries
    # One is due (next_retry_at is in the past)
    # One is NOT due (next_retry_at is in the future)
    due_delivery = WebhookDelivery(
        tenant_id=test_tenant_id,
        endpoint_id=ep1_id,
        event_type=WebhookEventType.signal_validated,
        payload={"msg": "due"},
        status="pending",
        attempt_count=1,
        next_retry_at=datetime.now(tz=UTC) - timedelta(minutes=10),
    )
    future_delivery = WebhookDelivery(
        tenant_id=test_tenant_id,
        endpoint_id=ep2_id,
        event_type=WebhookEventType.signal_validated,
        payload={"msg": "future"},
        status="pending",
        attempt_count=1,
        next_retry_at=datetime.now(tz=UTC) + timedelta(minutes=10),
    )
    db_session.add_all([due_delivery, future_delivery])
    await db_session.commit()

    due_id = due_delivery.id
    future_id = future_delivery.id

    with patch("httpx.AsyncClient.post") as mock_post:
        mock_post.return_value = _mock_response(200, "OK")

        # Run worker tick
        processed = await webhooks.retry_worker_tick(db_session, batch_size=10)
        assert processed == 1
        mock_post.assert_called_once()

        await db_session.commit()

        # Verify due delivery succeeded
        res_due = await db_session.execute(
            select(WebhookDelivery).where(WebhookDelivery.id == due_id)
        )
        d_due = res_due.scalar_one()
        assert d_due.status == "succeeded"
        assert d_due.attempt_count == 2

        # Verify future delivery is untouched
        res_future = await db_session.execute(
            select(WebhookDelivery).where(WebhookDelivery.id == future_id)
        )
        d_future = res_future.scalar_one()
        assert d_future.status == "pending"
        assert d_future.attempt_count == 1


async def test_retry_worker_tick_savepoint_isolation_on_failure(
    db_session: AsyncSession, test_tenant_id: uuid.UUID
) -> None:
    # Setup two endpoints
    ep1_id = uuid.uuid4()
    ep1 = WebhookEndpoint(
        id=ep1_id,
        tenant_id=test_tenant_id,
        url="https://example.com/success-endpoint",
        secret="whsec_ep1",
        enabled_events=[WebhookEventType.signal_validated.value],
        is_active=True,
    )
    ep2_id = uuid.uuid4()
    ep2 = WebhookEndpoint(
        id=ep2_id,
        tenant_id=test_tenant_id,
        url="https://example.com/crash-endpoint",
        secret="whsec_ep2",
        enabled_events=[WebhookEventType.signal_validated.value],
        is_active=True,
    )
    db_session.add_all([ep1, ep2])
    await db_session.commit()

    # Create two due deliveries
    d1 = WebhookDelivery(
        tenant_id=test_tenant_id,
        endpoint_id=ep1_id,
        event_type=WebhookEventType.signal_validated,
        payload={"msg": "success"},
        status="pending",
        attempt_count=1,
        next_retry_at=datetime.now(tz=UTC) - timedelta(minutes=5),
    )
    d2 = WebhookDelivery(
        tenant_id=test_tenant_id,
        endpoint_id=ep2_id,
        event_type=WebhookEventType.signal_validated,
        payload={"msg": "crash"},
        status="pending",
        attempt_count=1,
        next_retry_at=datetime.now(tz=UTC) - timedelta(minutes=5),
    )
    db_session.add_all([d1, d2])
    await db_session.commit()

    d1_id = d1.id
    d2_id = d2.id

    async def mock_post_action(url, **kwargs):
        url_str = str(url)
        if "success-endpoint" in url_str:
            return _mock_response(200, "OK")
        elif "crash-endpoint" in url_str:
            raise httpx.ConnectError("Network is down")
        return _mock_response(404, "Not Found")

    with patch("httpx.AsyncClient.post", side_effect=mock_post_action):
        processed = await webhooks.retry_worker_tick(db_session, batch_size=10)
        assert processed == 2

        await db_session.commit()

        # Verify d1 succeeded
        res1 = await db_session.execute(
            select(WebhookDelivery).where(WebhookDelivery.id == d1_id)
        )
        d1_updated = res1.scalar_one()
        assert d1_updated.status == "succeeded"

        # Verify d2 rolled back to savepoint and scheduled retry
        res2 = await db_session.execute(
            select(WebhookDelivery).where(WebhookDelivery.id == d2_id)
        )
        d2_updated = res2.scalar_one()
        assert d2_updated.status == "pending"
        assert d2_updated.attempt_count == 2
        assert d2_updated.response_body is not None
        assert "Network is down" in d2_updated.response_body


async def test_retry_delivery_via_router_api(
    client: AsyncClient, db_session: AsyncSession, test_tenant_id: uuid.UUID
) -> None:
    # 1. Seed user for authentication
    await _seed_user(db_session, test_tenant_id, "admin-webhook@test.com", "AdminPass123!")

    # 2. Setup endpoint and a failed delivery
    ep_id = uuid.uuid4()
    ep = WebhookEndpoint(
        id=ep_id,
        tenant_id=test_tenant_id,
        url="https://example.com/retry-endpoint",
        secret="whsec_ep_retry",
        enabled_events=[WebhookEventType.signal_validated.value],
        is_active=True,
    )
    db_session.add(ep)
    await db_session.commit()

    d = WebhookDelivery(
        tenant_id=test_tenant_id,
        endpoint_id=ep_id,
        event_type=WebhookEventType.signal_validated,
        payload={"msg": "retry-me"},
        status="failed",
        attempt_count=2,
    )
    db_session.add(d)
    await db_session.commit()
    d_id = d.id

    # 3. Authenticate to get a dev-token
    login_resp = await client.post(
        "/api/v1/auth/dev-login",
        json={
            "email": "admin-webhook@test.com",
            "password": "AdminPass123!",
            "tenant_slug": "test-tenant",
        },
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 4. Request manual retry through router endpoint
    original_post = httpx.AsyncClient.post

    async def selective_post(self, url, *args, **kwargs):
        url_str = str(url)
        if "retry-endpoint" in url_str:
            return _mock_response(200, "Resent OK")
        return await original_post(self, url, *args, **kwargs)

    with patch("httpx.AsyncClient.post", new=selective_post):
        url = f"/api/v1/webhooks/deliveries/{d_id}/retry"
        r = await client.post(url, headers=headers)
        
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["id"] == d_id
        assert body["status"] == "succeeded"
        assert body["attempt_count"] == 3
        assert body["response_status"] == 200

        # Check DB state
        await db_session.commit()
        db_session.expire_all()
        res = await db_session.execute(
            select(WebhookDelivery).where(WebhookDelivery.id == d_id)
        )
        d_reloaded = res.scalar_one()
        assert d_reloaded.status == "succeeded"
        assert d_reloaded.attempt_count == 3
        assert d_reloaded.response_body == "Resent OK"
