"""Integration connections — Shopify (MVP).

Endpoints (all tenant-scoped via the auth middleware):

    GET    /integrations/shopify            → current connection status
    POST   /integrations/shopify/connect    → validate token + save connection
    POST   /integrations/shopify/sync       → trigger a background backfill
    DELETE /integrations/shopify            → disconnect (forget token)

The backfill runs in-process as a background task (sync is IO-bound, not CPU
heavy), returning 202 immediately so the UI can poll status. The access token is
encrypted at rest and never returned to the client.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import UTC, datetime, timedelta

import structlog
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select, text, update

from app.config import get_settings
from app.core.crypto import decrypt_secret, encrypt_secret
from app.models.integration import IntegrationConnection
from app.routers.industry_router import TenantId, UserId
from app.schemas.integrations import (
    IntegrationStatus,
    LiveSaleRow,
    LiveSalesSummary,
    ShopifyConnectRequest,
    SyncAccepted,
    SyncScope,
)
from app.services import audit
from app.services.integrations.shopify_client import (
    ShopifyClient,
    ShopifyError,
    verify_webhook_hmac,
)
from app.services.integrations.shopify_sync import ingest_single_order, run_shopify_sync

WEBHOOK_PATH = "/api/v1/integrations/shopify/webhook"
WEBHOOK_TOPICS = ("orders/create", "orders/updated")

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/integrations", tags=["integrations"])

PROVIDER = "shopify"


def _to_status(conn: IntegrationConnection | None) -> IntegrationStatus:
    if conn is None:
        return IntegrationStatus(provider=PROVIDER, connected=False, status="disconnected")
    industry = (
        conn.target_industry.value
        if hasattr(conn.target_industry, "value")
        else str(conn.target_industry)
    )
    return IntegrationStatus(
        provider=conn.provider,
        connected=conn.status in ("connected", "syncing"),
        status=conn.status,
        shop_domain=conn.shop_domain,
        target_industry=industry,
        last_sync_at=conn.last_sync_at,
        last_sync_status=conn.last_sync_status,
        last_sync_stats=conn.last_sync_stats or {},
        error_message=conn.error_message,
        shop_name=(conn.last_sync_stats or {}).get("shop_name"),
    )


async def _load(db, tenant_id: uuid.UUID) -> IntegrationConnection | None:
    async with db.session(str(tenant_id)) as session:
        return await session.scalar(
            select(IntegrationConnection).where(
                IntegrationConnection.tenant_id == tenant_id,
                IntegrationConnection.provider == PROVIDER,
            )
        )


@router.get("/shopify", response_model=IntegrationStatus)
async def shopify_status(request: Request, tenant_id: TenantId) -> IntegrationStatus:
    return _to_status(await _load(request.app.state.db, tenant_id))


@router.post("/shopify/connect", response_model=IntegrationStatus)
async def shopify_connect(
    body: ShopifyConnectRequest, request: Request, tenant_id: TenantId, user_id: UserId
) -> IntegrationStatus:
    db = request.app.state.db
    http = getattr(request.app.state, "http", None)
    settings = get_settings()

    # Validate the token against Shopify before persisting anything.
    try:
        async with ShopifyClient(
            body.shop_domain,
            body.access_token,
            api_version=settings.shopify_api_version,
            http_client=http,
        ) as client:
            shop = await client.get_shop()
    except ShopifyError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    encrypted = encrypt_secret(body.access_token)
    normalized_domain = ShopifyClient(body.shop_domain, body.access_token).shop_domain

    # Webhook signing secret (the app's API secret) is stored encrypted in state,
    # used only to verify inbound webhooks. Optional — polling works without it.
    extra_state: dict = {}
    if body.api_secret:
        extra_state["webhook_secret_enc"] = encrypt_secret(body.api_secret)

    async with db.session(str(tenant_id)) as session:
        existing = await session.scalar(
            select(IntegrationConnection).where(
                IntegrationConnection.tenant_id == tenant_id,
                IntegrationConnection.provider == PROVIDER,
            )
        )
        if existing is None:
            conn = IntegrationConnection(
                tenant_id=tenant_id,
                provider=PROVIDER,
                status="connected",
                shop_domain=normalized_domain,
                access_token_encrypted=encrypted,
                target_industry=body.target_industry,
                last_sync_stats={"shop_name": shop.get("name")},
                state=extra_state,
                error_message=None,
            )
            session.add(conn)
        else:
            existing.status = "connected"
            existing.shop_domain = normalized_domain
            existing.access_token_encrypted = encrypted
            existing.target_industry = body.target_industry
            existing.error_message = None
            existing.last_sync_stats = {
                **(existing.last_sync_stats or {}),
                "shop_name": shop.get("name"),
            }
            existing.state = {**(existing.state or {}), **extra_state}
            conn = existing

        await audit.record(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            action="integration.connect",
            entity_type="integration_connection",
            entity_id=PROVIDER,
            new_value={"shop_domain": normalized_domain},
        )

    # Best-effort webhook registration for true real-time (only when a public
    # callback URL + signing secret are configured; otherwise polling covers it).
    if settings.public_webhook_base_url and body.api_secret:
        address = settings.public_webhook_base_url.rstrip("/") + WEBHOOK_PATH
        try:
            async with ShopifyClient(
                normalized_domain,
                body.access_token,
                api_version=settings.shopify_api_version,
                http_client=http,
            ) as client:
                for topic in WEBHOOK_TOPICS:
                    await client.create_webhook(topic, address)
            log.info("shopify.webhook.registered", shop=normalized_domain, address=address)
        except ShopifyError as exc:
            log.warning("shopify.webhook.register_failed", error=str(exc))

    return _to_status(await _load(db, tenant_id))


@router.post("/shopify/sync", status_code=202, response_model=SyncAccepted)
async def shopify_sync(
    body: SyncScope, request: Request, tenant_id: TenantId, user_id: UserId
) -> SyncAccepted:
    db = request.app.state.db
    http = getattr(request.app.state, "http", None)
    settings = get_settings()

    conn = await _load(db, tenant_id)
    if conn is None or conn.status == "disconnected" or not conn.access_token_encrypted:
        raise HTTPException(status_code=400, detail="Shopify is not connected")
    if conn.status == "syncing":
        raise HTTPException(status_code=409, detail="A sync is already running")

    scope = {
        "products": body.sync_products,
        "inventory": body.sync_inventory,
        "orders": body.sync_orders,
    }

    async with db.session(str(tenant_id)) as session:
        await session.execute(
            update(IntegrationConnection)
            .where(
                IntegrationConnection.tenant_id == tenant_id,
                IntegrationConnection.provider == PROVIDER,
            )
            .values(status="syncing", error_message=None)
        )
        await audit.record(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            action="integration.sync",
            entity_type="integration_connection",
            entity_id=PROVIDER,
            new_value=scope,
        )

    asyncio.create_task(_run_sync_task(db, http, tenant_id, scope, settings.shopify_api_version))
    return SyncAccepted(status="syncing", detail="Backfill started")


@router.delete("/shopify", response_model=IntegrationStatus)
async def shopify_disconnect(
    request: Request, tenant_id: TenantId, user_id: UserId
) -> IntegrationStatus:
    db = request.app.state.db
    async with db.session(str(tenant_id)) as session:
        await session.execute(
            update(IntegrationConnection)
            .where(
                IntegrationConnection.tenant_id == tenant_id,
                IntegrationConnection.provider == PROVIDER,
            )
            .values(status="disconnected", access_token_encrypted=None, error_message=None)
        )
        await audit.record(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            action="integration.disconnect",
            entity_type="integration_connection",
            entity_id=PROVIDER,
        )
    return _to_status(await _load(db, tenant_id))


@router.get("/shopify/live", response_model=LiveSalesSummary)
async def shopify_live(request: Request, tenant_id: TenantId) -> LiveSalesSummary:
    """Live sales summary from Shopify-sourced rows: today's totals, a 24h
    hourly sparkline, and the most recent line items."""
    db = request.app.state.db
    conn = await _load(db, tenant_id)
    connected = conn is not None and conn.status in ("connected", "syncing")

    now = datetime.now(tz=UTC)
    start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    since_24h = now - timedelta(hours=24)

    async with db.session(str(tenant_id)) as session:
        today = (
            await session.execute(
                text(
                    """
                    SELECT COALESCE(SUM(units_sold),0) AS units,
                           COALESCE(SUM(gross_revenue),0) AS revenue,
                           COUNT(DISTINCT metadata->>'order_id') AS orders
                    FROM historical_sales
                    WHERE tenant_id = :t
                      AND metadata->>'source' = 'shopify'
                      AND sale_time >= :start
                    """
                ),
                {"t": tenant_id, "start": start_today},
            )
        ).one()

        last_sale = await session.scalar(
            text(
                """
                SELECT MAX(sale_time) FROM historical_sales
                WHERE tenant_id = :t AND metadata->>'source' = 'shopify'
                """
            ),
            {"t": tenant_id},
        )

        hourly_rows = (
            await session.execute(
                text(
                    """
                    SELECT (EXTRACT(EPOCH FROM date_trunc('hour', sale_time))::bigint) AS h,
                           COALESCE(SUM(units_sold),0) AS u
                    FROM historical_sales
                    WHERE tenant_id = :t
                      AND metadata->>'source' = 'shopify'
                      AND sale_time >= :since
                    GROUP BY h
                    """
                ),
                {"t": tenant_id, "since": since_24h},
            )
        ).all()

        recent_rows = (
            await session.execute(
                text(
                    """
                    SELECT hs.sale_time, hs.units_sold, hs.gross_revenue,
                           hs.metadata->>'order_id' AS order_id,
                           s.sku_code, s.description
                    FROM historical_sales hs
                    LEFT JOIN skus s ON s.id = hs.sku_id
                    WHERE hs.tenant_id = :t AND hs.metadata->>'source' = 'shopify'
                    ORDER BY hs.sale_time DESC
                    LIMIT 15
                    """
                ),
                {"t": tenant_id},
            )
        ).all()

    # Build 24 hourly buckets (oldest → newest) keyed by epoch-hour.
    hour_units = {int(r.h): int(r.u) for r in hourly_rows}
    now_hour = int(now.replace(minute=0, second=0, microsecond=0).timestamp())
    sparkline = [hour_units.get(now_hour - 3600 * (23 - i), 0) for i in range(24)]

    recent = [
        LiveSaleRow(
            sale_time=r.sale_time,
            sku_code=r.sku_code,
            description=r.description,
            units=int(r.units_sold),
            revenue=float(r.gross_revenue) if r.gross_revenue is not None else None,
            order_id=r.order_id,
        )
        for r in recent_rows
    ]

    return LiveSalesSummary(
        connected=connected,
        today_units=int(today.units),
        today_revenue=float(today.revenue),
        today_orders=int(today.orders),
        last_sale_at=last_sale,
        sparkline_hourly=sparkline,
        recent=recent,
    )


@router.post("/shopify/webhook")
async def shopify_webhook(request: Request) -> dict:
    """Inbound Shopify webhook (public; verified by HMAC, not a bearer token).

    Shopify signs the raw body with the app's API secret. We resolve the tenant
    from the shop-domain header, verify the signature with the stored secret,
    then ingest the order as a live sale.
    """
    raw = await request.body()
    shop = request.headers.get("X-Shopify-Shop-Domain")
    hmac_header = request.headers.get("X-Shopify-Hmac-Sha256")
    topic = request.headers.get("X-Shopify-Topic", "")
    if not shop:
        raise HTTPException(status_code=400, detail="Missing shop domain")

    db = request.app.state.db
    async with db.session_no_rls() as session:
        conn = await session.scalar(
            select(IntegrationConnection).where(
                IntegrationConnection.provider == PROVIDER,
                IntegrationConnection.shop_domain == shop,
            )
        )
    if conn is None or not conn.access_token_encrypted:
        raise HTTPException(status_code=404, detail="Unknown shop")

    secret_enc = (conn.state or {}).get("webhook_secret_enc")
    secret = decrypt_secret(secret_enc) if secret_enc else None
    if not verify_webhook_hmac(secret or "", raw, hmac_header):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # Replay protection: Shopify retries deliveries and a validly-signed body can
    # be replayed. De-duplicate on the stable per-delivery id so an order is not
    # ingested twice (which would double-count live sales).
    settings = get_settings()
    if settings.webhook_replay_protection_enabled:
        from app.core.webhook_replay import WebhookReplayError, assert_fresh_and_unique

        webhook_id = request.headers.get("X-Shopify-Webhook-Id")
        try:
            await assert_fresh_and_unique(
                getattr(request.app.state, "redis", None),
                provider="shopify",
                delivery_id=webhook_id,
                event_ts=None,  # Shopify has no reliable delivery timestamp header
                max_age_s=settings.webhook_replay_max_age_s,
                dedupe_ttl_s=settings.webhook_replay_dedupe_ttl_s,
            )
        except WebhookReplayError as exc:
            log.info("shopify.webhook.replay_dropped", reason=exc.reason)
            return {"ok": True, "duplicate": True}

    if topic.startswith("orders/"):
        try:
            order = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON body")
        realtime = getattr(request.app.state, "realtime", None)
        await ingest_single_order(
            db=db,
            tenant_id=conn.tenant_id,
            connection=conn,
            order_payload=order,
            realtime=realtime,
        )
    return {"ok": True}


async def _run_sync_task(db, http, tenant_id: uuid.UUID, scope: dict, api_version: str) -> None:
    """Background backfill. Reloads the connection, runs the sync, records result."""
    conn = await _load(db, tenant_id)
    if conn is None:
        return
    try:
        stats = await run_shopify_sync(
            db=db,
            tenant_id=tenant_id,
            connection=conn,
            scope=scope,
            http_client=http,
            api_version=api_version,
        )
        async with db.session(str(tenant_id)) as session:
            await session.execute(
                update(IntegrationConnection)
                .where(
                    IntegrationConnection.tenant_id == tenant_id,
                    IntegrationConnection.provider == PROVIDER,
                )
                .values(
                    status="connected",
                    last_sync_at=datetime.now(tz=UTC),
                    last_sync_status="success",
                    last_sync_stats=stats,
                    error_message=None,
                )
            )
        log.info("shopify.sync.task.ok", tenant=str(tenant_id))
    except Exception as exc:  # noqa: BLE001 - record any failure to the row
        log.error("shopify.sync.task.failed", tenant=str(tenant_id), error=str(exc))
        async with db.session(str(tenant_id)) as session:
            await session.execute(
                update(IntegrationConnection)
                .where(
                    IntegrationConnection.tenant_id == tenant_id,
                    IntegrationConnection.provider == PROVIDER,
                )
                .values(
                    status="error",
                    last_sync_status="error",
                    error_message=str(exc)[:500],
                )
            )
