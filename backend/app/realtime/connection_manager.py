"""WebSocket connection registry with Redis pub/sub fan-out.

Single-replica deployments degrade to an in-process broadcast only.
Multi-replica deployments need Redis (configured via REDIS_URL) so events
fired in pod A reach subscribers connected to pod B.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections import defaultdict

import structlog
from fastapi import WebSocket

from app.realtime.events import RealtimeEvent

log = structlog.get_logger(__name__)


class ConnectionManager:
    def __init__(self, redis_url: str | None = None) -> None:
        self._connections: dict[uuid.UUID, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()
        self._redis_url = redis_url
        self._redis = None
        self._pubsub_task: asyncio.Task | None = None

    # ── lifecycle ─────────────────────────────────────────────────────────
    async def startup(self) -> None:
        if not self._redis_url:
            log.info("realtime.redis.disabled", reason="REDIS_URL unset; using in-process only")
            return
        try:
            import redis.asyncio as redis  # type: ignore
        except ImportError:
            log.warning(
                "realtime.redis.import_failed", msg="pip install redis>=5 for multi-replica fan-out"
            )
            return
        self._redis = redis.from_url(self._redis_url, decode_responses=True)
        # Single global subscriber that filters by tenant locally
        self._pubsub_task = asyncio.create_task(self._consume_redis())
        log.info("realtime.redis.connected", url=self._redis_url.split("@")[-1])

    async def connect_publisher(self) -> None:
        """Attach a Redis client for publish-only use (no local WS consumer).

        Used by out-of-process workers (e.g. the arq forecast worker) that emit
        events to be fanned out by the API replicas, but hold no WebSocket
        connections of their own and so must not start a consumer loop.
        """
        if not self._redis_url or self._redis is not None:
            return
        try:
            import redis.asyncio as redis  # type: ignore
        except ImportError:
            log.warning("realtime.redis.import_failed", msg="pip install redis>=5 for fan-out")
            return
        self._redis = redis.from_url(self._redis_url, decode_responses=True)
        log.info("realtime.redis.publisher_attached")

    async def shutdown(self) -> None:
        if self._pubsub_task:
            self._pubsub_task.cancel()
        if self._redis:
            await self._redis.close()
        async with self._lock:
            for sockets in self._connections.values():
                for ws in list(sockets):
                    try:
                        await ws.close()
                    except Exception:
                        pass
            self._connections.clear()
        log.info("realtime.shutdown.complete")

    # ── connection registry ───────────────────────────────────────────────
    async def connect(self, ws: WebSocket, tenant_id: uuid.UUID) -> None:
        await ws.accept()
        async with self._lock:
            self._connections[tenant_id].add(ws)
        log.info("realtime.connect", tenant=str(tenant_id), total=len(self._connections[tenant_id]))

    async def disconnect(self, ws: WebSocket, tenant_id: uuid.UUID) -> None:
        async with self._lock:
            self._connections[tenant_id].discard(ws)
            if not self._connections[tenant_id]:
                del self._connections[tenant_id]
        log.info("realtime.disconnect", tenant=str(tenant_id))

    def connection_count(self, tenant_id: uuid.UUID | None = None) -> int:
        if tenant_id:
            return len(self._connections.get(tenant_id, set()))
        return sum(len(s) for s in self._connections.values())

    # ── publish ───────────────────────────────────────────────────────────
    async def publish(self, event: RealtimeEvent) -> None:
        """Send to all local subscribers + fan out via Redis to peers."""
        await self._broadcast_local(event)
        if self._redis:
            try:
                await self._redis.publish(event.channel(), json.dumps(event.to_wire(), default=str))
            except Exception as exc:
                log.error("realtime.redis.publish_failed", error=str(exc))

    async def _broadcast_local(self, event: RealtimeEvent) -> None:
        sockets = list(self._connections.get(event.tenant_id, set()))
        if not sockets:
            return
        payload = event.to_wire()
        results = await asyncio.gather(
            *(self._safe_send(ws, payload) for ws in sockets),
            return_exceptions=True,
        )
        for ws, ok in zip(sockets, results, strict=False):
            if isinstance(ok, Exception) or ok is False:
                await self.disconnect(ws, event.tenant_id)

    @staticmethod
    async def _safe_send(ws: WebSocket, payload: dict) -> bool:
        try:
            await ws.send_json(payload)
            return True
        except Exception:
            return False

    async def _consume_redis(self) -> None:
        assert self._redis is not None
        pubsub = self._redis.pubsub()
        # Subscribe to all tenant channels via pattern
        await pubsub.psubscribe("sanket:tenant:*")
        log.info("realtime.redis.psubscribed")
        try:
            async for msg in pubsub.listen():
                if msg.get("type") != "pmessage":
                    continue
                try:
                    data = json.loads(msg["data"])
                    event = RealtimeEvent.model_validate(data)
                except Exception as exc:
                    log.warning("realtime.redis.decode_failed", error=str(exc))
                    continue
                await self._broadcast_local(event)
        except asyncio.CancelledError:
            log.info("realtime.redis.consumer_cancelled")
            raise


_GLOBAL_MANAGER: ConnectionManager | None = None


def get_connection_manager(redis_url: str | None = None) -> ConnectionManager:
    global _GLOBAL_MANAGER
    if _GLOBAL_MANAGER is None:
        _GLOBAL_MANAGER = ConnectionManager(redis_url=redis_url)
    return _GLOBAL_MANAGER
