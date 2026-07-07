"""Login attempt tracking for brute-force protection.

Tracks failed login attempts per (tenant_slug, email) key.
Uses Redis when available (shared across replicas); falls back to an
in-process LRU dict for single-node dev environments.

Policy:
  • 5 failed attempts within a 15-minute window → 429 Too Many Requests
  • Successful login resets the counter for that key
  • Redis keys auto-expire after WINDOW_SECONDS so bans lift automatically
"""

from __future__ import annotations

import time
from collections import defaultdict

import structlog

log = structlog.get_logger(__name__)

MAX_ATTEMPTS = 5  # per (tenant, email) account
IP_MAX_ATTEMPTS = 25  # per client IP — higher, to tolerate shared NAT/proxy
# while still catching email-rotation brute force
WINDOW_SECONDS = 900  # 15 minutes

# ---------------------------------------------------------------------------
# In-process fallback (dev / single-node)
# ---------------------------------------------------------------------------
_in_process: dict[str, list[float]] = defaultdict(list)


def _ip_key(tenant_slug: str, email: str) -> str:
    return f"login_attempt:{tenant_slug}:{email}"


# ---------------------------------------------------------------------------
# Public API — functions accept an optional redis_client
# ---------------------------------------------------------------------------


async def record_failure(key: str, redis_client=None) -> int:
    """Record a failed login attempt. Returns the current failure count."""
    if redis_client is not None:
        try:
            redis_key = f"lf:{key}"
            count = await redis_client.incr(redis_key)
            if count == 1:
                await redis_client.expire(redis_key, WINDOW_SECONDS)
            log.info("login_attempt.failure.redis", key=key, count=count)
            return int(count)
        except Exception as exc:
            log.warning("login_attempt.redis.error", error=str(exc))

    # In-process fallback
    now = time.monotonic()
    attempts = [t for t in _in_process[key] if now - t < WINDOW_SECONDS]
    attempts.append(now)
    _in_process[key] = attempts
    return len(attempts)


async def record_success(key: str, redis_client=None) -> None:
    """Clear the failure counter after a successful login."""
    if redis_client is not None:
        try:
            await redis_client.delete(f"lf:{key}")
            return
        except Exception as exc:
            log.warning("login_attempt.redis.error", error=str(exc))

    _in_process.pop(key, None)


async def is_locked_out(
    key: str, redis_client=None, *, max_attempts: int = MAX_ATTEMPTS
) -> tuple[bool, int]:
    """Return (is_locked, retry_after_seconds).

    retry_after_seconds is 0 when not locked. ``max_attempts`` lets callers use
    a higher threshold for per-IP keys than for per-account keys.
    """
    if redis_client is not None:
        try:
            redis_key = f"lf:{key}"
            count_raw = await redis_client.get(redis_key)
            count = int(count_raw or 0)
            if count >= max_attempts:
                ttl = await redis_client.ttl(redis_key)
                return True, max(ttl, 1)
            return False, 0
        except Exception as exc:
            log.warning("login_attempt.redis.error", error=str(exc))

    # In-process fallback
    now = time.monotonic()
    attempts = [t for t in _in_process.get(key, []) if now - t < WINDOW_SECONDS]
    if len(attempts) >= max_attempts:
        oldest = min(attempts)
        retry_after = int(WINDOW_SECONDS - (now - oldest)) + 1
        return True, max(retry_after, 1)
    return False, 0
