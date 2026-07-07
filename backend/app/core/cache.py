"""Redis-backed response cache for read-heavy, tenant-scoped GET endpoints.

Dashboard endpoints (sales analytics, etc.) are polled repeatedly and recompute
the same aggregates over slowly-changing data. This module caches the JSON
response in Redis for a short TTL.

Design notes
------------
* **Tenant + params scoping.** The cache key is
  ``rc:{tenant}:{version}:{name}:{digest(params)}`` so two tenants — or two
  different query parameterisations — never collide. Combined with RLS this is
  defence in depth: a key can only ever be produced for the tenant in scope.

* **Version-bump invalidation.** Rather than tracking and deleting every key a
  tenant might have produced (impossible without a key scan), each tenant has a
  monotonic ``version`` counter embedded in its keys. A mutating request calls
  :meth:`ResponseCache.invalidate_tenant`, which ``INCR``s that counter; all
  previously-cached keys are instantly unreachable and age out by TTL. This is
  O(1) and correct under concurrency.

* **Fail-open / no-Redis.** When Redis is absent or unavailable, every method
  degrades to "compute, don't cache" — identical behaviour to before this layer
  existed. The cache is never load-bearing for correctness.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

log = structlog.get_logger(__name__)

_PREFIX = "rc"  # response-cache namespace


class ResponseCache:
    """Thin async wrapper over a Redis client (or ``None`` for a no-op cache)."""

    def __init__(self, redis: Any | None, *, enabled: bool = True) -> None:
        # ``enabled`` lets config switch the whole layer off without removing Redis.
        self._redis = redis if enabled else None

    @property
    def enabled(self) -> bool:
        return self._redis is not None

    # ── key helpers ───────────────────────────────────────────────────────────
    @staticmethod
    def _version_key(tenant_id: str) -> str:
        return f"{_PREFIX}:ver:{tenant_id}"

    @staticmethod
    def _digest(params: dict[str, Any]) -> str:
        raw = json.dumps(params, sort_keys=True, default=str)
        return hashlib.blake2b(raw.encode("utf-8"), digest_size=12).hexdigest()

    async def _version(self, tenant_id: str) -> str:
        if self._redis is None:
            return "0"
        try:
            v = await self._redis.get(self._version_key(tenant_id))
            return v if v is not None else "0"
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("cache.version.error", error=str(exc))
            return "0"

    # ── public API ────────────────────────────────────────────────────────────
    async def get_or_set(
        self,
        *,
        tenant_id: Any,
        name: str,
        params: dict[str, Any],
        ttl_s: int,
        producer: Callable[[], Awaitable[Any]],
    ) -> Any:
        """Return the cached value for ``(tenant, name, params)`` or compute it.

        ``producer`` is an async callable that performs the expensive work (the
        DB query) on a cache miss; its JSON-serialisable result is cached for
        ``ttl_s`` seconds and returned.
        """
        tenant = str(tenant_id)
        if self._redis is None:
            return await producer()

        version = await self._version(tenant)
        key = f"{_PREFIX}:{tenant}:{version}:{name}:{self._digest(params)}"

        try:
            cached = await self._redis.get(key)
            if cached is not None:
                return json.loads(cached)
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("cache.get.error", name=name, error=str(exc))

        value = await producer()

        try:
            await self._redis.set(key, json.dumps(value, default=str), ex=ttl_s)
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("cache.set.error", name=name, error=str(exc))
        return value

    async def invalidate_tenant(self, tenant_id: Any) -> None:
        """Invalidate every cached entry for a tenant in O(1) by bumping its
        version counter. Safe to call on the write path — fail-open on error."""
        if self._redis is None:
            return
        try:
            await self._redis.incr(self._version_key(str(tenant_id)))
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("cache.invalidate.error", error=str(exc))


def get_response_cache(request: Any) -> ResponseCache:
    """Build a :class:`ResponseCache` bound to the app's shared Redis client.

    Reads ``api_cache_enabled`` from settings so the layer can be globally
    disabled, and tolerates a missing Redis (returns a no-op cache).
    """
    from app.config import get_settings

    state = getattr(request.app, "state", None)
    redis = getattr(state, "redis", None)
    return ResponseCache(redis, enabled=get_settings().api_cache_enabled)
