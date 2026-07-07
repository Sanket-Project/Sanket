"""Redis lease lock + leader election for singleton background work.

Problem this solves
-------------------
Several background loops are started inside the FastAPI ``lifespan`` (signal
ingestion, the Shopify sales poller, the webhook retry worker). With more than
one API replica each loop runs once *per replica*, so external APIs get polled
N× and ``pending`` webhooks get retried N× concurrently — duplicate work and,
for non-idempotent deliveries, duplicate side effects.

A :class:`RedisLeaderLock` is a single-holder lease: a replica wins the lock by
``SET key value NX EX ttl``. Only the holder runs the guarded loop. The holder
renews the lease on an interval; if it crashes the lease expires and another
replica takes over within ``ttl`` seconds. Release is atomic and owner-checked
via a Lua compare-and-delete so a replica can never delete a lease it no longer
owns (e.g. after a GC pause that outlived the TTL).

When Redis is unavailable (single-node dev, ``REDIS_URL`` unset) the lock is a
no-op that always "wins" — exactly the prior single-process behaviour.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import socket
import uuid

import structlog

log = structlog.get_logger(__name__)

# Atomic compare-and-delete: only delete the key if we still own it.
_RELEASE_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
"""

# Atomic compare-and-renew: extend TTL only if we still own it.
_RENEW_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('pexpire', KEYS[1], ARGV[2])
else
    return 0
end
"""


def _make_identity() -> str:
    """Stable-per-process identity so logs can attribute a lease to a replica."""
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


class RedisLeaderLock:
    """A renewable, single-holder lease lock backed by Redis.

    ``redis_client`` is an ``redis.asyncio`` client or ``None`` (no-op mode).
    """

    def __init__(
        self,
        redis_client,
        name: str,
        *,
        ttl_s: int = 30,
        renew_interval_s: int = 10,
        identity: str | None = None,
    ) -> None:
        if renew_interval_s >= ttl_s:
            # A renew interval >= ttl risks the lease expiring before we renew.
            renew_interval_s = max(1, ttl_s // 2)
        self._redis = redis_client
        self._key = f"sanket:leader:{name}"
        self._name = name
        self._ttl_ms = ttl_s * 1000
        self._renew_interval_s = renew_interval_s
        self._identity = identity or _make_identity()
        self._held = False
        self._renew_task: asyncio.Task | None = None

    @property
    def is_held(self) -> bool:
        return self._held

    async def acquire(self) -> bool:
        """Try once to win the lease. Returns True on success (or no-op mode)."""
        if self._redis is None:
            self._held = True
            return True
        try:
            won = await self._redis.set(self._key, self._identity, nx=True, px=self._ttl_ms)
        except Exception as exc:
            # Fail safe: if Redis is unreachable we'd rather run the loop than
            # silently stop all background work. Duplicate work is recoverable;
            # a stalled pipeline is not.
            log.warning("leader_lock.acquire.error", lock=self._name, error=str(exc))
            self._held = True
            return True
        self._held = bool(won)
        return self._held

    async def _renew_loop(self) -> None:
        while self._held:
            await asyncio.sleep(self._renew_interval_s)
            if self._redis is None:
                continue
            try:
                ok = await self._redis.eval(
                    _RENEW_LUA, 1, self._key, self._identity, str(self._ttl_ms)
                )
                if not ok:
                    # Lost the lease (expired + taken by another replica).
                    log.warning("leader_lock.lost", lock=self._name)
                    self._held = False
                    return
            except Exception as exc:
                log.warning("leader_lock.renew.error", lock=self._name, error=str(exc))

    def start_renewing(self) -> None:
        """Begin the background renew loop (call after a successful acquire)."""
        if self._redis is None or self._renew_task is not None:
            return
        self._renew_task = asyncio.create_task(self._renew_loop())

    async def release(self) -> None:
        if self._renew_task is not None:
            self._renew_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._renew_task
            self._renew_task = None
        if self._redis is not None and self._held:
            try:
                await self._redis.eval(_RELEASE_LUA, 1, self._key, self._identity)
            except Exception as exc:
                log.warning("leader_lock.release.error", lock=self._name, error=str(exc))
        self._held = False


async def run_as_leader(
    redis_client,
    name: str,
    coro_factory,
    *,
    ttl_s: int = 30,
    renew_interval_s: int = 10,
    retry_interval_s: float = 5.0,
) -> None:
    """Run ``coro_factory()`` only while this replica holds the ``name`` lease.

    Loops forever: when not the leader it polls for the lease every
    ``retry_interval_s`` so a standby replica takes over within ``ttl`` of the
    leader dying. ``coro_factory`` must return an awaitable that runs the actual
    guarded work and returns when it should yield leadership (or raises).
    """
    while True:
        lock = RedisLeaderLock(redis_client, name, ttl_s=ttl_s, renew_interval_s=renew_interval_s)
        won = await lock.acquire()
        if not won:
            await asyncio.sleep(retry_interval_s)
            continue
        log.info("leader_lock.acquired", lock=name, identity=lock._identity)
        lock.start_renewing()
        try:
            await coro_factory()
        except asyncio.CancelledError:
            await lock.release()
            raise
        except Exception as exc:
            log.error("leader_lock.guarded_task.error", lock=name, error=str(exc))
        finally:
            await lock.release()
        await asyncio.sleep(retry_interval_s)
