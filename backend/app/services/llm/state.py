from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass

from app.config import Settings
from app.services.llm.errors import AIError, TokenUsage


def cache_key(*, tenant: str, policy: str, payload: dict, config: Settings,
              task_name: str = "import_mapping", schema_version: str = "1", language: str = "en",
              actor_scope: str = "", snapshot: str = "") -> str:
    identity = [task_name, schema_version, language, actor_scope, snapshot, policy, config.llm_base_url, config.llm_model,
                config.llm_compatibility, config.llm_cache_generation, payload]
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return f"sanket:ai:{{{tenant}}}:cache:{digest}"


@dataclass(frozen=True)
class Reservation:
    key: str
    receipt: str
    amount: int


_RELEASE = """
if redis.call('GET', KEYS[1]) == ARGV[1] then return redis.call('DEL', KEYS[1]) end
return 0
"""
_PUT = """
if redis.call('GET', KEYS[1]) ~= ARGV[1] then return 0 end
redis.call('SET', KEYS[2], ARGV[2], 'EX', ARGV[3]); return 1
"""
_ADMIT = """
local m = tonumber(redis.call('GET', KEYS[1]) or '0')
local d = tonumber(redis.call('GET', KEYS[2]) or '0')
if m >= tonumber(ARGV[1]) or d >= tonumber(ARGV[2]) then return 0 end
redis.call('INCR', KEYS[1]); redis.call('EXPIRE', KEYS[1], 120)
redis.call('INCR', KEYS[2]); redis.call('EXPIRE', KEYS[2], 172800)
return 1
"""
_RESERVE = """
if redis.call('EXISTS', KEYS[2]) == 1 then return 1 end
local used = tonumber(redis.call('GET', KEYS[1]) or '0')
if used + tonumber(ARGV[1]) > tonumber(ARGV[2]) then return 0 end
redis.call('INCRBY', KEYS[1], ARGV[1]); redis.call('EXPIRE', KEYS[1], 172800)
redis.call('SET', KEYS[2], 'reserved', 'EX', 172800); return 1
"""
_SETTLE = """
if redis.call('GET', KEYS[2]) ~= 'reserved' then return 0 end
redis.call('INCRBY', KEYS[1], tonumber(ARGV[1]) - tonumber(ARGV[2]))
redis.call('SET', KEYS[2], 'settled', 'EX', 172800); return 1
"""
_ENTER = """
local now = tonumber(ARGV[2])
local opened = tonumber(redis.call('HGET', KEYS[1], 'until') or '0')
if opened > 0 then
  if now < opened then return 0 end
  local probe = redis.call('HGET', KEYS[1], 'probe')
  local lease = tonumber(redis.call('HGET', KEYS[1], 'probe_until') or '0')
  if probe and lease > now then return 0 end
  redis.call('HSET', KEYS[1], 'probe', ARGV[1], 'probe_until', now + tonumber(ARGV[3]))
end
local epoch = redis.call('HGET', KEYS[1], 'epoch') or '0'
redis.call('HSET', KEYS[1], 'in:' .. ARGV[1], epoch)
redis.call('EXPIRE', KEYS[1], 7200); return 1
"""
_FINISH = """
local field = 'in:' .. ARGV[1]
local epoch = redis.call('HGET', KEYS[1], field)
if not epoch then return 0 end
redis.call('HDEL', KEYS[1], field)
if epoch ~= (redis.call('HGET', KEYS[1], 'epoch') or '0') then return 0 end
local probe = redis.call('HGET', KEYS[1], 'probe')
if probe and probe ~= ARGV[1] then return 0 end
if ARGV[2] == 'neutral' then
  if probe == ARGV[1] then redis.call('HDEL', KEYS[1], 'probe', 'probe_until') end
  return 1
end
if ARGV[2] == 'failure' then
  local failures = redis.call('HINCRBY', KEYS[1], 'failures', 1)
  if failures >= tonumber(ARGV[4]) or probe then
    redis.call('HSET', KEYS[1], 'until', tonumber(ARGV[3]) + tonumber(ARGV[5]))
    redis.call('HINCRBY', KEYS[1], 'epoch', 1)
    redis.call('HDEL', KEYS[1], 'probe', 'probe_until')
  end
else
  redis.call('HSET', KEYS[1], 'failures', 0, 'until', 0)
  redis.call('HINCRBY', KEYS[1], 'epoch', 1)
  redis.call('HDEL', KEYS[1], 'probe', 'probe_until')
end
return 1
"""


class AIState:
    """Separate fail-closed AI namespace; ordinary app cache behavior is untouched."""

    def __init__(self, redis, settings: Settings, *, clock=time.time):
        self.redis, self.settings, self.clock = redis, settings, clock
        identity = f"{settings.llm_base_url}|{settings.llm_model}"
        self.breaker_key = "sanket:ai:provider:" + hashlib.sha256(identity.encode()).hexdigest()

    async def _call(self, method, *args, **kwargs):
        try:
            if self.redis is None:
                raise RuntimeError("Redis required for AI")
            return await getattr(self.redis, method)(*args, **kwargs)
        except Exception:
            raise AIError("infrastructure_unavailable") from None

    async def _eval(self, script, keys, *args):
        return await self._call("eval", script, len(keys), *keys, *args)

    async def cached(self, key):
        return await self._call("get", key)

    async def acquire(self, key, owner):
        return bool(await self._call("set", key + ":lease", owner, nx=True,
                                     px=int((self.settings.llm_deadline_s + 5) * 1000)))

    async def release(self, key, owner):
        await self._eval(_RELEASE, [key + ":lease"], owner)

    async def put(self, key, owner, content):
        if not await self._eval(_PUT, [key + ":lease", key], owner, content, self.settings.llm_cache_ttl_s):
            raise AIError("infrastructure_unavailable")

    async def admit(self, tenant):
        now = int(self.clock())
        prefix = f"sanket:ai:{{{tenant}}}:requests:"
        if not await self._eval(_ADMIT, [prefix + f"m:{now // 60}", prefix + f"d:{now // 86400}"],
                                self.settings.llm_requests_per_minute, self.settings.llm_requests_per_day):
            raise AIError("request_limit")

    async def reserve(self, tenant, attempt) -> Reservation:
        key = f"sanket:ai:{{{tenant}}}:tokens:{int(self.clock()) // 86400}"
        receipt = key + ":" + attempt
        amount = self.settings.llm_max_input_bytes + self.settings.llm_max_output_tokens
        if not await self._eval(_RESERVE, [key, receipt], amount, self.settings.llm_daily_token_limit):
            raise AIError("token_limit")
        return Reservation(key, receipt, amount)

    async def settle(self, reservation: Reservation, usage: TokenUsage | None):
        if usage is not None:
            await self._eval(_SETTLE, [reservation.key, reservation.receipt],
                             usage.input_tokens + usage.output_tokens, reservation.amount)

    async def breaker_enter(self, owner):
        if not await self._eval(_ENTER, [self.breaker_key], owner, self.clock(), self.settings.llm_deadline_s + 5):
            raise AIError("circuit_open")

    async def breaker_finish(self, owner, *, failed: bool | None):
        status = "neutral" if failed is None else "failure" if failed else "success"
        await self._eval(_FINISH, [self.breaker_key], owner, status, self.clock(),
                         self.settings.llm_breaker_failures, self.settings.llm_breaker_cooldown_s)
