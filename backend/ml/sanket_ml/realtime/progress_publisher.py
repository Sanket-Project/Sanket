"""Publishes training/forecast progress events to Redis so the backend
WebSocket layer can fan them out to tenant browser sessions.

The ML process never opens WebSockets itself — it only PUBLISHes to a
Redis channel that the backend's `ConnectionManager._consume_redis()`
subscribes to. This keeps the inference service stateless.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog

log = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class ProgressPublisher:
    redis_url: str | None

    def channel(self, tenant_id: uuid.UUID) -> str:
        return f"sanket:tenant:{tenant_id}"

    async def publish(
        self,
        *,
        tenant_id: uuid.UUID,
        run_id: uuid.UUID,
        stage: str,
        step: int,
        total_steps: int,
        message: str = "",
        industry: str | None = None,
        completed: bool = False,
    ) -> None:
        if not self.redis_url:
            return
        try:
            import redis.asyncio as redis  # type: ignore
        except ImportError:
            log.warning("progress.redis.import_failed")
            return
        event = {
            "event_id": str(uuid.uuid4()),
            "type": "forecast.run.completed" if completed else "forecast.run.progress",
            "tenant_id": str(tenant_id),
            "industry": industry,
            "occurred_at": datetime.now(tz=UTC).isoformat(),
            "data": {
                "run_id": str(run_id),
                "stage": stage,
                "step": step,
                "total_steps": total_steps,
                "message": message,
            },
        }
        try:
            client = redis.from_url(self.redis_url, decode_responses=True)
            await client.publish(self.channel(tenant_id), json.dumps(event))
            await client.close()
        except Exception as exc:
            log.warning("progress.publish_failed", error=str(exc))


_PUBLISHER: ProgressPublisher | None = None


def get_publisher() -> ProgressPublisher:
    global _PUBLISHER
    if _PUBLISHER is None:
        _PUBLISHER = ProgressPublisher(redis_url=os.environ.get("ML_REDIS_URL"))
    return _PUBLISHER
