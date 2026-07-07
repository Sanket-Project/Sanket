"""Token-bucket rate limit per client IP.

Strategy:
  • If Redis is available (REDIS_URL is set and reachable): use a Redis
    sliding-window counter (INCR + EXPIRE) so the limit is shared across
    all replicas — correct for multi-instance deployments.
  • Otherwise: fall back to the in-process token-bucket below. This is
    acceptable for single-node dev environments but will under-enforce in
    multi-replica prod.  A startup log line clearly states which mode is
    active so operators are not surprised.
"""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Awaitable, Callable

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Redis sliding-window implementation
# ---------------------------------------------------------------------------


# Atomic check-and-increment, evaluated server-side in ONE round trip.
#   - INCR the window counter; on the first hit, set its TTL.
#   - If over the limit, return the remaining TTL (>=1) as Retry-After.
#   - Otherwise return 0 (allowed).
# The previous Python implementation issued up to three sequential commands
# (INCR, EXPIRE, TTL) — three network round trips on the hot path of *every*
# API request. Folding them into a Lua script cuts that to one, and removes the
# INCR/EXPIRE race where a crash between the two could leave a key with no TTL.
_RATE_LIMIT_LUA = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
if count > tonumber(ARGV[2]) then
    local ttl = redis.call('TTL', KEYS[1])
    if ttl < 1 then ttl = 1 end
    return ttl
end
return 0
"""


async def _redis_is_limited(script, key: str, limit: int, window_s: int = 60) -> tuple[bool, int]:
    """Run the atomic rate-limit script. Returns (is_limited, retry_after_seconds).

    ``script`` is a registered ``AsyncScript`` (EVALSHA with automatic EVAL
    fallback). Fails open (allow) if Redis is briefly unavailable.
    """
    try:
        ttl = int(await script(keys=[key], args=[window_s, limit]))
        if ttl == 0:
            return False, 0
        return True, ttl
    except Exception as exc:
        # Redis temporarily unavailable — fail open (allow request) and log
        log.warning("rate_limit.redis.error", error=str(exc))
        return False, 0


# ---------------------------------------------------------------------------
# In-process token-bucket (fallback)
# ---------------------------------------------------------------------------


class _InProcessBucket:
    """Thread-safe-enough token bucket for single-process dev use."""

    def __init__(self, per_minute: int, burst: int | None) -> None:
        self._capacity = burst or per_minute
        self._refill_rate = per_minute / 60.0  # tokens / second
        self._buckets: dict[str, tuple[float, float]] = defaultdict(
            lambda: (self._capacity, time.monotonic())
        )

    def is_limited(self, client_ip: str) -> tuple[bool, int]:
        tokens, last = self._buckets[client_ip]
        now = time.monotonic()
        tokens = min(self._capacity, tokens + (now - last) * self._refill_rate)
        if tokens < 1.0:
            retry_after = int((1.0 - tokens) / self._refill_rate) + 1
            return True, retry_after
        self._buckets[client_ip] = (tokens - 1.0, now)
        return False, 0


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


def client_ip_from_request(request: Request, trusted_proxy_count: int) -> str:
    """Resolve the real client IP, accounting for trusted reverse proxies.

    ``X-Forwarded-For`` is a client-controllable header: a caller can prepend
    fake entries to dodge per-IP limits. We therefore trust only the last
    ``trusted_proxy_count`` hops and take the entry immediately to their left.
    When ``trusted_proxy_count`` is 0 we ignore the header entirely and use the
    socket peer.
    """
    peer = request.client.host if request.client else "unknown"
    if trusted_proxy_count <= 0:
        return peer
    forwarded = request.headers.get("X-Forwarded-For", "")
    if not forwarded:
        return peer
    chain = [p.strip() for p in forwarded.split(",") if p.strip()]
    if not chain:
        return peer
    # Rightmost entries are appended by infrastructure we control; index back
    # past the trusted hops to the first attacker-controllable value.
    idx = len(chain) - trusted_proxy_count
    if idx < 0:
        idx = 0
    return chain[idx]


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        *,
        per_minute: int = 600,
        burst: int | None = None,
        trusted_proxy_count: int = 1,
    ) -> None:
        super().__init__(app)
        self._per_minute = per_minute
        self._burst = burst
        self._trusted_proxy_count = trusted_proxy_count
        self._fallback = _InProcessBucket(per_minute, burst)
        self._redis_client = None  # resolved on first request via app.state
        self._rl_script = None  # registered AsyncScript, built once Redis is known

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Skip non-API and health/metrics paths
        path = request.url.path
        if not path.startswith("/api/") or path.endswith(("/health", "/metrics")):
            return await call_next(request)

        client_ip = client_ip_from_request(request, self._trusted_proxy_count)

        # Lazy-resolve Redis from app.state (set in lifespan if redis_url is configured)
        if self._redis_client is None:
            self._redis_client = getattr(
                getattr(request, "app", None),
                "state",
                type("_s", (), {"redis": None})(),
            ).redis  # may still be None

        limited = False
        retry_after = 0

        if self._redis_client is not None:
            if self._rl_script is None:
                # register_script gives an EVALSHA-first callable that falls back
                # to EVAL on NOSCRIPT, so the script body is sent at most once.
                self._rl_script = self._redis_client.register_script(_RATE_LIMIT_LUA)
            key = f"rl:{client_ip}"
            limited, retry_after = await _redis_is_limited(self._rl_script, key, self._per_minute)
        else:
            limited, retry_after = self._fallback.is_limited(client_ip)

        if limited:
            log.warning("rate_limit.exceeded", ip=client_ip, path=path)
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded"},
                headers={"Retry-After": str(retry_after)},
            )

        return await call_next(request)
