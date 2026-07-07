"""Admission control for the ML inference API — DoS protection.

Forecast inference is CPU-bound and slow (tens of seconds for zero-shot Chronos
on CPU). Three failure modes this guards against:

1. **Concurrency overload** — too many forecasts running at once thrash CPU and
   blow out tail latency for everyone. A semaphore caps concurrent executions;
   the heavy synchronous compute is offloaded to a thread pool so the event loop
   stays free to serve /health and reject excess load promptly.

2. **Unbounded queueing** — when all slots are busy, letting requests pile up
   forever just converts an overload into a timeout storm. We admit only a
   bounded queue; past that we shed load immediately with HTTP 429 + Retry-After
   (fast fail beats slow fail).

3. **Tenant unfairness / abuse** — one tenant hammering the endpoint could
   consume the whole replica. A per-tenant token bucket enforces a fair share.

All limits are per-replica (the service is stateless and horizontally scaled),
which is the correct place to protect a finite local CPU pool.
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager

import structlog

log = structlog.get_logger(__name__)


class ThrottleRejectionError(Exception):
    """Raised to reject a request under load. ``retry_after_s`` hints the client."""

    def __init__(self, reason: str, retry_after_s: int = 1) -> None:
        super().__init__(reason)
        self.reason = reason
        self.retry_after_s = retry_after_s


class _TokenBucket:
    """Classic token bucket: ``rate`` tokens/sec, capacity ``burst``."""

    def __init__(self, rate_per_min: int, burst: int) -> None:
        self._rate = rate_per_min / 60.0
        self._capacity = float(burst)
        self._tokens = float(burst)
        self._last = time.monotonic()

    def take(self) -> tuple[bool, int]:
        now = time.monotonic()
        self._tokens = min(self._capacity, self._tokens + (now - self._last) * self._rate)
        self._last = now
        if self._tokens < 1.0:
            retry = int((1.0 - self._tokens) / self._rate) + 1 if self._rate > 0 else 60
            return False, retry
        self._tokens -= 1.0
        return True, 0


class InferenceThrottle:
    """Per-replica admission controller for forecast inference."""

    def __init__(
        self,
        *,
        max_concurrent: int,
        max_queued: int,
        tenant_rate_per_min: int,
        tenant_burst: int,
        acquire_timeout_s: float,
    ) -> None:
        self._sem = asyncio.Semaphore(max_concurrent)
        self._capacity = max_concurrent + max_queued  # total admissible in-flight
        self._acquire_timeout_s = acquire_timeout_s
        self._tenant_rate_per_min = tenant_rate_per_min
        self._tenant_burst = tenant_burst
        self._inflight = 0
        self._guard = asyncio.Lock()
        self._buckets: dict[str, _TokenBucket] = {}
        # Monotonic counters for Prometheus scraping (see api.py /metrics).
        self.accepted_total = 0
        self.rejected_total: dict[str, int] = {
            "tenant_rate_limited": 0,
            "overloaded": 0,
            "queue_timeout": 0,
        }

    def stats(self) -> dict:
        return {
            "inflight": self._inflight,
            "capacity": self._capacity,
            "available_slots": self._sem._value,  # type: ignore[attr-defined]
            "accepted_total": self.accepted_total,
            "rejected_total": dict(self.rejected_total),
        }

    def _tenant_ok(self, tenant_id: str) -> tuple[bool, int]:
        bucket = self._buckets.get(tenant_id)
        if bucket is None:
            bucket = _TokenBucket(self._tenant_rate_per_min, self._tenant_burst)
            self._buckets[tenant_id] = bucket
        return bucket.take()

    @asynccontextmanager
    async def slot(self, tenant_id: str):
        """Admit one inference or raise :class:`ThrottleRejectionError`.

        Order of checks (cheapest / most-specific first):
          1. Per-tenant rate limit  → 429 (tenant exceeded its share)
          2. Global queue capacity  → 429 (replica overloaded)
          3. Concurrency semaphore  → wait up to acquire_timeout_s, else 429
        """
        ok, retry = self._tenant_ok(tenant_id)
        if not ok:
            self.rejected_total["tenant_rate_limited"] += 1
            log.warning("inference.throttle.tenant_limited", tenant=tenant_id, retry_after=retry)
            raise ThrottleRejectionError("tenant_rate_limited", retry)

        async with self._guard:
            if self._inflight >= self._capacity:
                self.rejected_total["overloaded"] += 1
                log.warning("inference.throttle.overloaded", inflight=self._inflight)
                raise ThrottleRejectionError("overloaded", 2)
            self._inflight += 1

        try:
            try:
                await asyncio.wait_for(self._sem.acquire(), timeout=self._acquire_timeout_s)
            except TimeoutError as exc:
                self.rejected_total["queue_timeout"] += 1
                raise ThrottleRejectionError("queue_timeout", 5) from exc
            self.accepted_total += 1
            try:
                yield
            finally:
                self._sem.release()
        finally:
            async with self._guard:
                self._inflight -= 1


def build_throttle(settings) -> InferenceThrottle:
    return InferenceThrottle(
        max_concurrent=settings.inference_max_concurrent,
        max_queued=settings.inference_max_queued,
        tenant_rate_per_min=settings.inference_tenant_rate_per_min,
        tenant_burst=settings.inference_tenant_burst,
        acquire_timeout_s=settings.inference_acquire_timeout_s,
    )
