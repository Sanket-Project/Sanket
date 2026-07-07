"""arq worker for durable, out-of-process hybrid forecast runs.

Run it alongside the API:

    cd backend
    .venv\\Scripts\\python.exe -m arq app.workers.forecast_worker.WorkerSettings

The worker holds its own Database engine, httpx client, and a publish-only
realtime manager (events are fanned out to WebSocket clients by the API
replicas that consume the same Redis pub/sub). Jobs survive an API restart
because they live in Redis until a worker picks them up.
"""

from __future__ import annotations

import uuid

import httpx
import structlog
from arq.connections import RedisSettings

# Side-effect import so SQLAlchemy registers every ORM model before any query.
import app.models  # noqa: F401
from app.config import get_settings
from app.core.database import Database
from app.realtime.connection_manager import ConnectionManager
from app.schemas.trends import HybridForecastRequest
from app.services.hybrid_forecast import execute_hybrid_run

log = structlog.get_logger(__name__)


async def run_hybrid_forecast(
    ctx: dict,
    run_id: str,
    tenant_id: str,
    industry_code: str,
    body_dict: dict,
) -> str:
    """arq task: compute a hybrid forecast and persist it to its run row."""
    body = HybridForecastRequest.model_validate(body_dict)
    await execute_hybrid_run(
        db=ctx["db"],
        http_client=ctx["http"],
        realtime=ctx["realtime"],
        run_id=uuid.UUID(run_id),
        tenant_id=uuid.UUID(tenant_id),
        industry_code=industry_code,
        body=body,
    )
    return run_id


async def startup(ctx: dict) -> None:
    settings = get_settings()
    from app.core.logging import configure_logging

    configure_logging(settings)
    ctx["db"] = Database(settings)
    ctx["http"] = httpx.AsyncClient(
        timeout=settings.ml_api_timeout_s,
        limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
    )
    realtime = ConnectionManager(redis_url=settings.redis_url)
    await realtime.connect_publisher()
    ctx["realtime"] = realtime
    log.info("forecast_worker.startup", ml_timeout_s=settings.ml_api_timeout_s)


async def shutdown(ctx: dict) -> None:
    await ctx["http"].aclose()
    await ctx["db"].close()
    log.info("forecast_worker.shutdown")


def _redis_settings() -> RedisSettings:
    settings = get_settings()
    if not settings.redis_url:
        raise RuntimeError(
            "REDIS_URL is required for the arq forecast worker. "
            "Set it in backend/.env (e.g. redis://localhost:6379/0) and run "
            "`docker compose up -d redis`."
        )
    return RedisSettings.from_dsn(settings.redis_url)


class WorkerSettings:
    """arq entrypoint — `arq app.workers.forecast_worker.WorkerSettings`."""

    functions = [run_hybrid_forecast]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = _redis_settings()
    # Chronos inference is slow; allow generous headroom before arq aborts a job.
    job_timeout = 600
    max_jobs = 4
    keep_result = 3600
