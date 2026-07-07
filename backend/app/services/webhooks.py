"""Outbound webhook delivery with HMAC signing and exponential backoff retry.

Design:
  • dispatch(event) inserts a row into webhook_deliveries (status=pending)
    for every matching endpoint, then attempts immediate delivery.
  • A background worker periodically retries `pending` rows where
    `next_retry_at <= now()`.
  • Backoff schedule: 30s → 2m → 10m → 1h → 6h → dead_letter after 6 attempts.
  • Payload signed with HMAC-SHA256 of `{timestamp}.{body}` using the
    endpoint's secret. Receivers verify per Stripe-style scheme.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.webhook import WebhookDelivery, WebhookEndpoint, WebhookEventType
from app.realtime.events import RealtimeEvent

log = structlog.get_logger(__name__)

BACKOFF_SCHEDULE_SEC = [30, 120, 600, 3600, 21600]
MAX_ATTEMPTS = len(BACKOFF_SCHEDULE_SEC) + 1
DELIVERY_TIMEOUT_SEC = 10.0


def generate_secret() -> str:
    return "whsec_" + secrets.token_urlsafe(40)


def sign_payload(secret: str, body: bytes, timestamp: int) -> str:
    """Stripe-style signature: t=<ts>,v1=<hmac_sha256>"""
    msg = f"{timestamp}.".encode() + body
    sig = hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={sig}"


async def dispatch(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    event_type: WebhookEventType,
    payload: dict[str, Any],
    http_client: httpx.AsyncClient | None = None,
) -> int:
    """Queue + immediately attempt delivery to every active matching endpoint.
    Returns the number of endpoints we attempted to notify."""
    res = await session.execute(
        select(WebhookEndpoint).where(
            WebhookEndpoint.tenant_id == tenant_id,
            WebhookEndpoint.is_active.is_(True),
        )
    )
    endpoints = [ep for ep in res.scalars().all() if event_type.value in (ep.enabled_events or [])]
    if not endpoints:
        return 0

    delivery_ids: list[int] = []
    for ep in endpoints:
        delivery = WebhookDelivery(
            tenant_id=tenant_id,
            endpoint_id=ep.id,
            event_type=event_type,
            payload=payload,
            status="pending",
            next_retry_at=datetime.now(tz=UTC),
        )
        session.add(delivery)
        await session.flush()
        delivery_ids.append(delivery.id)
    await session.commit()

    # Best-effort immediate attempt
    own_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=DELIVERY_TIMEOUT_SEC)
    try:
        for did in delivery_ids:
            await _try_deliver(session, did, client)
    finally:
        if own_client:
            await client.aclose()
    return len(endpoints)


async def _try_deliver(session: AsyncSession, delivery_id: int, client: httpx.AsyncClient) -> None:
    delivery = await session.get(WebhookDelivery, delivery_id)
    if delivery is None or delivery.status in ("succeeded", "dead_letter"):
        return
    endpoint = await session.get(WebhookEndpoint, delivery.endpoint_id)
    if endpoint is None or not endpoint.is_active:
        delivery.status = "dead_letter"
        # Caller's context manager commits
        return

    body = json.dumps(
        {
            "event_id": str(delivery.event_id),
            "type": delivery.event_type.value,
            "tenant_id": str(delivery.tenant_id),
            "occurred_at": delivery.created_at.isoformat(),
            "data": delivery.payload,
        }
    ).encode()
    timestamp = int(datetime.now(tz=UTC).timestamp())
    signature = sign_payload(endpoint.secret, body, timestamp)
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "SANKET-Webhooks/1.0",
        "X-Sanket-Signature": signature,
        "X-Sanket-Event": delivery.event_type.value,
        "X-Sanket-Delivery-Id": str(delivery.id),
        "X-Sanket-Event-Id": str(delivery.event_id),
    }

    delivery.attempt_count += 1
    try:
        r = await client.post(endpoint.url, content=body, headers=headers)
        delivery.response_status = r.status_code
        delivery.response_body = r.text[:2000]
        if 200 <= r.status_code < 300:
            delivery.status = "succeeded"
            delivery.delivered_at = datetime.now(tz=UTC)
            endpoint.failure_count = 0
            endpoint.last_delivery_at = delivery.delivered_at
        else:
            _schedule_retry(delivery, endpoint)
    except (TimeoutError, httpx.HTTPError) as exc:
        delivery.response_status = None
        delivery.response_body = str(exc)[:2000]
        _schedule_retry(delivery, endpoint)

    # Single commit at the end — the caller's context manager may also commit;
    # SQLAlchemy handles double-commit gracefully (no-op if nothing pending).
    await session.flush()
    log.info(
        "webhook.delivery.attempt",
        delivery_id=delivery_id,
        status=delivery.status,
        attempt=delivery.attempt_count,
        response_status=delivery.response_status,
    )


def _schedule_retry(delivery: WebhookDelivery, endpoint: WebhookEndpoint) -> None:
    endpoint.failure_count = (endpoint.failure_count or 0) + 1
    if delivery.attempt_count >= MAX_ATTEMPTS:
        delivery.status = "dead_letter"
        delivery.next_retry_at = None
        return
    delay = BACKOFF_SCHEDULE_SEC[min(delivery.attempt_count - 1, len(BACKOFF_SCHEDULE_SEC) - 1)]
    delivery.next_retry_at = datetime.now(tz=UTC) + timedelta(seconds=delay)
    delivery.status = "pending"


# ── background retry worker ──
async def retry_worker_tick(session: AsyncSession, batch_size: int = 50) -> int:
    """Pick up `pending` deliveries due for retry. Run on a CronJob or async loop.

    Each delivery is processed in its own sub-transaction (SAVEPOINT) so a
    single failed delivery doesn't roll back the entire batch.
    """
    res = await session.execute(
        text(
            """
            SELECT id
            FROM webhook_deliveries
            WHERE status = 'pending'
              AND (next_retry_at IS NULL OR next_retry_at <= now())
            ORDER BY next_retry_at NULLS FIRST
            LIMIT :limit
            FOR UPDATE SKIP LOCKED
            """
        ),
        {"limit": batch_size},
    )
    ids = [row.id for row in res]
    if not ids:
        return 0
    async with httpx.AsyncClient(timeout=DELIVERY_TIMEOUT_SEC) as client:
        for did in ids:
            try:
                async with session.begin_nested():  # SAVEPOINT per delivery
                    await _try_deliver(session, did, client)
            except Exception as exc:
                log.error("webhook.retry.delivery_failed", delivery_id=did, error=str(exc))
    return len(ids)


# Convenience to dispatch from a RealtimeEvent
async def dispatch_event(session: AsyncSession, event: RealtimeEvent) -> int:
    try:
        event_type = WebhookEventType(event.type)
    except ValueError:
        # Not a webhook-eligible event (e.g. progress streams)
        return 0
    return await dispatch(
        session,
        tenant_id=event.tenant_id,
        event_type=event_type,
        payload=event.data,
    )
