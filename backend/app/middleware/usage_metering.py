"""Records one `api_request` usage event per authenticated request.

Cheap-path optimization: writes are batched in-memory and flushed every N
events or T seconds via a background task, so we don't add a DB round-trip
on every request.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.models.billing import MeterKind

log = structlog.get_logger(__name__)

# Path prefixes that should NOT count toward billable API usage
_FREE_PATHS = ("/health", "/metrics", "/", "/docs", "/redoc", "/openapi.json", "/ws")


class UsageMeteringMiddleware(BaseHTTPMiddleware):
    """Buffer per-tenant API request counts, flush periodically."""

    def __init__(
        self,
        app,
        *,
        flush_every: int = 100,
        flush_interval_s: float = 10.0,
    ) -> None:
        super().__init__(app)
        self._buffer: dict[uuid.UUID, int] = defaultdict(int)
        self._lock = asyncio.Lock()
        self._flush_every = flush_every
        self._flush_interval_s = flush_interval_s
        self._last_flush_t = time.monotonic()

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        tenant_id = getattr(request.state, "tenant_id", None)
        if tenant_id is None or request.url.path in _FREE_PATHS:
            return response
        if any(request.url.path.startswith(p) for p in _FREE_PATHS):
            return response

        async with self._lock:
            self._buffer[tenant_id] += 1
            total = sum(self._buffer.values())
            elapsed = time.monotonic() - self._last_flush_t

        if total >= self._flush_every or elapsed >= self._flush_interval_s:
            asyncio.create_task(self._flush(request.app))
        return response

    async def _flush(self, app) -> None:
        async with self._lock:
            if not self._buffer:
                return
            snapshot = dict(self._buffer)
            self._buffer.clear()
            self._last_flush_t = time.monotonic()

        db = getattr(app.state, "db", None)
        if db is None:
            return
        from app.services.usage import record  # avoid circular import

        try:
            for tid, count in snapshot.items():
                async with db.session(str(tid)) as session:
                    await record(
                        session,
                        tenant_id=tid,
                        meter=MeterKind.api_request,
                        quantity=count,
                        metadata={"batched": True},
                    )
        except Exception as exc:
            log.error("usage.flush.failed", error=str(exc))
