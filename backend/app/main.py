from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.core.database import Database
from app.core.entitlement import require_active_subscription
from app.core.exceptions import SanketBaseError
from app.core.industry_scope import require_industry
from app.core.logging import configure_logging
from app.core.observability import configure_observability
from app.middleware.idempotency import IdempotencyMiddleware
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.region_router import RegionRouterMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.tenant_context import TenantContextMiddleware
from app.middleware.usage_metering import UsageMeteringMiddleware
from app.models.enums import IndustryCode
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
            last_digest_tick = 0.0
            while True:
                if settings.webhook_retry_worker_enabled:
                    try:
                        async with db.session_no_rls() as session:
                            await wh.retry_worker_tick(session)
                    except Exception as exc:
                        log.error("webhook.retry_loop.error", error=str(exc))

                # The morning WhatsApp digest rides the same leader loop but on
                # its own (much slower) cadence — the retry tick runs every 30s
                # and scanning every tenant that often would be wasteful.
                if settings.whatsapp_digest_worker_enabled:
                    now = asyncio.get_running_loop().time()
                    if now - last_digest_tick >= settings.whatsapp_digest_tick_s:
                        last_digest_tick = now
                        try:
                            from app.workers import whatsapp_digest

                            await whatsapp_digest.tick(
                                db, settings, getattr(fastapi_app.state, "http", None)
                            )
                        except Exception as exc:
                            log.error("whatsapp.digest_loop.error", error=str(exc))

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
    #
    #   CORS → SecurityHeaders → metrics → RateLimit(ip_only=True)
    #        → UsageMetering → RegionRouter → TenantContext
    #        → RateLimit(ip_only=False) → Idempotency → route
    #
    # RateLimitMiddleware is registered TWICE — a deliberate split:
    #
    #   ip_only=True  (outermost, before auth): enforces the per-IP bucket.
    #     This must run BEFORE TenantContextMiddleware so unauthenticated floods
    #     are dropped before any Firebase token verification occurs. With
    #     firebase_check_revoked=True, skipping this gate would mean every flood
    #     request triggers a Firebase round-trip — a DoS amplifier.
    #
    #   ip_only=False (just inside TenantContext, after auth): enforces the
    #     per-user and heavy-endpoint buckets. These require request.state.user_id,
    #     which TenantContextMiddleware populates. Running here means a user who
    #     approaches from two different IPs still hits a single shared quota keyed
    #     on their user_id — the correct multi-IP enforcement.
    #
    # Idempotency is the INNERMOST app middleware so (a) tenant context has
    # already set request.state.tenant_id (keys are tenant-scoped) and (b) it
    # directly wraps the route — on a replay it returns the cached response
    # without ever invoking the handler, so no side effects re-run.
    app.add_middleware(
        IdempotencyMiddleware,
        ttl_s=settings.idempotency_ttl_s,
        enabled=settings.idempotency_enabled,
    )
    # Per-user + heavy-endpoint buckets — MUST be inside (added before) TenantContext
    # so that request.state.user_id is already populated when this runs inbound.
    app.add_middleware(
        RateLimitMiddleware,
        ip_only=False,
        per_user_per_minute=settings.rate_limit_per_user_per_minute,
        heavy_per_minute=settings.rate_limit_heavy_per_minute,
        heavy_fail_closed=settings.rate_limit_heavy_fail_closed,
    )
    app.add_middleware(TenantContextMiddleware)
    app.add_middleware(RegionRouterMiddleware, deploy_region=settings.deploy_region)
    app.add_middleware(UsageMeteringMiddleware)
    # Per-IP bucket — MUST be outside (added after) TenantContext so unauthenticated
    # floods are dropped before Firebase verification runs.
    app.add_middleware(
        RateLimitMiddleware,
        ip_only=True,
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

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Return validation errors without echoing what the caller submitted.

        FastAPI's default handler serialises the offending value under
        `input`. On any endpoint that takes a password — signup, dev-login,
        password reset — that puts the plaintext password in the response
        body, and from there into browser devtools, error-tracking SDKs,
        proxy logs, CDN logs, and support screenshots. A 422 is a routine
        client mistake; it must not be a credential disclosure.

        `ctx` goes too: for several pydantic error types it carries the
        rejected value or an exception object built from it.

        `loc`, `msg` and `type` are preserved, because the frontend maps
        errors onto form fields by `loc`. Removing `input` is not a
        behavioural change for any correct client.
        """
        safe_errors = [
            {"type": err.get("type", ""), "loc": err.get("loc", []), "msg": err.get("msg", "")}
            for err in exc.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": safe_errors})

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
    from app.routers.data_quality import router as data_quality_router
    from app.routers.decisions import router as decisions_router
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
    from app.routers.locations import router as locations_router
    from app.routers.invites import router as invites_router
    from app.routers.notifications import router as notifications_router
    from app.routers.onboarding import router as onboarding_router
    from app.routers.planning import router as planning_router
    from app.routers.products import router as products_router
    from app.routers.roi import router as roi_router
    from app.routers.sales_analytics import router as sales_analytics_router
    from app.routers.scenarios import router as scenarios_router
    from app.routers.shortage_alerts import router as shortage_alerts_router
    from app.routers.signals import router as signals_router
    from app.routers.skus import router as skus_router
    from app.routers.trends import router as trends_router
    from app.routers.webhooks import router as webhooks_router
    from app.routers.websocket import router as ws_router

    api_prefix = "/api/v1"

    # ── Entitlement ──────────────────────────────────────────────────────────
    # Every router carrying tenant data is gated on a live subscription. This
    # is THE paywall; SubscriptionGate.tsx is only its presentation. Applied at
    # include_router so a new endpoint inherits the gate by construction rather
    # than by the author remembering a decorator.
    #
    # Ungated, deliberately — each of these must work for a tenant that has not
    # paid, or the tenant can never reach the point of paying:
    #   auth          sign in / sign up / session bootstrap
    #   industry      the shell and the paywall render from /industry/profile
    #   onboarding    setup precedes purchase
    #   invites       onboarding's team step calls it
    #   planning      onboarding's calendar step reads and writes /planning/config;
    #                 it is tenant configuration and returns no product value
    #   demo_request  public lead capture, pre-tenant
    #   billing       gating the checkout behind a subscription is a deadlock
    #   websocket     realtime is push-only and carries no data the REST API
    #                 does not already gate; see docs/audit/05
    #
    # The boundary is deliberately "you can set up and put data in, you cannot
    # get anything out": onboarding's file upload stays open (the wizard runs
    # before the paywall), while every read of products, SKUs, forecasts,
    # signals and analytics is gated — so an unsubscribed tenant can finish
    # setup and import a catalogue, and see none of it.
    gated = [require_active_subscription()]

    app.include_router(auth_router, prefix=api_prefix)
    app.include_router(industry_router, prefix=api_prefix)
    app.include_router(onboarding_router, prefix=api_prefix)
    app.include_router(planning_router, prefix=api_prefix)
    app.include_router(invites_router, prefix=api_prefix)
    app.include_router(products_router, prefix=api_prefix, dependencies=gated)
    app.include_router(skus_router, prefix=api_prefix, dependencies=gated)
    app.include_router(signals_router, prefix=api_prefix, dependencies=gated)
    # ── Industry scope ───────────────────────────────────────────────────────
    # A *different* boundary from tenant isolation: RLS says whose data, this
    # says which modules. Applied here rather than per-endpoint for the same
    # reason as the paywall above — every handler in these routers already
    # hardcodes its own industry in each query and none of them compared it to
    # the caller's, so a fashion tenant used to get a 200 from /pharma/overview.
    # Registering the gate once means a new endpoint inherits it by
    # construction, because its author never writes it.
    for _router, _industry in (
        (fashion_router, IndustryCode.fashion),
        (electronics_router, IndustryCode.electronics),
        (pharma_router, IndustryCode.pharma),
        (agrocenter_router, IndustryCode.agrocenter),
        (hardware_router, IndustryCode.hardware),
    ):
        # Industry check first, paywall second. The reason a fashion workspace
        # cannot read pharma has nothing to do with billing, so the answer must
        # not change from 403 to 402 depending on their subscription state.
        app.include_router(
            _router,
            prefix=api_prefix,
            dependencies=[require_industry(_industry), *gated],
        )
    app.include_router(demo_request_router, prefix=api_prefix)
    app.include_router(billing_router, prefix=api_prefix)
    app.include_router(webhooks_router, prefix=api_prefix, dependencies=gated)
    # Phase 6: trend signals, hybrid forecasts, shortage alerts
    app.include_router(trends_router, prefix=api_prefix, dependencies=gated)
    app.include_router(hybrid_forecast_router, prefix=api_prefix, dependencies=gated)
    app.include_router(shortage_alerts_router, prefix=api_prefix, dependencies=gated)
    # Analytics improvements
    # (cross-industry shortage correlation removed: it cannot be offered to a
    #  workspace scoped to one industry, and a permanently-403 endpoint is worse
    #  than no endpoint. Recoverable from git history if entitlements ever
    #  make it meaningful.)
    app.include_router(anomaly_router, prefix=api_prefix, dependencies=gated)
    app.include_router(inventory_router, prefix=api_prefix, dependencies=gated)
    app.include_router(locations_router, prefix=api_prefix, dependencies=gated)
    app.include_router(financial_router, prefix=api_prefix, dependencies=gated)
    app.include_router(sales_analytics_router, prefix=api_prefix, dependencies=gated)
    app.include_router(export_router, prefix=api_prefix, dependencies=gated)
    app.include_router(forecast_accuracy_router, prefix=api_prefix, dependencies=gated)
    app.include_router(forecasts_router, prefix=api_prefix, dependencies=gated)
    # Decision engine, digital twin and the ROI ledger built on top of them.
    app.include_router(decisions_router, prefix=api_prefix, dependencies=gated)
    app.include_router(scenarios_router, prefix=api_prefix, dependencies=gated)
    app.include_router(roi_router, prefix=api_prefix, dependencies=gated)
    # Data quality is gated with the rest: it reads the tenant's ingested data.
    # Onboarding's own readiness view lives on the ungated onboarding router,
    # so a tenant that has not paid can still see why their import is failing.
    app.include_router(data_quality_router, prefix=api_prefix, dependencies=gated)
    app.include_router(notifications_router, prefix=api_prefix, dependencies=gated)
    # Shopify (literal routes) must be registered before the Hub's generic
    # /integrations/{provider} routes so the dedicated flow isn't shadowed.
    # The Shopify webhook and the push-ingest endpoint are in the auth
    # middleware's public set, and onboarding's two upload paths are in
    # entitlement._SETUP_PATHS — the dependency short-circuits on all of them.
    app.include_router(integrations_router, prefix=api_prefix, dependencies=gated)
    app.include_router(integrations_hub_router, prefix=api_prefix, dependencies=gated)
    # WebSocket is mounted at /ws, not under /api/v1
    app.include_router(ws_router)

    # Standard Web Checkout direct /api/ routes
    from app.routers.billing import create_order as _create_order_handler
    from app.routers.billing import verify_payment as _verify_payment_handler

    app.post("/api/create-order", tags=["billing"])(_create_order_handler)
    app.post("/api/verify-payment", tags=["billing"])(_verify_payment_handler)

    # ── Health endpoints ─────────────────────────────────────────────────────
    @app.get("/health", tags=["ops"])
    async def health(request: Request) -> JSONResponse:
        """Minimal liveness probe for load balancer health checks.

        Returns liveness plus `git_sha`, the commit this build was produced
        from. The SHA is here rather than only on /health/detailed so that a
        deploy smoke test, a CI job, or a human with curl can confirm what is
        actually running without needing a token — the gap that let two rounds
        of payment fixes be reviewed as "shipped" while the running build
        predated all of them.

        Everything else (version, environment, per-subsystem status) stays
        behind /health/detailed. Note the tradeoff: a commit SHA fingerprints
        the exact build. That is the point, and it is also disclosure. Move
        this line to /health/detailed if you would rather not publish it.
        """
        db_ok = await request.app.state.db.healthcheck()
        status_code = 200 if db_ok else 503
        return JSONResponse(
            status_code=status_code,
            content={
                "status": "ok" if db_ok else "degraded",
                "git_sha": settings.git_sha,
            },
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
                "git_sha": settings.git_sha,
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
        # Schema drift, queryable rather than buried in a boot-time warning.
        # check_migration_version() already computes this at startup and only
        # logs it, which is how the database sat one migration behind long
        # enough that every read of the `plans` table 500'd and the cause was
        # attributed to application code for two audit rounds. Never raises.
        migrations_ok = await request.app.state.db.check_migration_version()
        return {
            "status": "ok" if db_ok else "degraded",
            "version": settings.app_version,
            "git_sha": settings.git_sha,
            "env": settings.app_env,
            "db": "ok" if db_ok else "unreachable",
            "redis": "ok" if redis_ok else "unavailable",
            "migrations": "ok" if migrations_ok else "behind",
        }

    @app.get("/", tags=["ops"], include_in_schema=False)
    async def root() -> dict:
        return {"service": "SANKET API"}

    return app


app = create_app()
