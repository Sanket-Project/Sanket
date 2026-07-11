"""Three-tier rate limiting per IP, per authenticated user, and per heavy endpoint.

Architecture — two middleware instances, not one
-------------------------------------------------
The three buckets run in two separate registered middleware instances to solve
an ordering constraint:

  ┌─ Outermost ─────────────────────────────────────────────────────────────┐
  │  RateLimitMiddleware(ip_only=True)                                       │
  │  Bucket 1 — per-IP (600/min). Runs BEFORE TenantContextMiddleware so    │
  │  unauthenticated floods are dropped before any Firebase token verification│
  │  occurs. Failing this check before auth is critical: with               │
  │  firebase_check_revoked=True, every unauthenticated request would        │
  │  otherwise trigger a Firebase round-trip — a DoS amplifier.             │
  │  Fails OPEN on Redis error (a blip should not kill all API traffic).     │
  └──────────────────────────────────────────────────────────────────────────┘
        ↓  (only requests that pass the IP gate reach here)
  ┌─ TenantContextMiddleware ────────────────────────────────────────────────┐
  │  Verifies Firebase token; populates request.state.user_id / tenant_id    │
  └──────────────────────────────────────────────────────────────────────────┘
        ↓  (request.state.user_id is NOW populated)
  ┌─ RateLimitMiddleware(ip_only=False) ────────────────────────────────────┐
  │  Bucket 2 — per-user (300/min). Fails OPEN on Redis error.              │
  │  Bucket 3 — heavy-endpoint (30/min for /forecasts, /export, etc.).      │
  │             Fails CLOSED (503) on Redis error — a Redis outage during   │
  │             high load is when ML/DB protection matters most.             │
  └──────────────────────────────────────────────────────────────────────────┘
        ↓
  Route handler

Registration order in main.py (innermost → outermost via add_middleware):
  1. IdempotencyMiddleware                      (innermost)
  2. RateLimitMiddleware(ip_only=False)   ← NEW, just inside TenantContext
  3. TenantContextMiddleware
  4. RegionRouterMiddleware
  5. UsageMeteringMiddleware
  6. RateLimitMiddleware(ip_only=True)    ← EXISTING, outermost rate gate
  7. SecurityHeadersMiddleware
  8. CORSMiddleware                             (outermost)

Why this avoids the DoS amplifier problem
------------------------------------------
ip_only=True (position 6) runs before Firebase token verification (position 3).
An unauthenticated flood is therefore dropped at IP cost — no Firebase calls.
ip_only=False (position 2) runs after Firebase has authenticated the caller, so
request.state.user_id is guaranteed to be populated for authenticated requests.
Unauthenticated requests (public paths) still reach position 2 but user_id is
None, so buckets 2 and 3 are skipped (no-op).

How to verify bucket 2 and 3 are actually enforced
----------------------------------------------------
Hit a heavy endpoint from TWO DIFFERENT IPs with the SAME user token:

  # Terminal 1 — simulate IP A
  for i in $(seq 1 40); do
    curl -s -o /dev/null -w "%{http_code}\\n" \\
      -H "Authorization: Bearer $TOKEN" \\
      http://localhost:8000/api/v1/forecasts
  done

  # Terminal 2 — simulate IP B (same user, different IP via X-Forwarded-For)
  for i in $(seq 1 40); do
    curl -s -o /dev/null -w "%{http_code}\\n" \\
      -H "Authorization: Bearer $TOKEN" \\
      -H "X-Forwarded-For: 10.0.0.99" \\
      http://localhost:8000/api/v1/forecasts
  done

Both terminals should 429 after a combined ~30 requests (the heavy bucket is
shared by user_id, not IP), even though each IP has not hit its own 600/min limit.
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
# Heavy-endpoint path prefixes (bucket 3 applies when a request path starts
# with any of these values).
# ---------------------------------------------------------------------------

_HEAVY_PREFIXES: tuple[str, ...] = (
    "/api/v1/forecasts",
    "/api/v1/export",
    "/api/v1/hybrid-forecast",
    "/api/v1/integrations",  # covers /upload sub-paths
)

# ---------------------------------------------------------------------------
# Redis sliding-window implementation
# ---------------------------------------------------------------------------

# Atomic check-and-increment evaluated server-side in ONE round trip.
#   - INCR the window counter; on the first hit, set its TTL.
#   - If over the limit, return the remaining TTL (>=1) as Retry-After.
#   - Otherwise return 0 (allowed).
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

_REDIS_ERROR = object()  # sentinel: Redis call failed


async def _redis_check(
    script, key: str, limit: int, window_s: int = 60
) -> tuple[bool, int] | object:
    """Run the atomic rate-limit script.

    Returns:
        (is_limited: bool, retry_after: int)  on success
        _REDIS_ERROR sentinel                  when Redis is unavailable
    """
    try:
        ttl = int(await script(keys=[key], args=[window_s, limit]))
        return ttl > 0, ttl
    except Exception as exc:
        log.warning("rate_limit.redis.error", error=str(exc))
        return _REDIS_ERROR


# ---------------------------------------------------------------------------
# In-process token-bucket (fallback for bucket 1 when Redis is absent)
# ---------------------------------------------------------------------------


class _InProcessBucket:
    """Thread-safe-enough token bucket for single-process dev use."""

    def __init__(self, per_minute: int, burst: int | None) -> None:
        self._capacity = burst or per_minute
        self._refill_rate = per_minute / 60.0  # tokens / second
        self._buckets: dict[str, tuple[float, float]] = defaultdict(
            lambda: (self._capacity, time.monotonic())
        )

    def is_limited(self, key: str) -> tuple[bool, int]:
        tokens, last = self._buckets[key]
        now = time.monotonic()
        tokens = min(self._capacity, tokens + (now - last) * self._refill_rate)
        if tokens < 1.0:
            retry_after = int((1.0 - tokens) / self._refill_rate) + 1
            return True, retry_after
        self._buckets[key] = (tokens - 1.0, now)
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
    """Rate-limit middleware.

    Instantiate with ``ip_only=True`` (outermost, before auth) for bucket 1,
    and again with ``ip_only=False`` (inside TenantContextMiddleware, after
    auth) for buckets 2 and 3. See module docstring for the registration order
    and the reasoning behind the split.

    Args:
        ip_only: When True, only the per-IP bucket (bucket 1) runs. When False,
            only the per-user and heavy-endpoint buckets (buckets 2 and 3) run.
            This controls which middleware instance you are creating — register
            both to get full three-tier enforcement.
    """

    def __init__(
        self,
        app,
        *,
        ip_only: bool = False,
        per_minute: int = 600,
        per_user_per_minute: int = 300,
        heavy_per_minute: int = 30,
        heavy_fail_closed: bool = True,
        burst: int | None = None,
        trusted_proxy_count: int = 1,
    ) -> None:
        super().__init__(app)
        self._ip_only = ip_only
        self._per_minute = per_minute
        self._per_user_per_minute = per_user_per_minute
        self._heavy_per_minute = heavy_per_minute
        self._heavy_fail_closed = heavy_fail_closed
        self._trusted_proxy_count = trusted_proxy_count
        # In-process fallback only used for the IP bucket (ip_only=True instance)
        self._fallback = _InProcessBucket(per_minute, burst) if ip_only else None
        self._redis_client = None  # resolved on first request via app.state
        self._rl_script = None  # registered AsyncScript, built once Redis is known

    def _is_heavy(self, path: str) -> bool:
        return any(path.startswith(prefix) for prefix in _HEAVY_PREFIXES)

    def _ensure_script(self) -> None:
        """Register the Lua script once Redis is known."""
        if self._rl_script is None and self._redis_client is not None:
            self._rl_script = self._redis_client.register_script(_RATE_LIMIT_LUA)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        # Skip non-API and health/metrics paths
        path = request.url.path
        if not path.startswith("/api/") or path.endswith(("/health", "/metrics")):
            return await call_next(request)

        # Lazy-resolve Redis from app.state (set in lifespan if redis_url is configured)
        if self._redis_client is None:
            self._redis_client = getattr(
                getattr(request, "app", None),
                "state",
                type("_s", (), {"redis": None})(),
            ).redis  # may still be None
        self._ensure_script()

        if self._ip_only:
            return await self._dispatch_ip(request, call_next, path)
        else:
            return await self._dispatch_user(request, call_next, path)

    # ── Bucket 1: per-IP (ip_only=True instance) ─────────────────────────────

    async def _dispatch_ip(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
        path: str,
    ) -> Response:
        client_ip = client_ip_from_request(request, self._trusted_proxy_count)

        if self._redis_client is not None and self._rl_script is not None:
            result = await _redis_check(
                self._rl_script, f"rl:ip:{client_ip}", self._per_minute
            )
            if result is _REDIS_ERROR:
                # Fail-open: a Redis blip must not stop all API traffic
                log.warning("rate_limit.ip.redis_error_fail_open", ip=client_ip)
            elif result[0]:  # type: ignore[index]
                _, retry_after = result  # type: ignore[misc]
                log.warning("rate_limit.ip.exceeded", ip=client_ip, path=path)
                return _rate_limited(retry_after)
        elif self._fallback is not None:
            limited, retry_after = self._fallback.is_limited(client_ip)
            if limited:
                log.warning("rate_limit.ip.exceeded", ip=client_ip, path=path)
                return _rate_limited(retry_after)

        return await call_next(request)

    # ── Buckets 2 & 3: per-user + heavy (ip_only=False instance) ─────────────
    # Runs AFTER TenantContextMiddleware, so request.state.user_id is populated.

    async def _dispatch_user(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
        path: str,
    ) -> Response:
        # user_id is None for unauthenticated / public-path requests.
        # Both buckets are skipped for those — they are already behind the IP gate.
        user_id = getattr(request.state, "user_id", None)
        if user_id is None:
            return await call_next(request)

        # ── Bucket 2: per-user ────────────────────────────────────────────────
        if self._redis_client is not None and self._rl_script is not None:
            result = await _redis_check(
                self._rl_script, f"rl:user:{user_id}", self._per_user_per_minute
            )
            if result is _REDIS_ERROR:
                log.warning("rate_limit.user.redis_error_fail_open", user_id=str(user_id))
            elif result[0]:  # type: ignore[index]
                _, retry_after = result  # type: ignore[misc]
                log.warning("rate_limit.user.exceeded", user_id=str(user_id), path=path)
                return _rate_limited(retry_after)

        # ── Bucket 3: heavy-endpoint (fail-closed on Redis error) ─────────────
        if self._is_heavy(path):
            if self._redis_client is not None and self._rl_script is not None:
                result = await _redis_check(
                    self._rl_script, f"rl:heavy:{user_id}", self._heavy_per_minute
                )
                if result is _REDIS_ERROR:
                    if self._heavy_fail_closed:
                        log.error(
                            "rate_limit.heavy.redis_error_fail_closed",
                            user_id=str(user_id),
                            path=path,
                        )
                        return JSONResponse(
                            status_code=503,
                            content={
                                "detail": (
                                    "Rate limiter temporarily unavailable. "
                                    "Please retry in a moment."
                                )
                            },
                        )
                    log.warning(
                        "rate_limit.heavy.redis_error_fail_open",
                        user_id=str(user_id),
                    )
                elif result[0]:  # type: ignore[index]
                    _, retry_after = result  # type: ignore[misc]
                    log.warning(
                        "rate_limit.heavy.exceeded", user_id=str(user_id), path=path
                    )
                    return _rate_limited(retry_after)
            else:
                # No Redis in dev/single-node — skip heavy bucket; log once so it's visible
                log.debug(
                    "rate_limit.heavy.no_redis_skip",
                    note="Set REDIS_URL to enforce the heavy-endpoint bucket in production",
                )

        return await call_next(request)


def _rate_limited(retry_after: int) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "Rate limit exceeded"},
        headers={"Retry-After": str(retry_after)},
    )
