from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.core.database import Database
from app.core.exceptions import SanketBaseError
from app.core.logging import configure_logging
from app.core.observability import configure_observability
from app.middleware.idempotency import IdempotencyMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.region_router import RegionRouterMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.tenant_context import TenantContextMiddleware
from app.middleware.usage_metering import UsageMeteringMiddleware
from app.realtime import get_connection_manager

log = structlog.get_logger(__name__)


async def _init_redis(redis_url: str | None):
    """Return an async Redis client if REDIS_URL is configured, else None."""
    if not redis_url:
        return None
    try:
        import redis.asyncio as aioredis  # type: ignore[import-untyped]

        client = aioredis.from_url(redis_url, decode_responses=True)
        await client.ping()
        log.info("startup.redis.connected", url=redis_url)
        return client
    except Exception as exc:
        log.warning("startup.redis.unavailable", error=str(exc))
        return None


@asynccontextmanager
async def lifespan(fastapi_app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings)

    # Side-effect import so SQLAlchemy registers every ORM model before
    # anything queries the database or seed runs.
    import app.models  # noqa: F401

    db = Database(settings)
    fastapi_app.state.db = db

    # Redis — shared client for rate limiting and WebSocket pub/sub
    redis_client = await _init_redis(settings.redis_url)
    fastapi_app.state.redis = redis_client
    if redis_client is None:
        log.warning(
            "startup.rate_limit.mode",
            mode="in-process",
            note="Set REDIS_URL for distributed rate limiting across replicas",
        )
    else:
        log.info("startup.rate_limit.mode", mode="redis")

    # Realtime: start the WebSocket connection manager + optional Redis pubsub
    manager = get_connection_manager(redis_url=settings.redis_url)
    await manager.startup()
    fastapi_app.state.realtime = manager

    # arq job queue — durable background execution for slow forecast runs.
    # Requires Redis; without it the forecast endpoint degrades to in-process.
    arq_pool = None
    if settings.redis_url:
        try:
            from arq import create_pool
            from arq.connections import RedisSettings

            arq_pool = await create_pool(RedisSettings.from_dsn(settings.redis_url))
            log.info("startup.arq.connected")
        except Exception as exc:
            log.warning("startup.arq.unavailable", error=str(exc))
    else:
        log.warning(
            "startup.arq.disabled",
            note="REDIS_URL unset — hybrid forecasts run in-process (not durable)",
        )
    fastapi_app.state.arq = arq_pool

    # Shared async HTTP client — connection pool reused across requests
    import httpx as _httpx

    http_client = _httpx.AsyncClient(
        timeout=settings.ml_api_timeout_s,
        limits=_httpx.Limits(max_keepalive_connections=20, max_connections=100),
    )
    fastapi_app.state.http = http_client
    log.info("startup.http_client.ready")

    # Phase 6: external signal ingestion pipeline (FRED / Google Trends / Reddit)
    from app.services.external_signals import SignalIngestionPipeline

    signal_pipeline = SignalIngestionPipeline(
        db=db,
        realtime=manager,
        poll_interval_s=getattr(settings, "signal_pipeline_interval_s", 900),
    )
    fastapi_app.state.signal_pipeline = signal_pipeline

    # Near-real-time Shopify sales poller (localhost-friendly live sales path)
    from app.services.integrations.shopify_poller import ShopifySalesPoller

    shopify_poller = ShopifySalesPoller(
        db=db,
        realtime=manager,
        poll_interval_s=settings.shopify_poll_interval_s,
        api_version=settings.shopify_api_version,
    )
    fastapi_app.state.shopify_poller = shopify_poller

    # ── Singleton background work, gated by a Redis leader lease ──────────────
    # These loops (signal ingest, Shopify poller, webhook retry) MUST run on
    # exactly one replica or they duplicate external API polling and webhook
    # retries. `run_as_leader` makes a single replica the leader; standbys take
    # over within the lease TTL if it dies. With no Redis the lock is a no-op and
    # the loops run in-process exactly as before (correct for single-node dev).
    import asyncio

    from app.core.distributed_lock import run_as_leader

    async def _run_singletons() -> None:
        """Runs only while this replica holds the leader lease."""
        from app.services import webhooks as wh

        if settings.signal_pipeline_enabled:
            await signal_pipeline.start()
        if settings.shopify_poll_enabled:
            await shopify_poller.start()
        log.info("leader.singletons.started")
        try:
            # The webhook-retry tick doubles as the leader heartbeat: while we
            # hold the lease we keep ticking; losing the lease ends the loop and
            # `run_as_leader` releases + re-contends.
            while True:
                if settings.webhook_retry_worker_enabled:
                    try:
                        async with db.session_no_rls() as session:
                            await wh.retry_worker_tick(session)
                    except Exception as exc:
                        log.error("webhook.retry_loop.error", error=str(exc))
                await asyncio.sleep(settings.webhook_retry_interval_s)
        finally:
            # Relinquish the singletons when we stop being the leader so the new
            # leader can own them without double-running.
            await signal_pipeline.stop()
            await shopify_poller.stop()
            log.info("leader.singletons.stopped")

    leader_task: asyncio.Task | None = asyncio.create_task(
        run_as_leader(
            redis_client,
            "background-singletons",
            _run_singletons,
            ttl_s=settings.worker_leader_lock_ttl_s,
            renew_interval_s=settings.worker_leader_renew_interval_s,
        )
    )
    fastapi_app.state.leader_task = leader_task

    healthy = await db.healthcheck()
    if not healthy:
        log.error("startup.db.unhealthy")
        # Do not raise — let the process start and surface errors on first request
    else:
        log.info("startup.db.ok")

        async def run_db_initialization() -> None:
            try:
                # Fail closed in production if the DB role can bypass RLS (superuser /
                # BYPASSRLS) or FORCE RLS is missing — tenant isolation would be off.
                await db.assert_tenant_isolation_enforced(strict=settings.is_production)
                await db.check_migration_version()
                # Self-healing backstop so a long-lived replica never runs out of
                # range partitions between CronJob ticks (best-effort, never fatal).
                await db.maintain_partitions()
                from app.core.database import seed_database_if_empty

                await seed_database_if_empty()
                log.info("startup.db_initialization.complete")
            except Exception as exc:
                log.error("startup.db_initialization.failed", error=str(exc))
                if settings.is_production and "tenant isolation" in str(exc):
                    log.critical("startup.db_initialization.isolation_violated.exiting")
                    import os

                    os._exit(1)

        asyncio.create_task(run_db_initialization())

    log.info(
        "startup.complete",
        env=settings.app_env,
        version=settings.app_version,
    )

    yield

    if leader_task is not None:
        leader_task.cancel()
        import contextlib

        with contextlib.suppress(asyncio.CancelledError):
            await leader_task
    if arq_pool is not None:
        await arq_pool.close()
    # Defensive: ensure the singletons are stopped even if we never held the lease.
    await signal_pipeline.stop()
    await shopify_poller.stop()
    await manager.shutdown()
    await http_client.aclose()
    if fastapi_app.state.redis is not None:
        await fastapi_app.state.redis.aclose()
    await db.close()
    log.info("shutdown.complete")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="SANKET API",
        description=(
            "Enterprise Multi-Industry Predictive Analytics & Supply Chain Optimization Platform"
        ),
        version=settings.app_version,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ── Middleware (order matters: outermost = last added) ───────────────────
    # Added innermost → outermost. On the way IN a request traverses them in the
    # reverse order it was added (CORS first, route last):
    #   CORS → security headers → metrics → rate limit → usage metering
    #        → region router → tenant context → idempotency → route
    # Idempotency is the INNERMOST app middleware so (a) tenant context has
    # already set request.state.tenant_id (keys are tenant-scoped) and (b) it
    # directly wraps the route — on a replay it returns the cached response
    # without ever invoking the handler, so no side effects re-run.
    app.add_middleware(
        IdempotencyMiddleware,
        ttl_s=settings.idempotency_ttl_s,
        enabled=settings.idempotency_enabled,
    )
    app.add_middleware(TenantContextMiddleware)
    app.add_middleware(RegionRouterMiddleware, deploy_region=settings.deploy_region)
    app.add_middleware(UsageMeteringMiddleware)
    app.add_middleware(
        RateLimitMiddleware,
        per_minute=settings.rate_limit_per_minute,
        trusted_proxy_count=settings.trusted_proxy_count,
    )
    if settings.metrics_enabled:
        configure_observability(app, settings)
    app.add_middleware(SecurityHeadersMiddleware, enable_hsts=settings.is_production)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=True,
        # Explicit allow-lists instead of "*": with credentials, a wildcard is
        # both unsafe and (per spec) ignored by browsers anyway.
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "X-Industry-Code",
            "X-Request-ID",
        ],
        expose_headers=["X-Request-ID"],
        max_age=600,
    )

    # ── Exception handlers ───────────────────────────────────────────────────
    @app.exception_handler(SanketBaseError)
    async def sanket_error_handler(request: Request, exc: SanketBaseError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=exc.headers or {},
        )

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled.exception", path=request.url.path, error=str(exc))
        return JSONResponse(
            status_code=500,
            content={"detail": "An unexpected error occurred"},
        )

    # ── Routers ──────────────────────────────────────────────────────────────
    from app.routers.anomaly import router as anomaly_router
    from app.routers.auth import router as auth_router
    from app.routers.billing import router as billing_router
    from app.routers.cross_industry import router as cross_industry_router
    from app.routers.demo_request import router as demo_request_router
    from app.routers.export import router as export_router
    from app.routers.financial import router as financial_router
    from app.routers.forecast_accuracy import router as forecast_accuracy_router
    from app.routers.forecasts import router as forecasts_router
    from app.routers.hybrid_forecast import router as hybrid_forecast_router
    from app.routers.industries.agrocenter import router as agrocenter_router
    from app.routers.industries.electronics import router as electronics_router
    from app.routers.industries.fashion import router as fashion_router
    from app.routers.industries.hardware import router as hardware_router
    from app.routers.industries.pharma import router as pharma_router
    from app.routers.industry_router import router as industry_router
    from app.routers.integrations import router as integrations_router
    from app.routers.integrations_hub import router as integrations_hub_router
    from app.routers.inventory import router as inventory_router
    from app.routers.invites import router as invites_router
    from app.routers.onboarding import router as onboarding_router
    from app.routers.planning import router as planning_router
    from app.routers.products import router as products_router
    from app.routers.sales_analytics import router as sales_analytics_router
    from app.routers.shortage_alerts import router as shortage_alerts_router
    from app.routers.signals import router as signals_router
    from app.routers.skus import router as skus_router
    from app.routers.trends import router as trends_router
    from app.routers.webhooks import router as webhooks_router
    from app.routers.websocket import router as ws_router

    api_prefix = "/api/v1"

    app.include_router(auth_router, prefix=api_prefix)
    app.include_router(industry_router, prefix=api_prefix)
    app.include_router(onboarding_router, prefix=api_prefix)
    app.include_router(planning_router, prefix=api_prefix)
    app.include_router(invites_router, prefix=api_prefix)
    app.include_router(products_router, prefix=api_prefix)
    app.include_router(skus_router, prefix=api_prefix)
    app.include_router(signals_router, prefix=api_prefix)
    app.include_router(fashion_router, prefix=api_prefix)
    app.include_router(electronics_router, prefix=api_prefix)
    app.include_router(pharma_router, prefix=api_prefix)
    app.include_router(agrocenter_router, prefix=api_prefix)
    app.include_router(hardware_router, prefix=api_prefix)
    app.include_router(demo_request_router, prefix=api_prefix)
    app.include_router(billing_router, prefix=api_prefix)
    app.include_router(webhooks_router, prefix=api_prefix)
    # Phase 6: trend signals, hybrid forecasts, shortage alerts
    app.include_router(trends_router, prefix=api_prefix)
    app.include_router(hybrid_forecast_router, prefix=api_prefix)
    app.include_router(shortage_alerts_router, prefix=api_prefix)
    # Analytics improvements
    app.include_router(cross_industry_router, prefix=api_prefix)  # before shortage_alerts catch-all
    app.include_router(anomaly_router, prefix=api_prefix)
    app.include_router(inventory_router, prefix=api_prefix)
    app.include_router(financial_router, prefix=api_prefix)
    app.include_router(sales_analytics_router, prefix=api_prefix)
    app.include_router(export_router, prefix=api_prefix)
    app.include_router(forecast_accuracy_router, prefix=api_prefix)
    app.include_router(forecasts_router, prefix=api_prefix)
    # Shopify (literal routes) must be registered before the Hub's generic
    # /integrations/{provider} routes so the dedicated flow isn't shadowed.
    app.include_router(integrations_router, prefix=api_prefix)
    app.include_router(integrations_hub_router, prefix=api_prefix)
    # WebSocket is mounted at /ws, not under /api/v1
    app.include_router(ws_router)

    # ── Health endpoints ─────────────────────────────────────────────────────
    @app.get("/health", tags=["ops"])
    async def health(request: Request) -> JSONResponse:
        """Minimal liveness probe for load balancer health checks.

        Returns only {"status": "ok" | "degraded"} — no version or environment
        information is exposed to unauthenticated callers. See /health/detailed
        for the full diagnostic view (requires authentication).
        """
        db_ok = await request.app.state.db.healthcheck()
        status_code = 200 if db_ok else 503
        return JSONResponse(
            status_code=status_code, content={"status": "ok" if db_ok else "degraded"}
        )

    @app.get("/api/v1/health", tags=["ops"])
    async def health_api(request: Request) -> JSONResponse:
        """Deep health check endpoint for external smoke testing.

        Verifies connectivity to the database and the ML inference service.
        """
        db_ok = await request.app.state.db.healthcheck()
        ml_ok = False
        try:
            response = await request.app.state.http.get(
                f"{settings.ml_api_url}/health", timeout=2.0
            )
            if response.status_code == 200:
                ml_ok = True
        except Exception:
            pass
        status = "ok" if (db_ok and ml_ok) else "degraded"
        status_code = 200 if status == "ok" else 503
        return JSONResponse(
            status_code=status_code,
            content={
                "status": status,
                "db": "ok" if db_ok else "unreachable",
                "ml": "ok" if ml_ok else "unreachable",
            },
        )

    @app.get("/health/detailed", tags=["ops"])
    async def health_detailed(request: Request) -> dict:
        """Full diagnostic health check. Requires an authenticated request.

        Returns version, environment, and per-subsystem statuses.
        """
        if getattr(request.state, "tenant_id", None) is None:
            # Allow internal callers (e.g. sidecar, ops tooling) via a header
            # secret set in deployment; reject everyone else.
            internal_token = request.headers.get("X-Internal-Token", "")
            ops_secret = getattr(settings, "ops_health_token", "") or ""
            if not ops_secret or internal_token != ops_secret:
                from fastapi import HTTPException

                raise HTTPException(status_code=401, detail="Authentication required")
        db_ok = await request.app.state.db.healthcheck()
        redis_ok = False
        if request.app.state.redis is not None:
            try:
                await request.app.state.redis.ping()
                redis_ok = True
            except Exception:
                pass
        return {
            "status": "ok" if db_ok else "degraded",
            "version": settings.app_version,
            "env": settings.app_env,
            "db": "ok" if db_ok else "unreachable",
            "redis": "ok" if redis_ok else "unavailable",
        }

    @app.get("/", tags=["ops"], include_in_schema=False)
    async def root() -> dict:
        return {"service": "SANKET API"}

    return app


app = create_app()
