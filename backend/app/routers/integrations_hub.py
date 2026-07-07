"""Integrations Hub — the catalog of every connectable data source, plus the
generic connect/disconnect and file-upload endpoints.

The Shopify-specific endpoints live in ``integrations.py``; this router adds the
provider-agnostic surface that makes the full catalog available:

    GET    /integrations/catalog              → all providers + per-tenant status
    POST   /integrations/{provider}/connect   → connect or request any provider
    DELETE /integrations/{provider}           → disconnect/forget any provider
    POST   /integrations/upload               → CSV/Excel → canonical schema

Credentials are encrypted at rest (secret fields → ``state.credentials_enc``);
non-secret config is kept in ``state.config``. For ``planned`` providers — the
ones whose sync adapter isn't built yet — connecting records the request
(status ``requested``) so the adapter can be enabled later with zero UI change.
"""

from __future__ import annotations

import asyncio
import hashlib
import secrets
import uuid
from datetime import UTC, datetime
from typing import Annotated

import structlog
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import select, update

from app.connectors import ConnectorAvailability, get_spec, grouped_catalog
from app.core.crypto import decrypt_secret, encrypt_secret
from app.models.enums import IndustryCode
from app.models.integration import IntegrationConnection
from app.routers.industry_router import TenantId, UserId
from app.schemas.integrations import (
    AuthFieldOut,
    CatalogOut,
    CategoryGroupOut,
    ConnectorOut,
    GenericConnectRequest,
    SyncAccepted,
    UploadResult,
)
from app.services import audit
from app.services.integrations import sql_source
from app.services.integrations.file_import import import_rows, parse_table
from app.services.integrations.woocommerce_client import WooCommerceClient, WooCommerceError
from app.services.integrations.woocommerce_sync import run_woocommerce_sync

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/integrations", tags=["integrations"])

# Providers with their own dedicated connect flow (handled elsewhere) or no
# connect step at all (files use the upload endpoint).
_DEDICATED = {"shopify"}
_FILE_PROVIDERS = {"csv_upload", "excel_upload"}
# Direct-SQL providers: connect via the generic flow below, but also support
# an on-demand sync (pull each configured feed query) via /sync.
_SQL_PROVIDERS = {"postgres", "mysql"}
_SYNCABLE_PROVIDERS = {"postgres", "mysql", "woocommerce"}
# Max upload size (10 MiB) — guards memory on the in-process parse.
_MAX_UPLOAD_BYTES = 10 * 1024 * 1024


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def _load_all(db, tenant_id: uuid.UUID) -> dict[str, IntegrationConnection]:
    async with db.session(str(tenant_id)) as session:
        rows = await session.scalars(
            select(IntegrationConnection).where(IntegrationConnection.tenant_id == tenant_id)
        )
        return {c.provider: c for c in rows.all()}


def _to_connector_out(spec, conn: IntegrationConnection | None) -> ConnectorOut:
    status = conn.status if conn else "disconnected"
    return ConnectorOut(
        key=spec.key,
        name=spec.name,
        category=spec.category.value,
        availability=spec.availability.value,
        summary=spec.summary,
        feeds=list(spec.feeds),
        auth_fields=[
            AuthFieldOut(
                key=f.key,
                label=f.label,
                type=f.type,
                required=f.required,
                placeholder=f.placeholder,
                help=f.help,
                options=list(f.options) if f.options else None,
                secret=f.secret,
            )
            for f in spec.auth_fields
        ],
        docs_url=spec.docs_url,
        icon=spec.icon,
        accent=spec.accent,
        status=status,
        connected=status in ("connected", "syncing"),
        last_sync_at=conn.last_sync_at if conn else None,
        last_sync_status=conn.last_sync_status if conn else None,
        error_message=conn.error_message if conn else None,
        supports_sync=spec.key in _SYNCABLE_PROVIDERS,
    )


@router.get("/catalog", response_model=CatalogOut)
async def catalog(request: Request, tenant_id: TenantId) -> CatalogOut:
    """The full connector catalog, grouped by category, with this tenant's
    connection state merged in."""
    conns = await _load_all(request.app.state.db, tenant_id)
    groups: list[CategoryGroupOut] = []
    total = live = connected = 0
    for grp in grouped_catalog():
        out_conns = [_to_connector_out(spec, conns.get(spec.key)) for spec in grp.connectors]
        groups.append(
            CategoryGroupOut(category=grp.category.value, label=grp.label, connectors=out_conns)
        )
        for c in out_conns:
            total += 1
            if c.availability == "live":
                live += 1
            if c.connected:
                connected += 1
    return CatalogOut(groups=groups, total=total, live=live, connected=connected)


@router.post("/{provider}/connect", response_model=ConnectorOut)
async def connect_provider(
    provider: str,
    body: GenericConnectRequest,
    request: Request,
    tenant_id: TenantId,
    user_id: UserId,
) -> ConnectorOut:
    """Connect (or, for not-yet-live providers, request) any catalog provider.

    Secret credential fields are encrypted at rest; non-secret fields are stored
    as plain config. Shopify and file providers are rejected here — they have
    dedicated flows.
    """
    spec = get_spec(provider)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")
    if provider in _DEDICATED:
        raise HTTPException(
            status_code=400, detail="Use POST /integrations/shopify/connect for Shopify"
        )
    if provider in _FILE_PROVIDERS:
        raise HTTPException(
            status_code=400, detail="File sources connect via POST /integrations/upload"
        )

    # Validate required credential fields are present.
    missing = [f.key for f in spec.auth_fields if f.required and not body.credentials.get(f.key)]
    if missing:
        raise HTTPException(
            status_code=400, detail=f"Missing required field(s): {', '.join(missing)}"
        )

    # Direct-SQL providers: need at least one feed query, and the DSN must
    # actually connect — validated live, the same way Shopify checks its token
    # before persisting anything.
    if provider in _SQL_PROVIDERS:
        if not any(body.credentials.get(k) for k in sql_source.FEED_QUERY_KEYS.values()):
            raise HTTPException(
                status_code=400,
                detail="Provide at least one of: " + ", ".join(sql_source.FEED_QUERY_KEYS.values()),
            )
        try:
            await sql_source.validate_connection(provider, body.credentials.get("dsn", ""))
        except sql_source.SqlSourceError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    elif provider == "woocommerce":
        base_url = body.credentials.get("base_url")
        consumer_key = body.credentials.get("consumer_key")
        consumer_secret = body.credentials.get("consumer_secret")
        if not base_url or not consumer_key or not consumer_secret:
            raise HTTPException(status_code=400, detail="Missing WooCommerce credentials")
        try:
            async with WooCommerceClient(base_url, consumer_key, consumer_secret) as client:
                await client.validate_credentials()
        except WooCommerceError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Could not connect: {exc}") from exc

    # Split secret vs config; encrypt secrets.
    secret_keys = {f.key for f in spec.auth_fields if f.secret}
    creds_enc: dict[str, str] = {}
    config: dict[str, str] = {}
    for k, v in body.credentials.items():
        if not v:
            continue
        if k in secret_keys:
            creds_enc[k] = encrypt_secret(v)
        else:
            config[k] = v

    # Push providers (rest_api / webhooks) are immediately usable and get a push
    # token minted; we store only its SHA-256 (used to resolve the tenant on
    # ingest) and return the raw token to the caller ONCE. Planned providers
    # record a connection request for an adapter to be enabled later.
    push_token_plain: str | None = None
    config_extra: dict[str, str] = {}
    if provider in ("rest_api", "webhooks"):
        status = "connected"
        push_token_plain = secrets.token_urlsafe(32)
        config_extra["push_token_sha256"] = _hash_token(push_token_plain)
    elif spec.availability == ConnectorAvailability.live:
        status = "connected"
    else:
        status = "requested"

    state = {"credentials_enc": creds_enc, "config": {**config, **config_extra}}
    db = request.app.state.db
    async with db.session(str(tenant_id)) as session:
        existing = await session.scalar(
            select(IntegrationConnection).where(
                IntegrationConnection.tenant_id == tenant_id,
                IntegrationConnection.provider == provider,
            )
        )
        if existing is None:
            session.add(
                IntegrationConnection(
                    tenant_id=tenant_id,
                    provider=provider,
                    status=status,
                    shop_domain=body.credentials.get("base_url")
                    if provider == "woocommerce"
                    else None,
                    target_industry=body.target_industry,
                    state=state,
                    last_sync_stats={},
                    error_message=None,
                )
            )
        else:
            existing.status = status
            existing.target_industry = body.target_industry
            if provider == "woocommerce":
                existing.shop_domain = body.credentials.get("base_url")
            existing.state = {**(existing.state or {}), **state}
            existing.error_message = None
        await audit.record(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            action="integration.connect",
            entity_type="integration_connection",
            entity_id=provider,
            new_value={"status": status},
        )

    conns = await _load_all(db, tenant_id)
    out = _to_connector_out(spec, conns.get(provider))
    out.push_token = push_token_plain  # one-time reveal; not stored in plaintext
    return out


@router.delete("/{provider}", response_model=ConnectorOut)
async def disconnect_provider(
    provider: str, request: Request, tenant_id: TenantId, user_id: UserId
) -> ConnectorOut:
    spec = get_spec(provider)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")
    if provider in _DEDICATED:
        raise HTTPException(status_code=400, detail="Use DELETE /integrations/shopify for Shopify")

    db = request.app.state.db
    async with db.session(str(tenant_id)) as session:
        existing = await session.scalar(
            select(IntegrationConnection).where(
                IntegrationConnection.tenant_id == tenant_id,
                IntegrationConnection.provider == provider,
            )
        )
        if existing is not None:
            existing.status = "disconnected"
            existing.access_token_encrypted = None
            existing.state = {}
            existing.error_message = None
        await audit.record(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            action="integration.disconnect",
            entity_type="integration_connection",
            entity_id=provider,
        )
    conns = await _load_all(db, tenant_id)
    return _to_connector_out(spec, conns.get(provider))


@router.post("/{provider}/sync", status_code=202, response_model=SyncAccepted)
async def sync_provider(
    provider: str, request: Request, tenant_id: TenantId, user_id: UserId
) -> SyncAccepted:
    """Trigger an on-demand pull for a direct-SQL provider (postgres / mysql).

    Same status machine as the Shopify backfill: ``connected`` → ``syncing`` →
    ``connected`` (success) or ``error``, run as an in-process background task
    since this is IO-bound, not CPU heavy.
    """
    spec = get_spec(provider)
    if spec is None:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")
    if provider not in _SYNCABLE_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"{spec.name} does not support on-demand sync")

    db = request.app.state.db
    conns = await _load_all(db, tenant_id)
    conn = conns.get(provider)
    if conn is None or conn.status == "disconnected":
        raise HTTPException(status_code=400, detail=f"{spec.name} is not connected")
    if conn.status == "syncing":
        raise HTTPException(status_code=409, detail="A sync is already running")

    async with db.session(str(tenant_id)) as session:
        await session.execute(
            update(IntegrationConnection)
            .where(
                IntegrationConnection.tenant_id == tenant_id,
                IntegrationConnection.provider == provider,
            )
            .values(status="syncing", error_message=None)
        )
        await audit.record(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            action="integration.sync",
            entity_type="integration_connection",
            entity_id=provider,
        )

    if provider == "woocommerce":
        asyncio.create_task(_run_woocommerce_sync_task(db, tenant_id))
    else:
        asyncio.create_task(_run_sql_sync_task(db, tenant_id, provider))
    return SyncAccepted(status="syncing", detail="Sync started")


async def _run_woocommerce_sync_task(db, tenant_id: uuid.UUID) -> None:
    """Background sync for a WooCommerce connection."""
    conns = await _load_all(db, tenant_id)
    conn = conns.get("woocommerce")
    if conn is None:
        return
    try:
        stats = await run_woocommerce_sync(db=db, tenant_id=tenant_id, connection=conn)
        async with db.session(str(tenant_id)) as session:
            await session.execute(
                update(IntegrationConnection)
                .where(
                    IntegrationConnection.tenant_id == tenant_id,
                    IntegrationConnection.provider == "woocommerce",
                )
                .values(
                    status="connected",
                    last_sync_at=datetime.now(tz=UTC),
                    last_sync_status="success",
                    last_sync_stats=stats,
                    error_message=None,
                )
            )
        log.info("woocommerce.sync.task.ok", tenant=str(tenant_id))
    except Exception as exc:  # noqa: BLE001 - record any failure
        log.error("woocommerce.sync.task.failed", tenant=str(tenant_id), error=str(exc))
        async with db.session(str(tenant_id)) as session:
            await session.execute(
                update(IntegrationConnection)
                .where(
                    IntegrationConnection.tenant_id == tenant_id,
                    IntegrationConnection.provider == "woocommerce",
                )
                .values(status="error", last_sync_status="error", error_message=str(exc)[:500])
            )


async def _run_sql_sync_task(db, tenant_id: uuid.UUID, provider: str) -> None:
    """Background pull for a direct-SQL connection. Reloads the connection,
    runs the sync, records the result — mirrors Shopify's `_run_sync_task`."""
    conns = await _load_all(db, tenant_id)
    conn = conns.get(provider)
    if conn is None:
        return
    try:
        creds_enc = (conn.state or {}).get("credentials_enc", {})
        config = (conn.state or {}).get("config", {})
        dsn_enc = creds_enc.get("dsn")
        if not dsn_enc:
            raise sql_source.SqlSourceError("No connection string stored for this connection")
        dsn = decrypt_secret(dsn_enc)
        queries = {key: config.get(key) for key in sql_source.FEED_QUERY_KEYS.values()}
        industry = (
            conn.target_industry
            if isinstance(conn.target_industry, IndustryCode)
            else IndustryCode(conn.target_industry)
        )
        stats = await sql_source.run_sql_sync(
            db=db,
            tenant_id=tenant_id,
            provider=provider,
            industry=industry,
            dsn=dsn,
            queries=queries,
        )
        async with db.session(str(tenant_id)) as session:
            await session.execute(
                update(IntegrationConnection)
                .where(
                    IntegrationConnection.tenant_id == tenant_id,
                    IntegrationConnection.provider == provider,
                )
                .values(
                    status="connected",
                    last_sync_at=datetime.now(tz=UTC),
                    last_sync_status="success",
                    last_sync_stats=stats,
                    error_message=None,
                )
            )
        log.info("sql_source.sync.task.ok", provider=provider, tenant=str(tenant_id))
    except Exception as exc:  # noqa: BLE001 - record any failure to the row
        log.error(
            "sql_source.sync.task.failed", provider=provider, tenant=str(tenant_id), error=str(exc)
        )
        async with db.session(str(tenant_id)) as session:
            await session.execute(
                update(IntegrationConnection)
                .where(
                    IntegrationConnection.tenant_id == tenant_id,
                    IntegrationConnection.provider == provider,
                )
                .values(status="error", last_sync_status="error", error_message=str(exc)[:500])
            )


@router.post("/upload", response_model=UploadResult)
async def upload_file(
    request: Request,
    tenant_id: TenantId,
    user_id: UserId,
    file: Annotated[UploadFile, File()],
    kind: Annotated[str, Form()],
    target_industry: Annotated[str, Form()],
) -> UploadResult:
    """Upload a CSV/Excel file of sales, inventory, or products and ingest it
    into the canonical schema."""
    if kind not in ("sales", "inventory", "products"):
        raise HTTPException(status_code=400, detail="kind must be sales, inventory, or products")
    try:
        industry = IndustryCode(target_industry)
    except ValueError:
        raise HTTPException(
            status_code=400, detail=f"Unknown industry: {target_industry}"
        ) from None

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(content) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds the 10 MB limit")

    try:
        headers, records = parse_table(file.filename or "", content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not records:
        raise HTTPException(status_code=400, detail="No data rows found in the file")

    db = request.app.state.db
    try:
        stats = await import_rows(
            db=db,
            tenant_id=tenant_id,
            industry=industry,
            kind=kind,
            headers=headers,
            records=records,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    provider = (
        "excel_upload"
        if (file.filename or "").lower().endswith((".xlsx", ".xlsm"))
        else "csv_upload"
    )

    # Record the upload as a connection so the Hub shows it as "connected" with
    # last-sync stats, and write an audit entry.
    async with db.session(str(tenant_id)) as session:
        existing = await session.scalar(
            select(IntegrationConnection).where(
                IntegrationConnection.tenant_id == tenant_id,
                IntegrationConnection.provider == provider,
            )
        )
        sync_stats = {k: v for k, v in stats.items() if isinstance(v, int)}
        if existing is None:
            session.add(
                IntegrationConnection(
                    tenant_id=tenant_id,
                    provider=provider,
                    status="connected",
                    target_industry=industry,
                    last_sync_at=datetime.now(tz=UTC),
                    last_sync_status="success",
                    last_sync_stats=sync_stats,
                    state={},
                )
            )
        else:
            existing.status = "connected"
            existing.target_industry = industry
            existing.last_sync_at = datetime.now(tz=UTC)
            existing.last_sync_status = "success"
            existing.last_sync_stats = sync_stats
        await audit.record(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            action="integration.upload",
            entity_type="integration_connection",
            entity_id=provider,
            new_value={"kind": kind, "rows": stats["rows_imported"]},
        )

    return UploadResult(provider=provider, kind=kind, **stats)


# ── Generic push ingest (rest_api / webhooks) ────────────────────────────────
def _extract_events(payload: object) -> list[dict]:
    """Accept a single event, {"events": [...]}, or a top-level list."""
    if isinstance(payload, list):
        return [e for e in payload if isinstance(e, dict)]
    if isinstance(payload, dict):
        if isinstance(payload.get("events"), list):
            return [e for e in payload["events"] if isinstance(e, dict)]
        return [payload]
    return []


@router.post("/ingest")
async def ingest_push(request: Request) -> dict:
    """Token-authenticated canonical sale-event ingest for the rest_api /
    webhooks connectors.

    Auth: send the push token from the connect step as ``X-Sanket-Token: <token>``
    or ``Authorization: Bearer <token>``. The token's SHA-256 resolves the
    tenant + connection, so this endpoint is public (no session cookie/JWT).

    Body (single object, ``{"events": [...]}``, or a JSON array) of canonical
    events::

        {"sku": "SKU001", "quantity": 2, "revenue": 2500,
         "timestamp": "2026-06-15T14:20:00Z", "channel": "pos"}
    """
    from app.realtime.events import EVENT_SALE_CREATED, RealtimeEvent
    from app.services.integrations import file_import as fi

    token = request.headers.get("X-Sanket-Token") or ""
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing push token")

    token_hash = _hash_token(token)
    db = request.app.state.db
    async with db.session_no_rls() as session:
        conn = await session.scalar(
            select(IntegrationConnection).where(
                IntegrationConnection.provider.in_(("rest_api", "webhooks")),
                IntegrationConnection.status == "connected",
                IntegrationConnection.state["config"]["push_token_sha256"].astext == token_hash,
            )
        )
    if conn is None:
        raise HTTPException(status_code=401, detail="Invalid push token")

    try:
        payload = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc
    events = _extract_events(payload)
    if not events:
        raise HTTPException(status_code=400, detail="No events in payload")

    tenant_id = conn.tenant_id
    industry = (
        conn.target_industry.value
        if hasattr(conn.target_industry, "value")
        else str(conn.target_industry)
    )
    industry_enum = IndustryCode(industry)
    accepted = 0
    skipped = 0
    units = 0
    revenue = 0.0

    async with db.session(str(tenant_id)) as session:
        import_product_id = await fi._ensure_import_product(session, tenant_id, industry_enum)
        sku_map = await fi._load_sku_map(session, tenant_id)
        for ev in events:
            sku = str(ev.get("sku") or ev.get("sku_code") or "").strip()
            qty = fi._to_int(ev.get("quantity") or ev.get("units") or ev.get("qty"))
            if not sku or qty is None or qty <= 0:
                skipped += 1
                continue
            when = fi._to_datetime(ev.get("timestamp") or ev.get("date")) or datetime.now(tz=UTC)
            if not (fi._MIN_SALE_DATE <= when.date() <= fi._max_sale_date()):
                skipped += 1
                continue
            rev = fi._to_decimal(ev.get("revenue") or ev.get("amount"))
            sku_id = await fi._get_or_create_sku(
                session, tenant_id, industry_enum, sku, sku_map, import_product_id
            )
            session.add(
                fi.HistoricalSale(
                    tenant_id=tenant_id,
                    sku_id=sku_id,
                    industry=industry_enum,
                    sale_time=when,
                    channel=str(ev.get("channel") or conn.provider),
                    region=(str(ev.get("region")) if ev.get("region") else None),
                    units_sold=qty,
                    gross_revenue=rev,
                    net_revenue=rev,
                    metadata_={"source": conn.provider, "order_id": ev.get("order_id")},
                )
            )
            accepted += 1
            units += qty
            revenue += float(rev) if rev is not None else 0.0

    # Best-effort live event so dashboards update in real time.
    realtime = getattr(request.app.state, "realtime", None)
    if realtime is not None and units > 0:
        try:
            await realtime.publish(
                RealtimeEvent(
                    type=EVENT_SALE_CREATED,
                    tenant_id=tenant_id,
                    industry=industry,
                    data={"orders": accepted, "units": units, "revenue": round(revenue, 2)},
                )
            )
        except Exception as exc:  # noqa: BLE001 - realtime is best-effort
            log.warning("ingest.realtime.publish_failed", error=str(exc))

    log.info(
        "integrations.ingest",
        provider=conn.provider,
        tenant=str(tenant_id),
        accepted=accepted,
        skipped=skipped,
    )
    return {"ok": True, "accepted": accepted, "skipped": skipped}
