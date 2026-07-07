"""Tests for the Redis leader lease lock used to make background loops singleton.

These are pure-asyncio unit tests with an in-memory fake Redis — no Postgres
container needed, so they run fast and in isolation.
"""

from __future__ import annotations

import asyncio

import pytest

from app.core.distributed_lock import RedisLeaderLock, run_as_leader


class FakeRedis:
    """Minimal async Redis supporting the lock's SET NX / eval(CAS) usage."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def set(self, key, value, nx=False, ex=None, px=None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def eval(self, script, numkeys, *args):
        key = args[0]
        argv = args[1:]
        if "del" in script:  # release: compare-and-delete
            if self.store.get(key) == argv[0]:
                self.store.pop(key, None)
                return 1
            return 0
        if "pexpire" in script:  # renew: compare-and-extend
            return 1 if self.store.get(key) == argv[0] else 0
        return 0


async def test_noop_mode_always_wins_without_redis():
    lock = RedisLeaderLock(None, "x")
    assert await lock.acquire() is True
    assert lock.is_held is True
    await lock.release()
    assert lock.is_held is False


async def test_only_one_holder_at_a_time():
    redis = FakeRedis()
    a = RedisLeaderLock(redis, "singleton", ttl_s=30, renew_interval_s=5)
    b = RedisLeaderLock(redis, "singleton", ttl_s=30, renew_interval_s=5)

    assert await a.acquire() is True
    assert await b.acquire() is False  # a already holds it

    # After the holder releases, the other can take over.
    await a.release()
    assert await b.acquire() is True
    await b.release()


async def test_release_is_owner_checked():
    redis = FakeRedis()
    a = RedisLeaderLock(redis, "owned", ttl_s=30)
    b = RedisLeaderLock(redis, "owned", ttl_s=30)
    await a.acquire()
    # b never owned it; b.release() must not delete a's lease.
    await b.release()
    assert redis.store.get("sanket:leader:owned") == a._identity


async def test_renew_interval_clamped_below_ttl():
    lock = RedisLeaderLock(FakeRedis(), "z", ttl_s=10, renew_interval_s=20)
    assert lock._renew_interval_s < 10


async def test_run_as_leader_runs_guarded_work_then_can_be_cancelled():
    redis = FakeRedis()
    ran = asyncio.Event()

    async def work():
        ran.set()
        await asyncio.sleep(3600)  # hold leadership until cancelled

    task = asyncio.create_task(
        run_as_leader(redis, "job", work, ttl_s=30, renew_interval_s=5, retry_interval_s=0.1)
    )
    await asyncio.wait_for(ran.wait(), timeout=2)
    # The lease is held by the running leader.
    assert redis.store.get("sanket:leader:job") is not None
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    # Lease released on cancellation so a standby can take over.
    assert redis.store.get("sanket:leader:job") is None
