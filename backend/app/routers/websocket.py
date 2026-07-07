"""WebSocket endpoint for real-time tenant event stream.

Auth: browsers can't set Authorization headers on WS handshakes, so we
accept the bearer token (Firebase ID token or dev token) as a `token` query
parameter. The same verification logic as the HTTP middleware is reused.
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from starlette.concurrency import run_in_threadpool

from app.core.firebase_auth import TokenVerificationError, get_verifier
from app.realtime import get_connection_manager
from app.realtime.events import RealtimeEvent

log = structlog.get_logger(__name__)
router = APIRouter()


@router.websocket("/ws")
async def realtime_stream(websocket: WebSocket, token: str = Query(...)) -> None:
    try:
        identity = await run_in_threadpool(get_verifier().verify, token)
    except TokenVerificationError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="invalid token")
        return

    try:
        tenant_id = uuid.UUID(identity["tid"])
        user_id = uuid.UUID(identity["puid"])
    except (KeyError, ValueError):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="invalid token")
        return
    manager = get_connection_manager()
    await manager.connect(websocket, tenant_id)

    # Hello frame so the client knows the connection is live
    await websocket.send_json(
        RealtimeEvent(
            type="connection.ready",
            tenant_id=tenant_id,
            data={"user_id": str(user_id), "industry": identity.get("ind")},
        ).to_wire()
    )

    try:
        while True:
            # We don't currently accept inbound messages, but we need to await
            # something so the connection stays open and we observe disconnects.
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        log.info("ws.client_disconnected", tenant=str(tenant_id))
    except Exception as exc:
        log.warning("ws.error", tenant=str(tenant_id), error=str(exc))
    finally:
        await manager.disconnect(websocket, tenant_id)
