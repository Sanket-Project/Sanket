"""Opt-in, one-call, non-sensitive foundation probe. Never run by CI."""
from __future__ import annotations

import argparse
import asyncio
import json
import time
import uuid

from app.config import Settings, get_settings
from app.core.database import Database
from app.models.enums import IndustryCode
from app.services.llm.client import ProviderClient
from app.services.llm.contracts import Column, TaskInput
from app.services.llm.policy import AIContext, PolicyStore
from app.services.llm.service import AIService
from app.services.llm.state import AIState
from app.services.llm.telemetry import Telemetry


def probe_settings(config: Settings) -> Settings:
    return config.model_copy(update={
        "llm_max_retries": 0,
        "llm_max_input_bytes": min(config.llm_max_input_bytes, 2048),
        "llm_max_output_tokens": min(config.llm_max_output_tokens, 256),
        "llm_daily_token_limit": min(config.llm_daily_token_limit, 4096),
    })


class ProbeTelemetry:
    def __init__(self, telemetry):
        self.telemetry = telemetry
        self.observed_usage = None

    async def record(self, *args, **kwargs):
        await self.telemetry.record(*args, **kwargs)
        if args[2] == "finished":
            self.observed_usage = kwargs.get("usage")


async def execute_probe(ctx: AIContext) -> dict:
    import redis.asyncio as redis

    config = probe_settings(get_settings())
    if not config.deepseek_api_key or not config.deepseek_api_key.get_secret_value().strip():
        return {"state": "unavailable", "reason": "configuration_missing"}
    if not config.redis_url:
        return {"state": "unavailable", "reason": "infrastructure_unavailable"}
    db = Database(config)
    redis_client = redis.from_url(config.redis_url, decode_responses=True,
                                  socket_connect_timeout=2, socket_timeout=2)
    client = ProviderClient(config)
    telemetry = ProbeTelemetry(Telemetry(db, config))
    try:
        await db.assert_tenant_isolation_enforced(strict=True)
        await redis_client.ping()
        service = AIService(config, PolicyStore(db), AIState(redis_client, config), client, telemetry)
        # A unique, non-sensitive ID forces this probe to test a fresh dispatch.
        task = TaskInput(columns=[Column(id=f"probe_{uuid.uuid4().hex}", label="Quantity", kind="integer")],
                         allowed_fields=["quantity"])
        start = time.monotonic()
        result = await service.run(ctx, task)
        actual = telemetry.observed_usage
        return {"state": result.state, "reason": result.reason, "model": config.llm_model,
                "cached": result.cached, "latency_ms": int((time.monotonic() - start) * 1000),
                "input_tokens": actual.input_tokens if actual else None,
                "output_tokens": actual.output_tokens if actual else None}
    finally:
        await client.aclose()
        await redis_client.aclose()
        await db.close()


async def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-live", action="store_true")
    parser.add_argument("--workspace", type=uuid.UUID)
    parser.add_argument("--actor", type=uuid.UUID)
    parser.add_argument("--industry", choices=[industry.value for industry in IndustryCode])
    args = parser.parse_args(argv)
    if not args.allow_live or not args.workspace or not args.actor or not args.industry:
        print(json.dumps({"state": "disabled", "reason": "explicit_live_opt_in_and_context_required"}))
        return 2
    try:
        result = await execute_probe(AIContext(args.workspace, args.actor, IndustryCode(args.industry)))
    except Exception:
        # Provider/config/connection exception text can contain credentials or data.
        result = {"state": "unavailable", "reason": "probe_unavailable"}
    print(json.dumps(result))
    return 0 if result["state"] == "success" else 2


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
