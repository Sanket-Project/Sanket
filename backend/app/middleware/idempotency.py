"""Request idempotency middleware.

A client (or a proxy / load balancer / the browser's own retry) can send the
same mutating request twice — a dropped response, a timeout-then-retry, a
double-click. Without protection that means two subscriptions, two webhooks
registered, two of whatever the POST creates.

Contract (mirrors Stripe's ``Idempotency-Key``):

* Applies only to mutating methods (POST/PUT/PATCH/DELETE) carrying an
  ``Idempotency-Key`` header. Everything else passes straight through.
* The first request for a key executes normally; its status + body are cached
  in Redis under a tenant-scoped key for ``idempotency_ttl_s``.
* A retry with the same key replays the cached response verbatim and never
  re-executes the handler — the client gets the original result with an
  ``Idempotency-Replayed: true`` header.
* A concurrent in-flight retry (original still running) gets ``409`` so it does
  not race the original.
* The key is scoped by ``tenant_id + method + path`` so the same key can never
  cross tenants or be reused to short-circuit a different endpoint.

Requires Redis to share state across replicas. With no Redis the middleware is
a transparent pass-through (single-node dev) — and that is logged at startup
via the rate-limit mode line, since both share the same Redis client.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.responses import Response as StarletteResponse

log = structlog.get_logger(__name__)

_MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})
# Max response body we are willing to cache (bytes). Larger responses skip the
# cache (still execute once, just not replayable) to bound Redis memory.
_MAX_CACHED_BODY = 256 * 1024


class IdempotencyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, ttl_s: int = 86_400, enabled: bool = True) -> None:
        super().__init__(app)
        self._ttl_s = ttl_s
        self._enabled = enabled

    def _redis(self, request: Request):
        return getattr(getattr(request, "app", None), "state", None) and request.app.state.redis

    @staticmethod
    def _cache_key(request: Request, idem_key: str) -> str:
        tenant = getattr(request.state, "tenant_id", None)
        raw = f"{tenant}:{request.method}:{request.url.path}:{idem_key}"
        digest = hashlib.sha256(raw.encode()).hexdigest()
        return f"sanket:idem:{digest}"

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        idem_key = request.headers.get("Idempotency-Key")
        if not self._enabled or request.method not in _MUTATING or not idem_key:
            return await call_next(request)

        redis = self._redis(request)
        if redis is None:
            # No shared store — cannot guarantee idempotency across replicas.
            return await call_next(request)

        cache_key = self._cache_key(request, idem_key)

        # Claim the key: SET NX with a short "in-progress" sentinel. If it already
        # exists we either have a finished result to replay or an in-flight twin.
        try:
            claimed = await redis.set(cache_key, "__in_progress__", nx=True, ex=self._ttl_s)
        except Exception as exc:
            log.warning("idempotency.redis_error", error=str(exc))
            return await call_next(request)

        if not claimed:
            try:
                stored = await redis.get(cache_key)
            except Exception:
                stored = None
            if stored in (None, "__in_progress__"):
                return JSONResponse(
                    status_code=409,
                    content={
                        "detail": "A request with this Idempotency-Key is already in progress"
                    },
                )
            return self._replay(stored)

        # We own the key — execute exactly once, then cache the result.
        response = await call_next(request)
        body = await self._read_body(response)

        if len(body) <= _MAX_CACHED_BODY and response.status_code < 500:
            payload = json.dumps(
                {
                    "status": response.status_code,
                    "headers": {
                        k: v for k, v in response.headers.items() if k.lower() in ("content-type",)
                    },
                    "body": body.decode("latin-1"),
                }
            )
            try:
                await redis.set(cache_key, payload, ex=self._ttl_s)
            except Exception as exc:
                log.warning("idempotency.store_error", error=str(exc))
        else:
            # Don't cache 5xx or oversized bodies — let the client legitimately
            # retry. Drop the in-progress sentinel so the retry isn't a false 409.
            try:
                await redis.delete(cache_key)
            except Exception:
                pass

        return self._rebuild(response, body)

    @staticmethod
    async def _read_body(response: Response) -> bytes:
        chunks = [section async for section in response.body_iterator]  # type: ignore[attr-defined]
        return b"".join(c if isinstance(c, bytes) else c.encode("utf-8") for c in chunks)

    @staticmethod
    def _rebuild(response: Response, body: bytes) -> Response:
        return StarletteResponse(
            content=body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )

    @staticmethod
    def _replay(stored: str) -> Response:
        try:
            data = json.loads(stored)
        except (ValueError, TypeError):
            return JSONResponse(status_code=409, content={"detail": "Idempotency conflict"})
        headers = dict(data.get("headers", {}))
        headers["Idempotency-Replayed"] = "true"
        return StarletteResponse(
            content=data["body"].encode("latin-1"),
            status_code=data["status"],
            headers=headers,
        )
