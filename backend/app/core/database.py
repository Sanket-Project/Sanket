"""PostgreSQL async database layer.

Real SQLAlchemy 2.0 async engine over asyncpg. Replaces the prior Firestore
adapter so Phase 1–6 schemas (RLS, partitioning, JSONB, pgvector) actually
work end-to-end.

`Database.session(tenant_id)` opens a transaction and runs:
    SET LOCAL app.current_tenant_id = :tenant_id

Every RLS policy in sql/003_rls_policies.sql + sql/006_*.sql reads that
setting, so per-tenant isolation is enforced at the DB layer for free.

`Database.session_no_rls()` opens a transaction without setting the tenant
GUC — used by background workers (signal ingest, webhook retry) that need
to write across tenants.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import Settings, get_settings

log = structlog.get_logger(__name__)


class Base(DeclarativeBase):
    """Shared declarative base for every ORM model."""


class Database:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        connect_args: dict = {}
        if settings.db_pgbouncer_mode:
            # PgBouncer transaction pooling is incompatible with asyncpg's
            # server-side prepared statements. Disable both the asyncpg statement
            # cache and SQLAlchemy's prepared-statement cache so every statement
            # is sent inline and safe to run on any pooled server connection.
            connect_args = {
                "statement_cache_size": 0,
                "prepared_statement_cache_size": 0,
            }
        self._engine: AsyncEngine = create_async_engine(
            settings.database_url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout,
            pool_pre_ping=True,
            echo=settings.db_echo,
            connect_args=connect_args,
        )
        self._sessionmaker: async_sessionmaker[AsyncSession] = async_sessionmaker(
            bind=self._engine,
            expire_on_commit=False,
            autoflush=False,
        )

    @asynccontextmanager
    async def session(self, tenant_id: str | None = None) -> AsyncIterator[AsyncSession]:
        """Open a tenant-scoped session.

        If `tenant_id` is provided, `SET LOCAL app.current_tenant_id` is run
        on the underlying connection so RLS policies activate. The setting
        only lives for the transaction (LOCAL), so connection pool reuse is
        safe.
        """
        async with self._sessionmaker() as session:
            try:
                async with session.begin():
                    if tenant_id is not None:
                        await session.execute(
                            text("SELECT set_config('app.current_tenant_id', :tid, true)"),
                            {"tid": str(tenant_id)},
                        )
                    yield session
            except Exception:
                # session.begin() context handles rollback automatically
                raise

    @asynccontextmanager
    async def session_no_rls(self) -> AsyncIterator[AsyncSession]:
        """Open a session WITHOUT setting the tenant GUC, but with RLS bypassed.

        Used for cross-tenant background work (signal ingest, retry workers,
        seeding, login). Sets the local `app.bypass_rls` GUC to 'true'.
        """
        async with self._sessionmaker() as session:
            try:
                async with session.begin():
                    await session.execute(text("SELECT set_config('app.bypass_rls', 'true', true)"))
                    yield session
            except Exception:
                raise

    async def healthcheck(self) -> bool:
        try:
            async with self._engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception as exc:
            log.error("database.healthcheck.failed", error=str(exc))
            return False

    async def assert_tenant_isolation_enforced(self, *, strict: bool) -> None:
        """Verify the runtime DB role cannot bypass row-level security.

        Tenant isolation depends on connecting as a role that is **not** a
        superuser and does **not** have BYPASSRLS — otherwise every RLS policy
        (even with FORCE ROW LEVEL SECURITY) is silently ignored and tenants can
        read each other's data. This is a common production footgun: pointing
        ``DATABASE_URL`` at a managed provider's admin/`postgres` role.

        In production (``strict=True``) a privileged role, or a core tenant table
        that is missing FORCE RLS, raises and aborts startup (fail-closed). In
        dev it logs a loud warning so the developer notices without being blocked.
        """
        try:
            async with self._engine.connect() as conn:
                role = (
                    await conn.execute(
                        text(
                            "SELECT rolsuper, rolbypassrls FROM pg_roles "
                            "WHERE rolname = current_user"
                        )
                    )
                ).first()
                forced = await conn.scalar(
                    text(
                        "SELECT relforcerowsecurity FROM pg_class "
                        "WHERE oid = 'public.tenants'::regclass"
                    )
                )
        except Exception as exc:
            # Never let an introspection hiccup itself cause an outage; surface it.
            log.warning("database.rls_check.skipped", error=str(exc))
            return

        is_super = bool(role[0]) if role else False
        is_bypass = bool(role[1]) if role else False
        problems: list[str] = []
        if is_super:
            problems.append("the role is a SUPERUSER (bypasses RLS)")
        if is_bypass:
            problems.append("the role has BYPASSRLS (bypasses RLS)")
        if forced is False:
            problems.append("the 'tenants' table is missing FORCE ROW LEVEL SECURITY")

        if not problems:
            log.info("database.rls_check.ok")
            return

        detail = "; ".join(problems)
        if strict:
            raise RuntimeError(
                "Refusing to start: tenant isolation is NOT enforced — "
                f"{detail}. Point DATABASE_URL at a NOSUPERUSER NOBYPASSRLS role "
                "(e.g. sanket_app) and run migrations so FORCE RLS is applied."
            )
        log.warning(
            "database.rls_check.unenforced",
            detail=detail,
            note="Tenant isolation is NOT enforced with this DB role/config.",
        )

    async def check_migration_version(self) -> bool:
        """Compare the DB's applied Alembic revision against the migration head.

        Logs a loud warning when the database is behind the latest migration
        (a common dev-machine footgun, since only the deploy pipeline runs
        `alembic upgrade head` automatically). Returns True when up to date.

        Never raises — a check failure should not block startup.
        """
        from pathlib import Path

        from alembic.config import Config
        from alembic.script import ScriptDirectory

        try:
            # backend/app/core/database.py -> backend/alembic.ini
            ini_path = Path(__file__).resolve().parents[2] / "alembic.ini"
            script = ScriptDirectory.from_config(Config(str(ini_path)))
            heads = set(script.get_heads())

            async with self._engine.connect() as conn:
                result = await conn.execute(text("SELECT version_num FROM alembic_version"))
                applied = {row[0] for row in result}
        except Exception as exc:
            log.warning("database.migration_check.skipped", error=str(exc))
            return True

        if applied == heads:
            log.info("database.migration_check.ok", revision=sorted(heads))
            return True

        log.warning(
            "database.migration_check.behind",
            applied=sorted(applied),
            expected=sorted(heads),
            hint="Run: python -m alembic upgrade head  (from the backend/ directory)",
        )
        return False

    async def maintain_partitions(self) -> None:
        """Self-healing partition maintenance (best-effort, never fatal).

        Calls ``sanket_maintain_partitions()`` (added in migration 0013) so the
        rolling window of quarterly partitions for ``historical_sales`` /
        ``forecast_results`` is extended whenever a replica boots. The scheduled
        CronJob is the primary mechanism; this is a backstop so a long-running
        deployment can't silently run out of partitions between cron ticks.

        Swallows every error (e.g. the function not yet present on an un-migrated
        DB, or a permission issue) — partition maintenance must never block boot.
        """
        try:
            async with self._engine.connect() as conn:
                result = await conn.execute(
                    text("SELECT parent, created FROM sanket_maintain_partitions()")
                )
                created = {row[0]: int(row[1]) for row in result}
                await conn.commit()
            total = sum(created.values())
            if total:
                log.info("database.partitions.maintained", created=created)
            else:
                log.info("database.partitions.ok", note="all partitions already present")
        except Exception as exc:
            log.warning("database.partitions.maintenance_skipped", error=str(exc))

    async def close(self) -> None:
        await self._engine.dispose()
        log.info("database.engine.disposed")


# ─────────────────────────────────────────────────────────────────────────
# Seeding — runs once on startup if the tenants table is empty
# ─────────────────────────────────────────────────────────────────────────


async def seed_database_if_empty() -> None:
    """Seed a dev tenant + users + industry profiles on a fresh database.

    Idempotent: checks for the `sanket-dev` tenant slug and bails if found.
    """
    import uuid

    from sqlalchemy import select

    from app.core.security import hash_password
    from app.models.enums import IndustryCode, TenantStatus, TenantTier, UserRole
    from app.models.tenant import Tenant, User

    settings = get_settings()
    db = Database(settings)

    try:
        async with db.session_no_rls() as session:
            existing = await session.scalar(select(Tenant).where(Tenant.slug == "sanket-dev"))
            if existing is not None:
                log.info("database.seed.skipped", reason="sanket-dev already exists")
            else:
                log.info("database.seed.start")
                tenant_id = uuid.uuid4()
                tenant = Tenant(
                    id=tenant_id,
                    slug="sanket-dev",
                    display_name="SANKET Dev Tenant",
                    tier=TenantTier.growth,
                    status=TenantStatus.active,
                    industries=["fashion", "electronics", "pharma", "agrocenter", "hardware"],
                    active_industry=IndustryCode.fashion,
                    max_skus=999999,
                    max_users=50,
                    data_retention_days=1825,
                )
                session.add(tenant)

                pwd = hash_password("Dev@Sanket2024!", settings)
                session.add(
                    User(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        email="owner@sanket-dev.com",
                        password_hash=pwd,
                        full_name="Platform Owner",
                        role=UserRole.owner,
                        active_industry=IndustryCode.fashion,
                        is_active=True,
                    )
                )
                session.add(
                    User(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        email="admin@sanket-dev.com",
                        password_hash=pwd,
                        full_name="Platform Admin",
                        role=UserRole.admin,
                        active_industry=IndustryCode.fashion,
                        is_active=True,
                    )
                )
                # Dedicated least-privilege account backing the public "Try the
                # Sandbox" flow (settings.sandbox_email). It is a VIEWER, not the
                # owner/admin above, so an anonymous visitor who starts a sandbox
                # session cannot mutate shared demo data, manage members, or reach
                # billing. No password_hash: in Firebase mode a passwordless custom
                # token is minted; in dev mode a dev token is minted server-side.
                session.add(
                    User(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        email="sandbox@sanket-dev.com",
                        password_hash=None,
                        full_name="Sandbox Guest",
                        role=UserRole.viewer,
                        active_industry=IndustryCode.fashion,
                        is_active=True,
                    )
                )
                log.info("database.seed.completed", tenant_id=str(tenant_id))

        # NOTE: demo product/SKU/inventory catalog seeding has been intentionally
        # removed. A fresh database now starts with an empty catalog so the app is
        # exercised against real data only (load via CSV upload or a connector).
        # Only the dev tenant + login users + industry profiles are seeded above,
        # which are required for local authentication.
    finally:
        await db.close()
