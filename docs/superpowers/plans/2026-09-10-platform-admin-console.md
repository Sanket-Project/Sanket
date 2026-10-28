# SANKET Platform Admin Console — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the internal operator console at `/admin` (backed by `/api/v1/admin`) that lets SANKET staff create, onboard, operate and audit customer tenants without weakening RLS tenant isolation or the industry boundary.

**Architecture:** Operators are users of one flagged operator tenant; a `platform_admins` row, checked in the database on every admin request (plus MFA in production), makes them platform admins. Per-tenant admin work runs in `Database.session(tenant_id)` so RLS scopes it to the tenant in the URL; cross-tenant listings use a database-enforced read-only wrapper over the existing bypass session. Every platform action is audited fail-closed and mirrored into the customer's own `audit_log`; customer data views require a time-limited support session.

**Tech Stack:** FastAPI, SQLAlchemy 2 async + asyncpg, Alembic, PostgreSQL 16 (RLS), Redis/arq, pytest + testcontainers; React 18 + Vite + TypeScript + Tailwind, TanStack Query, zustand, Vitest + Testing Library, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-10-platform-admin-console-design.md` (read it first; this plan argues from it).

## Global Constraints

- Branch `feat/platform-admin-console`. Migration `0022` has `down_revision = "0021"`.
- Backend: Python ≥ 3.12 target (`ruff` `target-version = "py312"`, line length 100). Run everything through `uv run` from `backend/`.
- Never connect application code as a superuser; the only cross-tenant path is `Database.session_no_rls(...)`, and admin code reaches it only via `services/admin/data_access.py`.
- Per-tenant admin work runs in `Database.session(str(tenant_id))` via `tenant_scope()`. Tenant creation is the single documented exception (bypass session, like `/auth/signup`).
- `platform_audit_events` and `audit_log` stay append-only. Platform audit writes are fail-closed (never wrapped in try/except on the success path).
- Admin responses are explicit Pydantic models. Never return: `password_hash`, `mfa_secret`, `firebase_uid`, `integration_connections.state`, `access_token_encrypted`, `token_hash`, push-token hashes.
- Customer roles `owner/admin/analyst/viewer` are untouched. Platform roles are `platform_super_admin`, `platform_admin`, `platform_support` — exact strings.
- Customer API behaviour unchanged except the deny-only `suspended`/`cancelled` checks (spec §6.4).
- The 402 paywall (`require_active_subscription`) is NOT applied to `/api/v1/admin`; admin routes never return 402.
- Support sessions: reason ≥ 10 chars, `1 ≤ minutes ≤ PLATFORM_SUPPORT_SESSION_MAX_MINUTES` (default and hard cap 120). The 403 detail for a missing session is exactly `support_session_required`.
- Frontend: import icons only from `@/components/ui/icons`. No new npm dependencies. No edits to `frontend/src/pages/Login.tsx`.
- Fail honestly: no fabricated metrics; unavailable data is labelled unavailable.
- Env vars (exact names): `PLATFORM_OPERATOR_TENANT_SLUG` (default `sanket-platform`), `PLATFORM_ADMIN_REQUIRE_MFA` (unset = on in production), `PLATFORM_SUPPORT_SESSION_MAX_MINUTES` (default 120), `VITE_PLATFORM_TENANT_SLUG` (default `sanket-platform`).
- Commit messages end with `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

## Spec amendment (made while planning, applied in Task 1.1)

Spec §6.3 said all three platform tables get one policy `USING (bypass_rls()) WITH CHECK (bypass_rls())`. That makes the fail-closed audit impossible: tenant mutations run in a tenant-scoped session (bypass off), so they could not insert their own `platform_audit_events` row in the same transaction. Resolution:

- `platform_audit_events`: `FOR SELECT USING (bypass_rls())` and `FOR INSERT WITH CHECK (true)`; no UPDATE/DELETE policy (plus rules and SELECT/INSERT-only grants). Any application session can *append* a platform event; only privileged sessions can *read* them.
- `platform_admins`, `support_access_sessions`: unchanged — privileged sessions only.
- Platform bookkeeping (support session open/end, read audits, denied/failed events, tenant creation) runs in a writable bypass session reached only through `data_access.platform_write(principal)`.

The spec file is updated in Task 1.1, Step 7.

## File map

**Backend — create**

| File | Responsibility |
|---|---|
| `backend/alembic/versions/0022_platform_admin_console.py` | Operator flag, platform tables, RLS, grants, run/invite columns |
| `backend/app/models/platform.py` | `PlatformRole`, `PlatformAdmin`, `PlatformAuditEvent`, `SupportAccessSession` |
| `backend/app/core/platform_authz.py` | Permissions, `PlatformPrincipal`, `require_platform_role`, `require_platform_admin`, `require_permission`, principal aliases |
| `backend/app/schemas/admin.py` | Every `/admin` request/response model |
| `backend/app/services/admin/__init__.py` | Package marker |
| `backend/app/services/admin/data_access.py` | `platform_read`, `platform_write`, `tenant_scope` |
| `backend/app/services/admin/audit.py` | `record_platform_event`, `record_read_event`, `record_best_effort` |
| `backend/app/services/admin/operator.py` | `ensure_operator_tenant`, `grant_platform_role`, `deactivate_platform_role` |
| `backend/app/services/admin/directory.py` | Tenant rows, filters, search, users directory |
| `backend/app/services/admin/metrics.py` | Dashboard, notifications, usage |
| `backend/app/services/admin/tenants.py` | Overview, lifecycle, profile, industry |
| `backend/app/services/admin/users.py` | Tenant users, invites, roles, revocation |
| `backend/app/services/admin/billing.py` | Admin billing over `SubscriptionManager` |
| `backend/app/services/admin/data.py` | Data summary, validate/import on behalf |
| `backend/app/services/admin/jobs.py` | Job list/detail, trigger, retry |
| `backend/app/services/admin/support.py` | Support sessions + gate dependency |
| `backend/app/services/admin/onboarding.py` | Checklist derivation, mark operational |
| `backend/app/services/admin/health.py` | Component checks |
| `backend/app/services/admin/revocation.py` | Firebase refresh-token revocation fan-out |
| `backend/app/services/industry_correction.py` | `lock_reason`, `correct_industry` (extracted) |
| `backend/app/services/invites.py` | `create_invite` (extracted) |
| `backend/app/services/integrations/upload.py` | `ingest_upload` (extracted) |
| `backend/app/routers/admin/__init__.py` | `build_admin_router()` |
| `backend/app/routers/admin/{session,dashboard,search,tenants,users,billing,usage,data,integrations,jobs,signals,support,audit,health}.py` | One router per area |
| `backend/scripts/create_platform_admin.py` | Bootstrap / deactivate CLI |
| `backend/tests/admin_factories.py` | Test builders + token minting |
| `backend/tests/test_platform_schema.py`, `test_platform_authz.py`, `test_admin_route_guard.py`, `test_admin_audit.py`, `test_admin_*.py`, `test_cross_tenant_isolation.py`, `test_admin_secrets.py` | Tests |

**Backend — modify**

| File | Change |
|---|---|
| `backend/app/config.py` | Platform settings + `platform_admin_mfa_required` |
| `backend/app/core/database.py` | `session_no_rls(read_only=...)`, `tenant_isolation_problems()` |
| `backend/app/core/firebase_auth.py` | Surface `firebase.sign_in_second_factor` as `mfa` |
| `backend/app/middleware/tenant_context.py` | `request.state.auth_second_factor` |
| `backend/app/middleware/rate_limit.py` | Admin writes → heavy bucket |
| `backend/app/core/entitlement.py` | `evaluate_entitlement`, suspended/cancelled deny |
| `backend/app/routers/auth.py` | Refuse `cancelled` where `suspended` is refused |
| `backend/app/routers/industry_router.py` | Use `services/industry_correction.py` |
| `backend/app/routers/invites.py` | Use `services/invites.py` |
| `backend/app/routers/hybrid_forecast.py`, `backend/app/services/hybrid_forecast.py` | `enqueue_hybrid_run` |
| `backend/app/routers/integrations_hub.py` | Use `ingest_upload` |
| `backend/app/services/integrations/file_import.py` | `RowError.kind`, `validate_rows` |
| `backend/app/services/billing/subscription_manager.py` | `activate_manual_contract` |
| `backend/app/workers/forecast_worker.py` | `health_check_interval = 60` |
| `backend/app/models/{tenant,invite,trend,__init__}.py` | New columns / registration |
| `backend/app/main.py` | Include admin router (no paywall) |

**Frontend — create**: `src/api/admin.ts`, `src/types/admin.ts`, `src/hooks/usePlatformAdmin.ts`, `src/components/admin/*` (AdminRoute, AdminLayout, shared UI), `src/pages/admin/*` (AdminApp, login, security, dashboard, tenants, tenant detail + tabs, onboarding, users, subscriptions, usage, integrations, jobs, health, audit), `e2e/admin-console.spec.ts`.

**Frontend — modify**: `src/App.tsx` (one lazy route), `src/api/client.ts` (`skipErrorToast` opt-out), `frontend/.env.example` if present.

**Docs — create/modify**: `docs/ADMIN_CONSOLE.md`, `.env.example`, `infra/kubernetes/base/backend.yaml` (env), `docs/ARCHITECTURE.md` (pointer).

## Conventions every task follows

- **Backend tests:** from `backend/`, `uv run pytest tests/<file>.py -v`. Docker must be running (testcontainers starts `pgvector/pgvector:pg16` and runs `alembic upgrade head`). The whole schema is rebuilt per test session, so a new migration is picked up automatically.
- **Shared DB across tests:** tests share one database. Always create uniquely-named rows (`uuid4().hex[:8]` suffix) and assert relative facts, never global counts.
- **Frontend tests:** from `frontend/`, `npx vitest run <path>`.
- **TDD:** each task writes the failing test first and runs it to see the expected failure before implementing.
- **Commit** at the end of every task with the listed files only (`git add <files>`; never `git add -A`).

---

# M0 — Baseline

### Task 0.1: Record the pre-change test baseline

**Files:**
- Create: `docs/audit/2026-09-10-admin-console-baseline.md`

- [ ] **Step 1: Run the backend suite and capture the summary**

Run (from `backend/`): `uv run pytest -q -p no:cacheprovider 2>&1 | tail -30`
Expected: a pass/fail summary line. Copy the summary and the names of any failing tests.

- [ ] **Step 2: Run the frontend checks and capture results**

Run (from `frontend/`): `npm run typecheck; npm run lint; npm test -- --reporter=dot`
Expected: exit codes and failing test names (if any).

- [ ] **Step 3: Write the baseline file**

```markdown
# Admin console — pre-change baseline (2026-09-10)

Branch `feat/platform-admin-console` at `3dba120`, before any admin-console code.

## Backend (`uv run pytest -q`)
<paste summary line>
Failing before any change:
- <test ids, or "none">

## Frontend
- typecheck: <exit code / errors>
- lint: <exit code / error count>
- vitest: <summary / failing tests>

## Known pre-existing E2E failures (from project notes)
- e2e/billing.spec.ts: "display plan options", "show current subscription status",
  "deny billing access to viewer role" — failing on main as of 2026-08-31.
```

- [ ] **Step 4: Commit**

```bash
git add docs/audit/2026-09-10-admin-console-baseline.md
git commit -m "docs(audit): record test baseline before admin console work"
```

---

# Milestones (re-cut from spec §13 for dependency order — scope unchanged)

| | Scope |
|---|---|
| M0 | Baseline |
| M1 | Backend foundation: migration, authz, audit, data access, admin router, bootstrap CLI |
| M2 | Backend read side: directory, overview, users, integrations, signals, jobs, support sessions + gated views, platform audit, dashboard, notifications, search, health |
| M3 | Frontend foundation + read pages: client opt-out, admin API/types, AdminRoute, login + MFA + security, shell with search/notifications, dashboard, tenants, tenant detail (read tabs), users, integrations, jobs, health, audit |
| M4 | Tenant lifecycle, suspension enforcement, industry, users/invites/roles (backend + frontend) |
| M5 | Billing and usage (backend + frontend) |
| M6 | Onboarding: validate/import, forecast trigger/retry, readiness, wizard, mark operational (backend + frontend) |
| M7 | Isolation + secrets suites, Chandler E2E, docs, deployment checks, full verification, reviews |

# M1 — Backend foundation

### Task 1.1: Migration 0022 and platform models

**Files:**
- Create: `backend/alembic/versions/0022_platform_admin_console.py`
- Create: `backend/app/models/platform.py`
- Modify: `backend/app/models/tenant.py` (add `is_operator`, `home_region`)
- Modify: `backend/app/models/invite.py` (add `invitee_name`)
- Modify: `backend/app/models/trend.py` (add `trigger_source`, `triggered_by`, `retry_of` to `HybridForecastRun`)
- Modify: `backend/app/models/__init__.py` (register platform models)
- Modify: `docs/superpowers/specs/2026-09-10-platform-admin-console-design.md` (amendment)
- Test: `backend/tests/test_platform_schema.py`

**Interfaces:**
- Produces: `app.models.platform.PlatformRole` (StrEnum: `platform_super_admin`, `platform_admin`, `platform_support`); ORM classes `PlatformAdmin(user_id, role, is_active, granted_by)`, `PlatformAuditEvent(...)`, `SupportAccessSession(tenant_id, admin_user_id, reason, created_at, expires_at, ended_at, ended_by)`; `Tenant.is_operator: bool`, `Tenant.home_region: str`; `Invite.invitee_name: str | None`; `HybridForecastRun.trigger_source: str`, `.triggered_by: UUID | None`, `.retry_of: UUID | None`.

- [ ] **Step 1: Write the failing schema tests**

Create `backend/tests/test_platform_schema.py`:

```python
"""Schema for the platform admin console (migration 0022).

These run as the container superuser for setup and drop to `sanket_app` (with a
tenant GUC, or with the bypass GUC) to prove what the application role can and
cannot do. The properties under test are the ones the console's security model
leans on: one operator tenant, platform roles only for operator users, platform
tables invisible to tenant sessions, and append-only platform audit.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

pytestmark = pytest.mark.asyncio


async def _as_tenant(conn, tenant_id: uuid.UUID) -> None:
    await conn.execute(text("SET LOCAL ROLE sanket_app"))
    await conn.execute(
        text("SELECT set_config('app.current_tenant_id', :t, true)"), {"t": str(tenant_id)}
    )


async def _as_privileged(conn) -> None:
    await conn.execute(text("SET LOCAL ROLE sanket_app"))
    await conn.execute(text("SELECT set_config('app.bypass_rls', 'true', true)"))


async def _operator_tenant(conn) -> uuid.UUID:
    row = (await conn.execute(text("SELECT id FROM tenants WHERE is_operator"))).first()
    if row is not None:
        return row[0]
    tid = uuid.uuid4()
    await conn.execute(
        text(
            """
            INSERT INTO tenants (id, slug, display_name, tier, status, industry,
                                 is_operator, settings)
            VALUES (:id, 'sanket-platform', 'SANKET Platform', 'enterprise',
                    'active', 'fashion', TRUE, '{}'::jsonb)
            """
        ),
        {"id": str(tid)},
    )
    return tid


async def _customer_tenant(conn) -> uuid.UUID:
    tid = uuid.uuid4()
    await conn.execute(
        text(
            """
            INSERT INTO tenants (id, slug, display_name, tier, status, industry)
            VALUES (:id, :slug, 'Schema Customer', 'growth', 'active', 'fashion')
            """
        ),
        {"id": str(tid), "slug": f"schema-{tid.hex[:8]}"},
    )
    return tid


async def _user(conn, tenant_id: uuid.UUID) -> uuid.UUID:
    uid = uuid.uuid4()
    await conn.execute(
        text(
            """
            INSERT INTO users (id, tenant_id, email, full_name, role, active_industry)
            VALUES (:id, :tid, :email, 'Schema User', 'admin', 'fashion')
            """
        ),
        {"id": str(uid), "tid": str(tenant_id), "email": f"s-{uid.hex[:8]}@example.test"},
    )
    return uid


async def test_customer_tenants_are_not_operators(rls_engine) -> None:
    async with rls_engine.begin() as conn:
        tid = await _customer_tenant(conn)
        flag = await conn.scalar(text("SELECT is_operator FROM tenants WHERE id = :t"), {"t": str(tid)})
    assert flag is False


async def test_only_one_operator_tenant_can_exist(rls_engine) -> None:
    async with rls_engine.begin() as conn:
        await _operator_tenant(conn)
    with pytest.raises(DBAPIError):
        async with rls_engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO tenants (id, slug, display_name, tier, status, industry, is_operator)
                    VALUES (gen_random_uuid(), :slug, 'Second operator', 'growth', 'active',
                            'fashion', TRUE)
                    """
                ),
                {"slug": f"op2-{uuid.uuid4().hex[:8]}"},
            )


async def test_operator_flag_is_immutable_after_insert(rls_engine) -> None:
    async with rls_engine.begin() as conn:
        tid = await _customer_tenant(conn)
    with pytest.raises(DBAPIError):
        async with rls_engine.begin() as conn:
            await conn.execute(
                text("UPDATE tenants SET is_operator = TRUE WHERE id = :t"), {"t": str(tid)}
            )


async def test_platform_role_is_refused_for_a_customer_user(rls_engine) -> None:
    async with rls_engine.begin() as conn:
        uid = await _user(conn, await _customer_tenant(conn))
    with pytest.raises(DBAPIError, match="operator-tenant"):
        async with rls_engine.begin() as conn:
            await conn.execute(
                text("INSERT INTO platform_admins (user_id, role) VALUES (:u, 'platform_admin')"),
                {"u": str(uid)},
            )


async def test_platform_role_is_accepted_for_an_operator_user(rls_engine) -> None:
    async with rls_engine.begin() as conn:
        uid = await _user(conn, await _operator_tenant(conn))
        await conn.execute(
            text("INSERT INTO platform_admins (user_id, role) VALUES (:u, 'platform_support')"),
            {"u": str(uid)},
        )
        role = await conn.scalar(
            text("SELECT role::text FROM platform_admins WHERE user_id = :u"), {"u": str(uid)}
        )
    assert role == "platform_support"


async def test_platform_tables_are_invisible_to_a_tenant_session(rls_engine) -> None:
    async with rls_engine.begin() as conn:
        op_user = await _user(conn, await _operator_tenant(conn))
        customer = await _customer_tenant(conn)
        await conn.execute(
            text("INSERT INTO platform_admins (user_id, role) VALUES (:u, 'platform_admin')"),
            {"u": str(op_user)},
        )
        await conn.execute(
            text(
                """
                INSERT INTO support_access_sessions (tenant_id, admin_user_id, reason, expires_at)
                VALUES (:t, :u, 'investigating a failed import', now() + interval '30 minutes')
                """
            ),
            {"t": str(customer), "u": str(op_user)},
        )
        await conn.execute(
            text(
                "INSERT INTO platform_audit_events (action, target_type, tenant_id, outcome) "
                "VALUES ('platform.test', 'tenant', :t, 'success')"
            ),
            {"t": str(customer)},
        )

    async with rls_engine.begin() as conn:
        await _as_tenant(conn, customer)
        for table in ("platform_admins", "support_access_sessions", "platform_audit_events"):
            count = await conn.scalar(text(f"SELECT count(*) FROM {table}"))  # noqa: S608
            assert count == 0, f"{table} leaked into a tenant session"


async def test_a_tenant_session_cannot_grant_itself_a_platform_role(rls_engine) -> None:
    async with rls_engine.begin() as conn:
        op_user = await _user(conn, await _operator_tenant(conn))
        customer = await _customer_tenant(conn)
    with pytest.raises(DBAPIError):
        async with rls_engine.begin() as conn:
            await _as_tenant(conn, customer)
            await conn.execute(
                text("INSERT INTO platform_admins (user_id, role) VALUES (:u, 'platform_super_admin')"),
                {"u": str(op_user)},
            )


async def test_a_tenant_session_can_append_but_not_read_platform_audit(rls_engine) -> None:
    async with rls_engine.begin() as conn:
        customer = await _customer_tenant(conn)
    marker = f"platform.append.{uuid.uuid4().hex[:8]}"
    async with rls_engine.begin() as conn:
        await _as_tenant(conn, customer)
        await conn.execute(
            text(
                "INSERT INTO platform_audit_events (action, target_type, tenant_id, outcome) "
                "VALUES (:a, 'tenant', :t, 'success')"
            ),
            {"a": marker, "t": str(customer)},
        )
        visible = await conn.scalar(
            text("SELECT count(*) FROM platform_audit_events WHERE action = :a"), {"a": marker}
        )
    assert visible == 0
    async with rls_engine.begin() as conn:
        await _as_privileged(conn)
        stored = await conn.scalar(
            text("SELECT count(*) FROM platform_audit_events WHERE action = :a"), {"a": marker}
        )
    assert stored == 1


async def test_platform_audit_is_append_only(rls_engine) -> None:
    marker = f"platform.immutable.{uuid.uuid4().hex[:8]}"
    async with rls_engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO platform_audit_events (action, target_type, outcome) "
                "VALUES (:a, 'tenant', 'success')"
            ),
            {"a": marker},
        )
        await conn.execute(
            text("UPDATE platform_audit_events SET outcome = 'failure' WHERE action = :a"),
            {"a": marker},
        )
        await conn.execute(text("DELETE FROM platform_audit_events WHERE action = :a"), {"a": marker})
        outcome = await conn.scalar(
            text("SELECT outcome FROM platform_audit_events WHERE action = :a"), {"a": marker}
        )
        can_update = await conn.scalar(
            text("SELECT has_table_privilege('sanket_app', 'platform_audit_events', 'UPDATE')")
        )
        can_delete = await conn.scalar(
            text("SELECT has_table_privilege('sanket_app', 'platform_audit_events', 'DELETE')")
        )
    assert outcome == "success"
    assert can_update is False
    assert can_delete is False


async def test_support_sessions_are_capped_at_two_hours(rls_engine) -> None:
    async with rls_engine.begin() as conn:
        op_user = await _user(conn, await _operator_tenant(conn))
        customer = await _customer_tenant(conn)
    with pytest.raises(DBAPIError):
        async with rls_engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO support_access_sessions (tenant_id, admin_user_id, reason, expires_at)
                    VALUES (:t, :u, 'a long investigation', now() + interval '3 hours')
                    """
                ),
                {"t": str(customer), "u": str(op_user)},
            )


async def test_support_sessions_need_a_real_reason(rls_engine) -> None:
    async with rls_engine.begin() as conn:
        op_user = await _user(conn, await _operator_tenant(conn))
        customer = await _customer_tenant(conn)
    with pytest.raises(DBAPIError):
        async with rls_engine.begin() as conn:
            await conn.execute(
                text(
                    """
                    INSERT INTO support_access_sessions (tenant_id, admin_user_id, reason, expires_at)
                    VALUES (:t, :u, 'short', now() + interval '10 minutes')
                    """
                ),
                {"t": str(customer), "u": str(op_user)},
            )


async def test_hybrid_runs_default_to_customer_trigger(rls_engine) -> None:
    async with rls_engine.begin() as conn:
        customer = await _customer_tenant(conn)
        run_id = uuid.uuid4()
        await conn.execute(
            text(
                "INSERT INTO hybrid_forecast_runs (id, tenant_id, industry, horizon_weeks) "
                "VALUES (:id, :t, 'fashion', 12)"
            ),
            {"id": str(run_id), "t": str(customer)},
        )
        source = await conn.scalar(
            text("SELECT trigger_source FROM hybrid_forecast_runs WHERE id = :id"),
            {"id": str(run_id)},
        )
    assert source == "customer"


async def test_hybrid_runs_reject_an_unknown_trigger(rls_engine) -> None:
    async with rls_engine.begin() as conn:
        customer = await _customer_tenant(conn)
    with pytest.raises(DBAPIError):
        async with rls_engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO hybrid_forecast_runs (tenant_id, industry, horizon_weeks, trigger_source) "
                    "VALUES (:t, 'fashion', 12, 'someone_else')"
                ),
                {"t": str(customer)},
            )


async def test_invites_carry_an_optional_invitee_name(rls_engine) -> None:
    async with rls_engine.connect() as conn:
        nullable = await conn.scalar(
            text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name = 'invites' AND column_name = 'invitee_name'"
            )
        )
    assert nullable == "YES"
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `uv run pytest tests/test_platform_schema.py -v`
Expected: FAIL — errors such as `column "is_operator" does not exist` / `relation "platform_admins" does not exist`.

- [ ] **Step 3: Write migration 0022**

Create `backend/alembic/versions/0022_platform_admin_console.py`:

```python
"""Platform admin console: operator tenant, platform roles, platform audit,
support sessions, forecast trigger provenance, invitee names.

Additive and reversible. No existing RLS policy is altered.

* ``tenants.is_operator`` marks the one tenant whose users are SANKET staff. A
  partial unique index allows at most one, and a trigger makes the flag
  immutable after INSERT, so no customer workspace can be turned into the
  operator tenant by an UPDATE any code path might issue.
* ``platform_admins`` is the only source of platform authority. A trigger
  refuses any user who is not a member of the operator tenant, so a customer
  owner cannot hold a platform role even through a stray SQL write.
* ``platform_audit_events`` is append-only (rules + SELECT/INSERT-only grants).
  Any application session may append (so a tenant-scoped transaction can audit
  itself atomically); only privileged (bypass) sessions may read.
* ``support_access_sessions`` rows are capped at two hours by the database.

Revision ID: 0022
Revises: 0021
Create Date: 2026-09-10
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PRIVILEGED_TABLES = ("platform_admins", "support_access_sessions")


def upgrade() -> None:
    # ── Operator tenant flag ─────────────────────────────────────────────────
    op.execute("ALTER TABLE tenants ADD COLUMN is_operator BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute(
        "CREATE UNIQUE INDEX uq_tenants_single_operator ON tenants (is_operator) WHERE is_operator"
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION tenants_operator_flag_immutable()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public, pg_temp
        AS $$
        BEGIN
            IF NEW.is_operator IS DISTINCT FROM OLD.is_operator THEN
                RAISE EXCEPTION 'tenants.is_operator cannot be changed after creation'
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER trg_tenants_operator_flag_immutable BEFORE UPDATE ON tenants "
        "FOR EACH ROW EXECUTE FUNCTION tenants_operator_flag_immutable()"
    )

    # ── Platform roles ───────────────────────────────────────────────────────
    op.execute(
        "CREATE TYPE platform_role AS ENUM "
        "('platform_super_admin', 'platform_admin', 'platform_support')"
    )
    op.execute(
        """
        CREATE TABLE platform_admins (
            id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id     UUID        NOT NULL UNIQUE REFERENCES users (id) ON DELETE CASCADE,
            role        platform_role NOT NULL,
            is_active   BOOLEAN     NOT NULL DEFAULT TRUE,
            granted_by  UUID        REFERENCES users (id) ON DELETE SET NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE TRIGGER trg_platform_admins_updated_at BEFORE UPDATE ON platform_admins "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION platform_admins_require_operator_user()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        SET search_path = pg_catalog, public, pg_temp
        AS $$
        DECLARE
            operator_member BOOLEAN;
        BEGIN
            SELECT t.is_operator INTO operator_member
            FROM public.users u
            JOIN public.tenants t ON t.id = u.tenant_id
            WHERE u.id = NEW.user_id;
            IF operator_member IS DISTINCT FROM TRUE THEN
                RAISE EXCEPTION 'platform roles may only be held by operator-tenant users'
                    USING ERRCODE = 'check_violation';
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER trg_platform_admins_operator_only "
        "BEFORE INSERT OR UPDATE ON platform_admins "
        "FOR EACH ROW EXECUTE FUNCTION platform_admins_require_operator_user()"
    )

    # ── Platform audit (append-only) ─────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE platform_audit_events (
            id            BIGSERIAL   PRIMARY KEY,
            occurred_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            actor_user_id UUID,
            actor_email   CITEXT,
            actor_role    TEXT,
            action        TEXT        NOT NULL,
            target_type   TEXT        NOT NULL,
            target_id     TEXT,
            tenant_id     UUID,
            outcome       TEXT        NOT NULL
                          CHECK (outcome IN ('success', 'failure', 'denied')),
            detail        JSONB       NOT NULL DEFAULT '{}'::jsonb,
            ip_address    INET,
            user_agent    TEXT,
            request_id    TEXT
        )
        """
    )
    op.execute("CREATE INDEX idx_platform_audit_time ON platform_audit_events (occurred_at DESC)")
    op.execute(
        "CREATE INDEX idx_platform_audit_tenant ON platform_audit_events (tenant_id, occurred_at DESC)"
    )
    op.execute(
        "CREATE INDEX idx_platform_audit_actor ON platform_audit_events (actor_user_id, occurred_at DESC)"
    )
    op.execute(
        "CREATE INDEX idx_platform_audit_action ON platform_audit_events (action, occurred_at DESC)"
    )
    op.execute(
        "CREATE RULE no_update_platform_audit AS ON UPDATE TO platform_audit_events DO INSTEAD NOTHING"
    )
    op.execute(
        "CREATE RULE no_delete_platform_audit AS ON DELETE TO platform_audit_events DO INSTEAD NOTHING"
    )

    # ── Support access sessions ──────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE support_access_sessions (
            id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id     UUID        NOT NULL REFERENCES tenants (id) ON DELETE CASCADE,
            admin_user_id UUID        NOT NULL REFERENCES users (id),
            reason        TEXT        NOT NULL CHECK (char_length(reason) >= 10),
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at    TIMESTAMPTZ NOT NULL,
            ended_at      TIMESTAMPTZ,
            ended_by      UUID        REFERENCES users (id) ON DELETE SET NULL,
            CONSTRAINT ck_support_session_window
                CHECK (expires_at > created_at AND expires_at <= created_at + interval '2 hours')
        )
        """
    )
    op.execute(
        "CREATE INDEX idx_support_sessions_lookup "
        "ON support_access_sessions (tenant_id, admin_user_id, expires_at DESC)"
    )

    # ── RLS ──────────────────────────────────────────────────────────────────
    for table in (*_PRIVILEGED_TABLES, "platform_audit_events"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    for table in _PRIVILEGED_TABLES:
        op.execute(
            f"CREATE POLICY {table}_privileged ON {table} "
            "USING (bypass_rls()) WITH CHECK (bypass_rls())"
        )
    op.execute(
        "CREATE POLICY platform_audit_events_read ON platform_audit_events "
        "FOR SELECT USING (bypass_rls())"
    )
    op.execute(
        "CREATE POLICY platform_audit_events_append ON platform_audit_events "
        "FOR INSERT WITH CHECK (true)"
    )

    # ── Grants (guarded like 0021 so a DB without the app role still migrates)
    op.execute(
        """
        DO $grant$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'sanket_app') THEN
                GRANT SELECT, INSERT, UPDATE ON platform_admins TO sanket_app;
                GRANT SELECT, INSERT ON platform_audit_events TO sanket_app;
                GRANT USAGE, SELECT ON SEQUENCE platform_audit_events_id_seq TO sanket_app;
                GRANT SELECT, INSERT ON support_access_sessions TO sanket_app;
                GRANT UPDATE (ended_at, ended_by) ON support_access_sessions TO sanket_app;
            END IF;
        END
        $grant$;
        """
    )

    # ── Forecast trigger provenance ──────────────────────────────────────────
    op.execute(
        """
        ALTER TABLE hybrid_forecast_runs
            ADD COLUMN trigger_source TEXT NOT NULL DEFAULT 'customer',
            ADD COLUMN triggered_by UUID REFERENCES users (id) ON DELETE SET NULL,
            ADD COLUMN retry_of UUID REFERENCES hybrid_forecast_runs (id) ON DELETE SET NULL,
            ADD CONSTRAINT ck_hybrid_runs_trigger_source
                CHECK (trigger_source IN ('customer', 'platform_admin', 'platform_retry'))
        """
    )

    # ── Invitee display name ─────────────────────────────────────────────────
    op.execute("ALTER TABLE invites ADD COLUMN invitee_name TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE invites DROP COLUMN IF EXISTS invitee_name")
    op.execute(
        """
        ALTER TABLE hybrid_forecast_runs
            DROP CONSTRAINT IF EXISTS ck_hybrid_runs_trigger_source,
            DROP COLUMN IF EXISTS retry_of,
            DROP COLUMN IF EXISTS triggered_by,
            DROP COLUMN IF EXISTS trigger_source
        """
    )
    op.execute("DROP TABLE IF EXISTS support_access_sessions")
    op.execute("DROP TABLE IF EXISTS platform_audit_events")
    op.execute("DROP TABLE IF EXISTS platform_admins")
    op.execute("DROP FUNCTION IF EXISTS platform_admins_require_operator_user()")
    op.execute("DROP TYPE IF EXISTS platform_role")
    op.execute("DROP TRIGGER IF EXISTS trg_tenants_operator_flag_immutable ON tenants")
    op.execute("DROP FUNCTION IF EXISTS tenants_operator_flag_immutable()")
    op.execute("DROP INDEX IF EXISTS uq_tenants_single_operator")
    op.execute("ALTER TABLE tenants DROP COLUMN IF EXISTS is_operator")
```

- [ ] **Step 4: Add the ORM models**

Create `backend/app/models/platform.py`:

```python
"""Platform (operator) tables. See migration 0022 and docs/ADMIN_CONSOLE.md.

None of these are tenant data. `platform_admins` and `support_access_sessions`
are readable and writable only from privileged (bypass) sessions;
`platform_audit_events` may be appended from any session but read only from a
privileged one.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Text, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import CITEXT, INET, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKey


class PlatformRole(enum.StrEnum):
    platform_super_admin = "platform_super_admin"
    platform_admin = "platform_admin"
    platform_support = "platform_support"


class PlatformAdmin(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "platform_admins"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    role: Mapped[PlatformRole] = mapped_column(
        SAEnum(PlatformRole, name="platform_role", create_type=False), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    granted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )


class PlatformAuditEvent(Base):
    __tablename__ = "platform_audit_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    actor_email: Mapped[str | None] = mapped_column(CITEXT)
    actor_role: Mapped[str | None] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str] = mapped_column(Text, nullable=False)
    target_id: Mapped[str | None] = mapped_column(Text)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(Text)


class SupportAccessSession(UUIDPrimaryKey, Base):
    __tablename__ = "support_access_sessions"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    admin_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
```

In `backend/app/models/tenant.py`, add `text` to the `sqlalchemy` import list (alongside `Boolean`, `DateTime`, …) and add these two columns to `Tenant` directly after `data_retention_days`:

```python
    # The single SANKET operator workspace (migration 0022). Set only at INSERT
    # by the bootstrap CLI; a database trigger refuses any later change.
    is_operator: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    # Residency region (sql/005). Mapped read-mostly so the console can show and
    # set it; the database default applies when a creation path omits it.
    home_region: Mapped[str] = mapped_column(
        SAEnum(
            "us-east",
            "us-west",
            "eu-west",
            "eu-central",
            "ap-south",
            "ap-northeast",
            name="region_code",
            create_type=False,
        ),
        nullable=False,
        server_default=text("'us-east'"),
    )
```

In `backend/app/models/invite.py`, add after `invited_by`:

```python
    # Display name the operator typed when inviting (migration 0022). The
    # accepted user's name still comes from the invitee at redemption.
    invitee_name: Mapped[str | None] = mapped_column(Text)
```

In `backend/app/models/trend.py`, add to `HybridForecastRun` after `error`:

```python
    # Who started this run (migration 0022). `customer` for the workspace's own
    # users; `platform_admin` / `platform_retry` for the operator console.
    trigger_source: Mapped[str] = mapped_column(
        Text, nullable=False, default="customer", server_default="customer"
    )
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    retry_of: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("hybrid_forecast_runs.id", ondelete="SET NULL"), nullable=True
    )
```

(Check `trend.py`'s imports: it already imports `uuid`, `ForeignKey`, `Text`, `UUID`; add any that are missing.)

In `backend/app/models/__init__.py`, add `from app.models.platform import PlatformAdmin, PlatformAuditEvent, SupportAccessSession` and the three names to `__all__` (alphabetical).

- [ ] **Step 5: Run the schema tests**

Run: `uv run pytest tests/test_platform_schema.py tests/test_rls_isolation.py -v`
Expected: all PASS (the existing FORCE-RLS guard still passes because every new RLS table is FORCEd).

- [ ] **Step 6: Run the whole backend suite for regressions**

Run: `uv run pytest -q`
Expected: same failures as the M0 baseline and no new ones. (Mapping `home_region` and `is_operator` on `Tenant` touches every tenant query; this run is what proves it.)

- [ ] **Step 7: Record the spec amendment**

In `docs/superpowers/specs/2026-09-10-platform-admin-console-design.md`, §6.3, replace the bullet beginning `- **Platform tables**` with:

```markdown
- **Platform tables** (`platform_admins`, `platform_audit_events`,
  `support_access_sessions`): `ENABLE` + `FORCE ROW LEVEL SECURITY`.
  `platform_admins` and `support_access_sessions` have one policy
  `USING (bypass_rls()) WITH CHECK (bypass_rls())`. `platform_audit_events` has
  `FOR SELECT USING (bypass_rls())` and `FOR INSERT WITH CHECK (true)` so a
  tenant-scoped transaction can append its own audit row atomically; no UPDATE
  or DELETE policy exists and the rules/grants forbid both. A customer session
  can therefore never read any platform table. Platform bookkeeping (support
  sessions, read audits, denied/failed events, tenant creation) runs in a
  writable bypass session reached only through `data_access.platform_write`.
```

and in §7's table, change the `platform_audit_events` row's grant note to end with `; RLS: read = privileged only, insert = any session`.

- [ ] **Step 8: Commit**

```bash
git add backend/alembic/versions/0022_platform_admin_console.py backend/app/models/platform.py \
  backend/app/models/tenant.py backend/app/models/invite.py backend/app/models/trend.py \
  backend/app/models/__init__.py backend/tests/test_platform_schema.py \
  docs/superpowers/specs/2026-09-10-platform-admin-console-design.md
git commit -m "feat(db): operator tenant, platform roles, platform audit, support sessions"
```

---

### Task 1.2: Settings, read-only bypass sessions, and the MFA claim

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/app/core/database.py` (`session_no_rls(read_only=...)`, `tenant_isolation_problems()`)
- Modify: `backend/app/core/firebase_auth.py` (`_normalize` surfaces `mfa`)
- Modify: `backend/app/middleware/tenant_context.py` (`request.state.auth_second_factor`)
- Test: `backend/tests/test_platform_foundation.py`

**Interfaces:**
- Produces: `Settings.platform_operator_tenant_slug: str`, `Settings.platform_admin_require_mfa: bool | None`, `Settings.platform_support_session_max_minutes: int`, property `Settings.platform_admin_mfa_required -> bool`; `Database.session_no_rls(*, read_only: bool = False)`; `Database.tenant_isolation_problems() -> list[str]`; identity key `NormalizedIdentity["mfa"]: str | None`; `request.state.auth_second_factor: str | None`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_platform_foundation.py`:

```python
"""Small primitives the console depends on: settings, the read-only bypass
session, and carrying the MFA claim from the token to the request."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from app.config import Settings, get_settings
from app.core.firebase_auth import DEV_IDENTITY_MARKER, FirebaseVerifier

pytestmark = pytest.mark.asyncio

_SECRET = "test-secret-min-32-chars-please-rotate-1234"


def _settings(**overrides) -> Settings:
    return Settings(jwt_secret=_SECRET, **overrides)


async def test_mfa_is_required_by_default_only_in_production() -> None:
    assert _settings(app_env="development").platform_admin_mfa_required is False
    prod = Settings(
        jwt_secret=_SECRET * 2,
        app_env="production",
        firebase_project_id="p",
        database_url="postgresql+asyncpg://sanket_app:strong@db:5432/sanket",
        metrics_token="m",
        ml_service_token="ml",
        integration_encryption_key="k",
    )
    assert prod.platform_admin_mfa_required is True


async def test_mfa_requirement_can_be_set_explicitly() -> None:
    assert _settings(platform_admin_require_mfa=True).platform_admin_mfa_required is True


async def test_support_sessions_cannot_be_configured_past_two_hours() -> None:
    with pytest.raises(ValueError):
        _settings(platform_support_session_max_minutes=121)


async def test_operator_slug_defaults() -> None:
    assert _settings().platform_operator_tenant_slug == "sanket-platform"


async def test_read_only_bypass_session_refuses_writes(setup_schema) -> None:
    from app.core.database import Database

    get_settings.cache_clear()
    db = Database(get_settings())
    try:
        with pytest.raises(DBAPIError, match="read-only"):
            async with db.session_no_rls(read_only=True) as session:
                await session.execute(
                    text(
                        "INSERT INTO platform_audit_events (action, target_type, outcome) "
                        "VALUES ('platform.test', 'x', 'success')"
                    )
                )
        async with db.session_no_rls(read_only=True) as session:
            bypass = await session.scalar(text("SELECT current_setting('app.bypass_rls', true)"))
        assert bypass == "true"
    finally:
        await db.close()


async def test_isolation_problems_are_reported_for_a_superuser(setup_schema) -> None:
    # The test container connects as its superuser, so the check must say so.
    from app.core.database import Database

    get_settings.cache_clear()
    db = Database(get_settings())
    try:
        problems = await db.tenant_isolation_problems()
    finally:
        await db.close()
    assert any("SUPERUSER" in p for p in problems)


def _dev_token(**extra) -> str:
    now = datetime.now(tz=UTC)
    payload = {
        "sub": "u1", "uid": "u1", "puid": "00000000-0000-0000-0000-000000000001",
        "tid": "00000000-0000-0000-0000-000000000002", "role": "admin", "ind": "fashion",
        "iat": now, "exp": now + timedelta(minutes=5), DEV_IDENTITY_MARKER: True, **extra,
    }
    return jwt.encode(payload, _SECRET, algorithm="HS256")


async def test_identity_carries_the_second_factor_when_present() -> None:
    verifier = FirebaseVerifier(_settings())
    identity = verifier.verify(_dev_token(firebase={"sign_in_second_factor": "totp"}))
    assert identity["mfa"] == "totp"


async def test_identity_has_no_second_factor_by_default() -> None:
    verifier = FirebaseVerifier(_settings())
    assert verifier.verify(_dev_token())["mfa"] is None
```

- [ ] **Step 2: Run to see failures**

Run: `uv run pytest tests/test_platform_foundation.py -v`
Expected: FAIL — `AttributeError: ... has no attribute 'platform_admin_mfa_required'`, `unexpected keyword argument 'read_only'`, `KeyError: 'mfa'`.

- [ ] **Step 3: Add the settings**

In `backend/app/config.py`, add this block to `Settings` immediately before the `@field_validator("allowed_origins", ...)` method:

```python
    # ── Platform admin console ───────────────────────────────────────────────
    # Slug of the single operator workspace whose users are SANKET staff. It is
    # reserved: no signup or admin action may create a customer tenant with it.
    platform_operator_tenant_slug: str = Field(
        default="sanket-platform", pattern=r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$"
    )
    # None = required in production, not elsewhere. Set true/false explicitly to
    # override (e.g. true on staging). Production without MFA shows as a warning
    # on the console's health page rather than silently.
    platform_admin_require_mfa: bool | None = None
    # Hard cap is also enforced by the database (migration 0022).
    platform_support_session_max_minutes: int = Field(default=120, ge=1, le=120)
```

and add this property next to `is_production`:

```python
    @property
    def platform_admin_mfa_required(self) -> bool:
        if self.platform_admin_require_mfa is None:
            return self.is_production
        return self.platform_admin_require_mfa
```

- [ ] **Step 4: Add the read-only option and the isolation check**

In `backend/app/core/database.py`, replace `session_no_rls` with:

```python
    @asynccontextmanager
    async def session_no_rls(self, *, read_only: bool = False) -> AsyncIterator[AsyncSession]:
        """Open a session WITHOUT setting the tenant GUC, but with RLS bypassed.

        Used for cross-tenant background work (signal ingest, retry workers,
        seeding, login). Sets the local `app.bypass_rls` GUC to 'true'.

        ``read_only=True`` issues ``SET TRANSACTION READ ONLY`` first, so the
        database itself refuses any write made through the session. The platform
        console's cross-tenant listings use this so a bug there can read too
        much but can never change anything.
        """
        async with self._sessionmaker() as session:
            try:
                async with session.begin():
                    if read_only:
                        # Must be the first statement of the transaction.
                        await session.execute(text("SET TRANSACTION READ ONLY"))
                    await session.execute(text("SELECT set_config('app.bypass_rls', 'true', true)"))
                    yield session
            except Exception:
                raise
```

Refactor `assert_tenant_isolation_enforced` into two methods (behaviour of the assert is unchanged):

```python
    async def tenant_isolation_problems(self) -> list[str]:
        """Why tenant isolation would NOT hold with this role, or [] if it does.

        Raises on connection failure; callers decide how to treat that.
        """
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
        problems: list[str] = []
        if role and bool(role[0]):
            problems.append("the role is a SUPERUSER (bypasses RLS)")
        if role and bool(role[1]):
            problems.append("the role has BYPASSRLS (bypasses RLS)")
        if forced is False:
            problems.append("the 'tenants' table is missing FORCE ROW LEVEL SECURITY")
        return problems

    async def assert_tenant_isolation_enforced(self, *, strict: bool) -> None:
        """Verify the runtime DB role cannot bypass row-level security.

        (Docstring unchanged from the previous version — keep it.)
        """
        try:
            problems = await self.tenant_isolation_problems()
        except Exception as exc:
            log.warning("database.rls_check.skipped", error=str(exc))
            return
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
```

(Keep the original long docstring text of `assert_tenant_isolation_enforced` verbatim.)

- [ ] **Step 5: Carry the second factor through**

In `backend/app/core/firebase_auth.py`, in `_normalize`, compute the factor before building the identity and add it as a key:

```python
        firebase_claims = decoded.get("firebase")
        second_factor = (
            firebase_claims.get("sign_in_second_factor")
            if isinstance(firebase_claims, dict)
            else None
        )
        identity = NormalizedIdentity(
            uid=str(uid),
            puid=str(puid),
            email=decoded.get("email"),
            tid=str(tid),
            role=str(role),
            ind=str(ind),
            source=source,
            # Firebase stamps `firebase.sign_in_second_factor` ("totp", "phone")
            # when the session was established with MFA. The platform console
            # requires it in production; customer routes ignore it.
            mfa=str(second_factor) if second_factor else None,
        )
```

Update the `NormalizedIdentity` docstring's key list to mention optional `mfa`.

In `backend/app/middleware/tenant_context.py`: add `request.state.auth_second_factor = None` next to the other `request.state` initialisations, and `request.state.auth_second_factor = identity.get("mfa")` next to `request.state.firebase_uid = identity.get("uid")`. Add `auth_second_factor (str | None)` to the class docstring's attribute list.

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/test_platform_foundation.py tests/test_firebase_auth.py tests/test_auth.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/config.py backend/app/core/database.py backend/app/core/firebase_auth.py \
  backend/app/middleware/tenant_context.py backend/tests/test_platform_foundation.py
git commit -m "feat(core): platform settings, read-only bypass sessions, MFA claim on request"
```

---

### Task 1.3: Test factories and the platform authorization dependency

**Files:**
- Create: `backend/tests/admin_factories.py`
- Create: `backend/app/core/platform_authz.py`
- Test: `backend/tests/test_platform_authz.py`

**Interfaces:**
- Consumes: Task 1.1 models; Task 1.2 `session_no_rls(read_only=True)`, `request.state.auth_second_factor`, `Settings.platform_admin_mfa_required`.
- Produces (in `app.core.platform_authz`):
  - `class Permission(StrEnum)`: `platform_read="platform:read"`, `support_open="support:open"`, `tenants_write="tenants:write"`, `tenants_archive="tenants:archive"`, `users_write="users:write"`, `billing_write="billing:write"`, `billing_contract="billing:contract"`, `data_write="data:write"`, `jobs_write="jobs:write"`.
  - `ROLE_PERMISSIONS: dict[PlatformRole, frozenset[Permission]]`.
  - `@dataclass(frozen=True) class PlatformPrincipal`: `user_id`, `tenant_id`, `email`, `full_name`, `role`, `mfa_required`, `mfa_satisfied`, `ip_address`, `user_agent`, `request_id`; property `permissions`; method `can(p) -> bool`. Constructible only through `_issue(...)`.
  - `async def require_platform_role(request) -> PlatformPrincipal` (role checked, MFA reported not enforced; used only by `/admin/me`).
  - `async def require_platform_admin(request) -> PlatformPrincipal` (role + MFA; router-level for everything else).
  - `def require_permission(p: Permission) -> Depends`.
  - Aliases: `ReadPrincipal`, `SupportPrincipal`, `TenantsWritePrincipal`, `TenantsArchivePrincipal`, `UsersWritePrincipal`, `BillingWritePrincipal`, `BillingContractPrincipal`, `DataWritePrincipal`, `JobsWritePrincipal` (each `Annotated[PlatformPrincipal, require_permission(...)]`).
  - Constants `DENIED_DETAIL = "Platform access denied"`, `MFA_DETAIL = "Multi-factor authentication is required for the platform console"`.
- Produces (in `tests/admin_factories.py`): `mint(...) -> str`, `auth(token) -> dict`, `Actor` dataclass (`user_id`, `tenant_id`, `email`, `token`), `ensure_operator_tenant(db)`, `create_user(db, tenant_id, *, role="admin", email=None, is_active=True, industry="fashion")`, `create_platform_admin(db, role="platform_admin", *, active=True, second_factor=None) -> Actor`, `create_customer_tenant(db, *, slug=None, industry="fashion", subscribed=True, status="active") -> uuid.UUID`, `create_customer(db, tenant_id, role="owner") -> Actor`.

- [ ] **Step 1: Write the test factories**

Create `backend/tests/admin_factories.py`:

```python
"""Builders for platform-console tests.

Everything is created through SQL as the container superuser (the `db_session`
fixture), then exercised through the real HTTP stack with dev tokens, exactly
as other suites do (see tests/test_industry_scope.py).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.firebase_auth import DEV_IDENTITY_MARKER


@dataclass(frozen=True)
class Actor:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    token: str

    @property
    def headers(self) -> dict[str, str]:
        return auth(self.token)


def mint(
    *,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    role: str = "admin",
    industry: str = "fashion",
    email: str | None = None,
    second_factor: str | None = None,
) -> str:
    """A dev identity token, optionally carrying Firebase's MFA claim."""
    now = datetime.now(tz=UTC)
    payload: dict = {
        "sub": str(user_id),
        "uid": str(user_id),
        "puid": str(user_id),
        "email": email,
        "tid": str(tenant_id),
        "role": role,
        "ind": industry,
        "iat": now,
        "exp": now + timedelta(minutes=30),
        DEV_IDENTITY_MARKER: True,
    }
    if second_factor:
        payload["firebase"] = {"sign_in_second_factor": second_factor}
    return jwt.encode(payload, get_settings().jwt_secret, algorithm="HS256")


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def ensure_operator_tenant(db: AsyncSession) -> uuid.UUID:
    row = (await db.execute(text("SELECT id FROM tenants WHERE is_operator"))).first()
    if row is not None:
        return row[0]
    tid = uuid.uuid4()
    await db.execute(
        text(
            """
            INSERT INTO tenants (id, slug, display_name, tier, status, industry,
                                 is_operator, settings)
            VALUES (:id, :slug, 'SANKET Platform', 'enterprise', 'active', 'fashion',
                    TRUE, '{}'::jsonb)
            """
        ),
        {"id": str(tid), "slug": get_settings().platform_operator_tenant_slug},
    )
    await db.commit()
    return tid


async def create_user(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    role: str = "admin",
    email: str | None = None,
    is_active: bool = True,
    industry: str = "fashion",
    full_name: str = "Test User",
) -> tuple[uuid.UUID, str]:
    uid = uuid.uuid4()
    email = email or f"u-{uid.hex[:10]}@example.test"
    await db.execute(
        text(
            """
            INSERT INTO users (id, tenant_id, email, full_name, role, active_industry, is_active)
            VALUES (:id, :tid, :email, :name, :role, :ind, :active)
            """
        ),
        {
            "id": str(uid),
            "tid": str(tenant_id),
            "email": email,
            "name": full_name,
            "role": role,
            "ind": industry,
            "active": is_active,
        },
    )
    await db.commit()
    return uid, email


async def create_platform_admin(
    db: AsyncSession,
    role: str = "platform_admin",
    *,
    active: bool = True,
    second_factor: str | None = None,
) -> Actor:
    operator = await ensure_operator_tenant(db)
    uid, email = await create_user(db, operator, role="admin", full_name="Ops Person")
    await db.execute(
        text(
            "INSERT INTO platform_admins (user_id, role, is_active) "
            "VALUES (:u, CAST(:r AS platform_role), :a)"
        ),
        {"u": str(uid), "r": role, "a": active},
    )
    await db.commit()
    token = mint(user_id=uid, tenant_id=operator, email=email, second_factor=second_factor)
    return Actor(user_id=uid, tenant_id=operator, email=email, token=token)


async def create_customer_tenant(
    db: AsyncSession,
    *,
    slug: str | None = None,
    industry: str = "fashion",
    subscribed: bool = True,
    status: str = "active",
    display_name: str | None = None,
) -> uuid.UUID:
    tid = uuid.uuid4()
    slug = slug or f"cust-{tid.hex[:8]}"
    await db.execute(
        text(
            """
            INSERT INTO tenants (id, slug, display_name, tier, status, industry, settings)
            VALUES (:id, :slug, :name, 'growth', CAST(:status AS tenant_status),
                    CAST(:ind AS industry_code), '{}'::jsonb)
            """
        ),
        {
            "id": str(tid),
            "slug": slug,
            "name": display_name or slug.replace("-", " ").title(),
            "status": status,
            "ind": industry,
        },
    )
    await db.execute(
        text(
            """
            INSERT INTO industry_profiles (id, tenant_id, industry, custom_signal_types,
                                           model_overrides, feature_flags)
            VALUES (gen_random_uuid(), :tid, CAST(:ind AS industry_code), '{}', '{}', '{}')
            """
        ),
        {"tid": str(tid), "ind": industry},
    )
    if subscribed:
        await db.execute(
            text(
                """
                INSERT INTO subscriptions (id, tenant_id, plan_id, status, current_period_start,
                                           current_period_end, cancel_at_period_end, metadata)
                VALUES (gen_random_uuid(), :tid, 'growth_monthly', 'active',
                        now() - interval '1 day', now() + interval '30 days', FALSE, '{}'::jsonb)
                """
            ),
            {"tid": str(tid)},
        )
    await db.commit()
    return tid


async def create_customer(
    db: AsyncSession, tenant_id: uuid.UUID, role: str = "owner", industry: str = "fashion"
) -> Actor:
    uid, email = await create_user(db, tenant_id, role=role, industry=industry)
    token = mint(user_id=uid, tenant_id=tenant_id, role=role, industry=industry, email=email)
    return Actor(user_id=uid, tenant_id=tenant_id, email=email, token=token)
```

- [ ] **Step 2: Write the failing authz tests**

Create `backend/tests/test_platform_authz.py`:

```python
"""The platform authorization boundary, tested through a throwaway router.

Endpoints in later tasks inherit these dependencies; testing them against a
minimal app keeps each rule's failure message pointed at the rule.
"""

from __future__ import annotations

import pytest
from fastapi import APIRouter, Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from admin_factories import (
    auth,
    create_customer,
    create_customer_tenant,
    create_platform_admin,
    create_user,
    ensure_operator_tenant,
    mint,
)
from app.config import get_settings
from app.core.platform_authz import (
    DENIED_DETAIL,
    MFA_DETAIL,
    Permission,
    PlatformPrincipal,
    ReadPrincipal,
    TenantsArchivePrincipal,
    TenantsWritePrincipal,
    require_platform_admin,
    require_platform_role,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def probe(setup_schema):
    """A real app (real middleware) with three probe routes mounted."""
    from app.main import create_app

    app = create_app()
    role_only = APIRouter(dependencies=[Depends(require_platform_role)])
    secured = APIRouter(dependencies=[Depends(require_platform_admin)])

    @role_only.get("/api/v1/_probe/me")
    async def me(principal: PlatformPrincipal = Depends(require_platform_role)) -> dict:
        return {"role": principal.role.value, "mfa_satisfied": principal.mfa_satisfied}

    @secured.get("/api/v1/_probe/read")
    async def read(principal: ReadPrincipal) -> dict:
        return {"ok": True}

    @secured.post("/api/v1/_probe/write")
    async def write(principal: TenantsWritePrincipal) -> dict:
        return {"ok": True}

    @secured.post("/api/v1/_probe/archive")
    async def archive(principal: TenantsArchivePrincipal) -> dict:
        return {"ok": True}

    app.include_router(role_only)
    app.include_router(secured)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        async with app.router.lifespan_context(app):
            yield ac


async def test_no_token_is_401(probe: AsyncClient) -> None:
    assert (await probe.get("/api/v1/_probe/read")).status_code == 401


@pytest.mark.parametrize("role", ["owner", "admin", "analyst", "viewer"])
async def test_every_customer_role_is_denied(
    probe: AsyncClient, db_session: AsyncSession, role: str
) -> None:
    tenant = await create_customer_tenant(db_session)
    customer = await create_customer(db_session, tenant, role=role)
    r = await probe.get("/api/v1/_probe/read", headers=customer.headers)
    assert r.status_code == 403
    assert r.json()["detail"] == DENIED_DETAIL


async def test_operator_user_without_a_role_is_denied(
    probe: AsyncClient, db_session: AsyncSession
) -> None:
    operator = await ensure_operator_tenant(db_session)
    uid, email = await create_user(db_session, operator)
    token = mint(user_id=uid, tenant_id=operator, email=email)
    assert (await probe.get("/api/v1/_probe/read", headers=auth(token))).status_code == 403


async def test_deactivated_platform_admin_is_denied(
    probe: AsyncClient, db_session: AsyncSession
) -> None:
    ops = await create_platform_admin(db_session, active=False)
    assert (await probe.get("/api/v1/_probe/read", headers=ops.headers)).status_code == 403


async def test_disabled_operator_user_is_denied(
    probe: AsyncClient, db_session: AsyncSession
) -> None:
    ops = await create_platform_admin(db_session)
    await db_session.execute(
        text("UPDATE users SET is_active = FALSE WHERE id = :u"), {"u": str(ops.user_id)}
    )
    await db_session.commit()
    assert (await probe.get("/api/v1/_probe/read", headers=ops.headers)).status_code == 403


async def test_token_for_the_wrong_tenant_is_denied(
    probe: AsyncClient, db_session: AsyncSession
) -> None:
    """A real platform admin's user id with a customer tenant id in the token."""
    ops = await create_platform_admin(db_session)
    customer_tenant = await create_customer_tenant(db_session)
    token = mint(user_id=ops.user_id, tenant_id=customer_tenant, email=ops.email)
    assert (await probe.get("/api/v1/_probe/read", headers=auth(token))).status_code == 403


async def test_support_can_read_but_not_write(
    probe: AsyncClient, db_session: AsyncSession
) -> None:
    ops = await create_platform_admin(db_session, "platform_support")
    assert (await probe.get("/api/v1/_probe/read", headers=ops.headers)).status_code == 200
    r = await probe.post("/api/v1/_probe/write", headers=ops.headers)
    assert r.status_code == 403
    assert "tenants:write" in r.json()["detail"]


async def test_admin_cannot_use_super_admin_actions(
    probe: AsyncClient, db_session: AsyncSession
) -> None:
    ops = await create_platform_admin(db_session, "platform_admin")
    assert (await probe.post("/api/v1/_probe/write", headers=ops.headers)).status_code == 200
    assert (await probe.post("/api/v1/_probe/archive", headers=ops.headers)).status_code == 403


async def test_super_admin_can_archive(probe: AsyncClient, db_session: AsyncSession) -> None:
    ops = await create_platform_admin(db_session, "platform_super_admin")
    assert (await probe.post("/api/v1/_probe/archive", headers=ops.headers)).status_code == 200


async def test_mfa_is_enforced_when_required(
    probe: AsyncClient, db_session: AsyncSession, monkeypatch
) -> None:
    monkeypatch.setattr(get_settings(), "platform_admin_require_mfa", True)
    without = await create_platform_admin(db_session)
    r = await probe.get("/api/v1/_probe/read", headers=without.headers)
    assert r.status_code == 403
    assert r.json()["detail"] == MFA_DETAIL
    # /me still answers, reporting the gap, so the console can route to enrollment.
    me = await probe.get("/api/v1/_probe/me", headers=without.headers)
    assert me.status_code == 200
    assert me.json()["mfa_satisfied"] is False

    with_mfa = await create_platform_admin(db_session, second_factor="totp")
    assert (await probe.get("/api/v1/_probe/read", headers=with_mfa.headers)).status_code == 200


async def test_denied_attempts_are_recorded(
    probe: AsyncClient, db_session: AsyncSession
) -> None:
    tenant = await create_customer_tenant(db_session)
    customer = await create_customer(db_session, tenant)
    await probe.get("/api/v1/_probe/read", headers=customer.headers)
    count = await db_session.scalar(
        text(
            "SELECT count(*) FROM platform_audit_events "
            "WHERE actor_user_id = :u AND outcome = 'denied'"
        ),
        {"u": str(customer.user_id)},
    )
    assert count >= 1


async def test_principals_cannot_be_constructed_directly() -> None:
    import uuid

    from app.models.platform import PlatformRole

    with pytest.raises(RuntimeError):
        PlatformPrincipal(
            user_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            email="x@example.test",
            full_name="X",
            role=PlatformRole.platform_super_admin,
            mfa_required=False,
            mfa_satisfied=True,
            ip_address=None,
            user_agent=None,
            request_id=None,
        )


async def test_role_permission_matrix() -> None:
    from app.core.platform_authz import ROLE_PERMISSIONS
    from app.models.platform import PlatformRole

    support = ROLE_PERMISSIONS[PlatformRole.platform_support]
    admin = ROLE_PERMISSIONS[PlatformRole.platform_admin]
    superadmin = ROLE_PERMISSIONS[PlatformRole.platform_super_admin]
    assert support == {Permission.platform_read, Permission.support_open}
    assert Permission.tenants_archive not in admin
    assert Permission.billing_contract not in admin
    assert admin < superadmin
    assert {Permission.tenants_archive, Permission.billing_contract} <= superadmin
```

- [ ] **Step 3: Run to see failures**

Run: `uv run pytest tests/test_platform_authz.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.platform_authz'`.

- [ ] **Step 4: Implement `platform_authz`**

Create `backend/app/core/platform_authz.py`:

```python
"""Platform (operator) authorization — the third boundary.

RLS answers *whose data may this request read*; ``industry_scope`` answers
*which modules may this company use*; this module answers *may this person
operate the platform at all*. They are separate on purpose (see the spec,
docs/superpowers/specs/2026-09-10-platform-admin-console-design.md §2).

Authority is the ``platform_admins`` table, read on every admin request — never
a token claim — so revoking a role takes effect on the next request. A caller
is a platform principal only if all of these hold:

* the bearer verified (TenantContextMiddleware),
* their user row is active and belongs to the operator tenant named in the token,
* the operator tenant is not suspended or cancelled,
* their ``platform_admins`` row is active,
* and, when required, the token carries a second factor.

Everything fails closed: a database error is a 403, not a pass.
"""

from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from typing import Annotated, Any

import structlog
from fastapi import Depends, Request
from sqlalchemy import select

from app.config import get_settings
from app.core.exceptions import AuthenticationError, PermissionDeniedError
from app.middleware.rate_limit import client_ip_from_request
from app.models.enums import TenantStatus
from app.models.platform import PlatformAdmin, PlatformRole
from app.models.tenant import Tenant, User

log = structlog.get_logger(__name__)

DENIED_DETAIL = "Platform access denied"
MFA_DETAIL = "Multi-factor authentication is required for the platform console"


class Permission(enum.StrEnum):
    platform_read = "platform:read"
    support_open = "support:open"
    tenants_write = "tenants:write"
    tenants_archive = "tenants:archive"
    users_write = "users:write"
    billing_write = "billing:write"
    billing_contract = "billing:contract"
    data_write = "data:write"
    jobs_write = "jobs:write"


_READ = frozenset({Permission.platform_read, Permission.support_open})
_ADMIN = _READ | {
    Permission.tenants_write,
    Permission.users_write,
    Permission.billing_write,
    Permission.data_write,
    Permission.jobs_write,
}
ROLE_PERMISSIONS: dict[PlatformRole, frozenset[Permission]] = {
    PlatformRole.platform_support: _READ,
    PlatformRole.platform_admin: frozenset(_ADMIN),
    PlatformRole.platform_super_admin: frozenset(
        _ADMIN | {Permission.tenants_archive, Permission.billing_contract}
    ),
}

# Only `_issue` holds this, so a principal cannot be conjured by code that has
# not been through the database check. It is a guard against accident, not an
# adversary with interpreter access.
_ISSUER = object()


@dataclass(frozen=True)
class PlatformPrincipal:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    full_name: str
    role: PlatformRole
    mfa_required: bool
    mfa_satisfied: bool
    ip_address: str | None
    user_agent: str | None
    request_id: str | None
    _issuer: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._issuer is not _ISSUER:
            raise RuntimeError("PlatformPrincipal is issued only by platform_authz")

    @property
    def permissions(self) -> frozenset[Permission]:
        return ROLE_PERMISSIONS[self.role]

    def can(self, permission: Permission) -> bool:
        return permission in self.permissions


def _issue(**values: Any) -> PlatformPrincipal:
    return PlatformPrincipal(**values, _issuer=_ISSUER)


def _client_ip(request: Request) -> str | None:
    return client_ip_from_request(request, get_settings().trusted_proxy_count)


async def _record_denied(request: Request, reason: str) -> None:
    """Best-effort: a failure to log a denial must not turn a 403 into a 500."""
    from app.services.admin.audit import record_best_effort

    await record_best_effort(
        request.app.state.db,
        actor_user_id=getattr(request.state, "user_id", None),
        actor_email=None,
        actor_role=None,
        action="platform.access.denied",
        target_type="platform_console",
        target_id=request.url.path,
        tenant_id=None,
        outcome="denied",
        detail={
            "reason": reason,
            "method": request.method,
            "caller_tenant_id": str(getattr(request.state, "tenant_id", "") or ""),
        },
        ip_address=_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
        request_id=getattr(request.state, "request_id", None),
    )


async def _load_principal(request: Request) -> PlatformPrincipal:
    cached = getattr(request.state, "platform_principal", None)
    if isinstance(cached, PlatformPrincipal):
        return cached

    user_id = getattr(request.state, "user_id", None)
    tenant_id = getattr(request.state, "tenant_id", None)
    if user_id is None or tenant_id is None:
        raise AuthenticationError()

    try:
        async with request.app.state.db.session_no_rls(read_only=True) as session:
            row = (
                await session.execute(
                    select(PlatformAdmin.role, User.email, User.full_name)
                    .join(User, User.id == PlatformAdmin.user_id)
                    .join(Tenant, Tenant.id == User.tenant_id)
                    .where(
                        PlatformAdmin.user_id == user_id,
                        PlatformAdmin.is_active.is_(True),
                        User.is_active.is_(True),
                        User.tenant_id == tenant_id,
                        Tenant.is_operator.is_(True),
                        Tenant.status.not_in((TenantStatus.suspended, TenantStatus.cancelled)),
                    )
                )
            ).first()
    except Exception as exc:  # fail closed
        log.error("platform_authz.lookup_failed", error=str(exc))
        raise PermissionDeniedError(DENIED_DETAIL) from exc

    if row is None:
        await _record_denied(request, "not_a_platform_admin")
        raise PermissionDeniedError(DENIED_DETAIL)

    settings = get_settings()
    mfa_required = settings.platform_admin_mfa_required
    mfa_satisfied = (not mfa_required) or bool(getattr(request.state, "auth_second_factor", None))
    principal = _issue(
        user_id=user_id,
        tenant_id=tenant_id,
        email=str(row.email),
        full_name=row.full_name,
        role=PlatformRole(row.role),
        mfa_required=mfa_required,
        mfa_satisfied=mfa_satisfied,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
        request_id=getattr(request.state, "request_id", None),
    )
    request.state.platform_principal = principal
    return principal


async def require_platform_role(request: Request) -> PlatformPrincipal:
    """A platform role, without enforcing MFA. Used only by ``GET /admin/me``
    so the console can tell an operator they must enrol a second factor."""
    return await _load_principal(request)


async def require_platform_admin(request: Request) -> PlatformPrincipal:
    """Router-level dependency for every admin route except ``/admin/me``."""
    principal = await _load_principal(request)
    if not principal.mfa_satisfied:
        await _record_denied(request, "mfa_required")
        raise PermissionDeniedError(MFA_DETAIL)
    return principal


def require_permission(permission: Permission) -> Any:
    """Endpoint-level permission. Returns ``Depends(...)`` — use it directly."""

    async def _check(request: Request) -> PlatformPrincipal:
        # The router dependency normally ran first; if an endpoint were ever
        # mounted without it, run the full check here rather than trust nothing.
        principal = await require_platform_admin(request)
        if not principal.can(permission):
            await _record_denied(request, f"missing_permission:{permission.value}")
            raise PermissionDeniedError(f"Requires platform permission: {permission.value}")
        return principal

    return Depends(_check)


ReadPrincipal = Annotated[PlatformPrincipal, require_permission(Permission.platform_read)]
SupportPrincipal = Annotated[PlatformPrincipal, require_permission(Permission.support_open)]
TenantsWritePrincipal = Annotated[PlatformPrincipal, require_permission(Permission.tenants_write)]
TenantsArchivePrincipal = Annotated[
    PlatformPrincipal, require_permission(Permission.tenants_archive)
]
UsersWritePrincipal = Annotated[PlatformPrincipal, require_permission(Permission.users_write)]
BillingWritePrincipal = Annotated[PlatformPrincipal, require_permission(Permission.billing_write)]
BillingContractPrincipal = Annotated[
    PlatformPrincipal, require_permission(Permission.billing_contract)
]
DataWritePrincipal = Annotated[PlatformPrincipal, require_permission(Permission.data_write)]
JobsWritePrincipal = Annotated[PlatformPrincipal, require_permission(Permission.jobs_write)]
```

This imports `app.services.admin.audit.record_best_effort`, created in Task 1.4. To make this task's tests runnable now, create the package and a first version of that function in this task:

Create `backend/app/services/admin/__init__.py` containing only `"""Platform admin console services."""`.

Create `backend/app/services/admin/audit.py` (Task 1.4 extends it):

```python
"""Platform audit writers.

Two kinds of write, deliberately different:

* ``record_platform_event`` joins the caller's transaction and never swallows
  an error — if the audit row cannot be written, the action it describes rolls
  back with it (fail-closed, spec §6.6).
* ``record_best_effort`` opens its own transaction and swallows errors. Used
  only for denials and failures, which are recorded *because* something did not
  happen; losing one must not change the response.
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from fastapi.encoders import jsonable_encoder
from sqlalchemy import insert

from app.models.platform import PlatformAuditEvent

log = structlog.get_logger(__name__)


async def record_best_effort(
    db: Any,
    *,
    actor_user_id: uuid.UUID | None,
    actor_email: str | None,
    actor_role: str | None,
    action: str,
    target_type: str,
    target_id: str | None,
    tenant_id: uuid.UUID | None,
    outcome: str,
    detail: dict[str, Any] | None,
    ip_address: str | None,
    user_agent: str | None,
    request_id: str | None,
) -> None:
    try:
        async with db.session_no_rls() as session:
            await session.execute(
                insert(PlatformAuditEvent).values(
                    actor_user_id=actor_user_id,
                    actor_email=actor_email,
                    actor_role=actor_role,
                    action=action,
                    target_type=target_type,
                    target_id=target_id,
                    tenant_id=tenant_id,
                    outcome=outcome,
                    detail=jsonable_encoder(detail or {}),
                    ip_address=ip_address,
                    user_agent=user_agent,
                    request_id=request_id,
                )
            )
    except Exception as exc:  # noqa: BLE001 - best effort by definition
        log.error("platform_audit.best_effort_failed", action=action, error=str(exc))
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_platform_authz.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/platform_authz.py backend/app/services/admin/__init__.py \
  backend/app/services/admin/audit.py backend/tests/admin_factories.py \
  backend/tests/test_platform_authz.py
git commit -m "feat(authz): platform roles checked in the database on every admin request"
```

---

### Task 1.4: Fail-closed audit and the data-access wrappers

**Files:**
- Modify: `backend/app/services/admin/audit.py` (add `record_platform_event`, `record_read_event`)
- Create: `backend/app/services/admin/data_access.py`
- Test: `backend/tests/test_admin_audit.py`

**Interfaces:**
- Consumes: `PlatformPrincipal`, `_issue` (tests only), models.
- Produces:
  - `async def record_platform_event(session, principal, *, action: str, target_type: str, target_id: str | None = None, tenant: Tenant | None = None, tenant_id: uuid.UUID | None = None, detail: dict | None = None, outcome: str = "success", mirror: bool = False) -> None`
  - `async def record_read_event(db, principal, *, action, target_type, target_id=None, tenant_id=None, detail=None) -> None`
  - `data_access.platform_read(db, principal)` async CM → read-only bypass `AsyncSession`
  - `data_access.platform_write(db, principal)` async CM → writable bypass `AsyncSession`
  - `data_access.tenant_scope(db, principal, tenant_id)` async CM → `(AsyncSession, Tenant)`; raises `NotFoundError("Tenant")` for unknown or operator tenants.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_admin_audit.py`:

```python
"""Audit writers and data-access wrappers."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from admin_factories import create_customer_tenant, create_platform_admin
from app.config import get_settings
from app.core.database import Database
from app.core.exceptions import NotFoundError
from app.core.platform_authz import _issue
from app.models.platform import PlatformRole
from app.models.tenant import Tenant
from app.services.admin.audit import record_platform_event, record_read_event
from app.services.admin.data_access import platform_read, platform_write, tenant_scope

pytestmark = pytest.mark.asyncio


def _principal(user_id: uuid.UUID, tenant_id: uuid.UUID, email: str):
    return _issue(
        user_id=user_id,
        tenant_id=tenant_id,
        email=email,
        full_name="Ops Person",
        role=PlatformRole.platform_admin,
        mfa_required=False,
        mfa_satisfied=True,
        ip_address="10.0.0.1",
        user_agent="pytest",
        request_id="req-1",
    )


@pytest.fixture
async def db(setup_schema):
    get_settings.cache_clear()
    database = Database(get_settings())
    yield database
    await database.close()


async def test_mutation_audit_is_mirrored_into_the_tenant_log(
    db: Database, db_session: AsyncSession
) -> None:
    ops = await create_platform_admin(db_session)
    tenant_id = await create_customer_tenant(db_session)
    principal = _principal(ops.user_id, ops.tenant_id, ops.email)
    marker = f"platform.test.{uuid.uuid4().hex[:8]}"

    async with tenant_scope(db, principal, tenant_id) as (session, tenant):
        await record_platform_event(
            session, principal, action=marker, target_type="tenant",
            target_id=str(tenant_id), tenant=tenant, detail={"reason": "testing"}, mirror=True,
        )

    platform_rows = await db_session.execute(
        text("SELECT actor_email, tenant_id, outcome FROM platform_audit_events WHERE action = :a"),
        {"a": marker},
    )
    assert [(r.actor_email, r.tenant_id, r.outcome) for r in platform_rows] == [
        (ops.email, tenant_id, "success")
    ]
    mirrored = (
        await db_session.execute(
            text("SELECT user_id, new_value FROM audit_log WHERE action = :a"), {"a": marker}
        )
    ).one()
    assert mirrored.user_id == ops.user_id
    assert mirrored.new_value["actor_email"] == ops.email
    assert mirrored.new_value["actor_type"] == "platform_admin"
    assert mirrored.new_value["reason"] == "testing"


async def test_a_failed_audit_write_rolls_the_action_back(
    db: Database, db_session: AsyncSession
) -> None:
    ops = await create_platform_admin(db_session)
    tenant_id = await create_customer_tenant(db_session)
    principal = _principal(ops.user_id, ops.tenant_id, ops.email)
    new_name = f"Renamed {uuid.uuid4().hex[:6]}"

    with pytest.raises(Exception):  # noqa: B017, PT011 - any DB error proves the point
        async with tenant_scope(db, principal, tenant_id) as (session, tenant):
            tenant.display_name = new_name
            await session.flush()
            # outcome violates the CHECK constraint → the insert fails
            await record_platform_event(
                session, principal, action="platform.test", target_type="tenant",
                tenant=tenant, outcome="bogus",
            )

    stored = await db_session.scalar(
        select(Tenant.display_name).where(Tenant.id == tenant_id)
    )
    assert stored != new_name


async def test_read_events_are_recorded_in_their_own_transaction(
    db: Database, db_session: AsyncSession
) -> None:
    ops = await create_platform_admin(db_session)
    principal = _principal(ops.user_id, ops.tenant_id, ops.email)
    marker = f"platform.search.{uuid.uuid4().hex[:8]}"
    await record_read_event(db, principal, action=marker, target_type="search", detail={"q": "x"})
    count = await db_session.scalar(
        text("SELECT count(*) FROM platform_audit_events WHERE action = :a"), {"a": marker}
    )
    assert count == 1


async def test_platform_read_is_refused_writes_by_the_database(
    db: Database, db_session: AsyncSession
) -> None:
    ops = await create_platform_admin(db_session)
    principal = _principal(ops.user_id, ops.tenant_id, ops.email)
    with pytest.raises(Exception, match="read-only"):  # noqa: PT011
        async with platform_read(db, principal) as session:
            await session.execute(text("UPDATE tenants SET display_name = display_name"))


async def test_platform_read_sees_every_tenant(db: Database, db_session: AsyncSession) -> None:
    ops = await create_platform_admin(db_session)
    a = await create_customer_tenant(db_session)
    b = await create_customer_tenant(db_session)
    principal = _principal(ops.user_id, ops.tenant_id, ops.email)
    async with platform_read(db, principal) as session:
        ids = set((await session.execute(select(Tenant.id).where(Tenant.id.in_([a, b])))).scalars())
    assert ids == {a, b}


async def test_tenant_scope_is_rls_scoped_to_one_tenant(
    db: Database, db_session: AsyncSession
) -> None:
    ops = await create_platform_admin(db_session)
    a = await create_customer_tenant(db_session)
    b = await create_customer_tenant(db_session)
    principal = _principal(ops.user_id, ops.tenant_id, ops.email)
    async with tenant_scope(db, principal, a) as (session, tenant):
        assert tenant.id == a
        visible = set((await session.execute(select(Tenant.id))).scalars())
    assert visible == {a}, "a tenant-scoped admin session saw another tenant"
    assert b not in visible


async def test_tenant_scope_refuses_the_operator_tenant(
    db: Database, db_session: AsyncSession
) -> None:
    ops = await create_platform_admin(db_session)
    principal = _principal(ops.user_id, ops.tenant_id, ops.email)
    with pytest.raises(NotFoundError):
        async with tenant_scope(db, principal, ops.tenant_id):
            pass


async def test_tenant_scope_refuses_an_unknown_tenant(
    db: Database, db_session: AsyncSession
) -> None:
    ops = await create_platform_admin(db_session)
    principal = _principal(ops.user_id, ops.tenant_id, ops.email)
    with pytest.raises(NotFoundError):
        async with tenant_scope(db, principal, uuid.uuid4()):
            pass


async def test_platform_write_can_insert_support_sessions(
    db: Database, db_session: AsyncSession
) -> None:
    ops = await create_platform_admin(db_session)
    tenant_id = await create_customer_tenant(db_session)
    principal = _principal(ops.user_id, ops.tenant_id, ops.email)
    async with platform_write(db, principal) as session:
        await session.execute(
            text(
                "INSERT INTO support_access_sessions (tenant_id, admin_user_id, reason, expires_at) "
                "VALUES (:t, :u, 'checking the import errors', now() + interval '5 minutes')"
            ),
            {"t": str(tenant_id), "u": str(ops.user_id)},
        )
```

- [ ] **Step 2: Run to see failures**

Run: `uv run pytest tests/test_admin_audit.py -v`
Expected: FAIL — `ImportError: cannot import name 'record_platform_event'` / `No module named 'app.services.admin.data_access'`.

- [ ] **Step 3: Implement the data-access wrappers**

Create `backend/app/services/admin/data_access.py`:

```python
"""The console's only ways into the database.

* ``tenant_scope``   — per-tenant work. RLS scopes every statement to the tenant
  in the URL, so a bug cannot return a second tenant's rows. The operator tenant
  and unknown ids are a 404.
* ``platform_read``  — cross-tenant listings and totals. A bypass session opened
  READ ONLY, so the database refuses any write through it.
* ``platform_write`` — platform bookkeeping only: support sessions, read audits,
  and tenant creation (which cannot be scoped to a tenant that does not exist
  yet, exactly like /auth/signup). Never used to change tenant data.

Each takes a ``PlatformPrincipal``, which only ``platform_authz`` can issue, so
none of them can be reached from code that skipped authorization.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.platform_authz import PlatformPrincipal
from app.models.tenant import Tenant


def _require(principal: object) -> None:
    if not isinstance(principal, PlatformPrincipal):
        raise TypeError("a PlatformPrincipal from platform_authz is required")


@asynccontextmanager
async def platform_read(db: Any, principal: PlatformPrincipal) -> AsyncIterator[AsyncSession]:
    _require(principal)
    async with db.session_no_rls(read_only=True) as session:
        yield session


@asynccontextmanager
async def platform_write(db: Any, principal: PlatformPrincipal) -> AsyncIterator[AsyncSession]:
    _require(principal)
    async with db.session_no_rls() as session:
        yield session


@asynccontextmanager
async def tenant_scope(
    db: Any, principal: PlatformPrincipal, tenant_id: uuid.UUID
) -> AsyncIterator[tuple[AsyncSession, Tenant]]:
    _require(principal)
    async with db.session(str(tenant_id)) as session:
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None or tenant.is_operator:
            raise NotFoundError("Tenant")
        yield session, tenant
```

- [ ] **Step 4: Add the fail-closed writers to `audit.py`**

Append to `backend/app/services/admin/audit.py` (and add `from sqlalchemy.ext.asyncio import AsyncSession`, `from app.models.audit import AuditLog`, `from app.models.tenant import Tenant`, and `from app.core.platform_authz import PlatformPrincipal` under a `TYPE_CHECKING` guard — `platform_authz` imports this module lazily, so import `PlatformPrincipal` only for typing):

```python
async def record_platform_event(
    session: AsyncSession,
    principal: PlatformPrincipal,
    *,
    action: str,
    target_type: str,
    target_id: str | None = None,
    tenant: Tenant | None = None,
    tenant_id: uuid.UUID | None = None,
    detail: dict[str, Any] | None = None,
    outcome: str = "success",
    mirror: bool = False,
) -> None:
    """Append a platform event inside the caller's transaction. Never swallows.

    ``mirror=True`` also writes the action into the tenant's own ``audit_log``
    so the customer can see what SANKET staff did; spec §6.6 limits that to
    mutations and support-session open/end.
    """
    target_tenant_id = tenant.id if tenant is not None else tenant_id
    payload = jsonable_encoder(detail or {})
    await session.execute(
        insert(PlatformAuditEvent).values(
            actor_user_id=principal.user_id,
            actor_email=principal.email,
            actor_role=principal.role.value,
            action=action,
            target_type=target_type,
            target_id=target_id,
            tenant_id=target_tenant_id,
            outcome=outcome,
            detail=payload,
            ip_address=principal.ip_address,
            user_agent=principal.user_agent,
            request_id=principal.request_id,
        )
    )
    if mirror:
        if tenant is None:
            raise ValueError("mirroring into audit_log needs the Tenant row")
        await session.execute(
            insert(AuditLog).values(
                tenant_id=tenant.id,
                user_id=principal.user_id,
                industry=tenant.industry,
                action=action,
                entity_type=target_type,
                entity_id=target_id,
                new_value={
                    "actor_type": "platform_admin",
                    "actor_email": principal.email,
                    "actor_role": principal.role.value,
                    **payload,
                },
                ip_address=principal.ip_address,
                user_agent=principal.user_agent,
                request_id=principal.request_id,
            )
        )


async def record_read_event(
    db: Any,
    principal: PlatformPrincipal,
    *,
    action: str,
    target_type: str,
    target_id: str | None = None,
    tenant_id: uuid.UUID | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    """Audit a read (search, tenant view) in its own transaction.

    Fail-closed too: if this raises, the request fails rather than returning
    data whose access was not recorded.
    """
    from app.services.admin.data_access import platform_write

    async with platform_write(db, principal) as session:
        await record_platform_event(
            session,
            principal,
            action=action,
            target_type=target_type,
            target_id=target_id,
            tenant_id=tenant_id,
            detail=detail,
        )
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_admin_audit.py tests/test_platform_authz.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/admin/audit.py backend/app/services/admin/data_access.py \
  backend/tests/test_admin_audit.py
git commit -m "feat(admin): fail-closed platform audit and scoped data-access wrappers"
```

---

### Task 1.5: Admin router, `/admin/me`, `/admin/session`, and the route guard

**Files:**
- Create: `backend/app/schemas/admin.py`
- Create: `backend/app/routers/admin/__init__.py`
- Create: `backend/app/routers/admin/session.py`
- Modify: `backend/app/main.py` (include the admin router)
- Modify: `backend/app/middleware/rate_limit.py` (admin writes are heavy)
- Test: `backend/tests/test_admin_route_guard.py`, `backend/tests/test_admin_session.py`

**Interfaces:**
- Produces: `app.routers.admin.build_admin_router() -> APIRouter` (prefix `/admin`); module attribute `ROUTER_MODULES: list[ModuleType]` consumed by later tasks (each later router module is appended to this list); `schemas.admin.PlatformMeOut`.

- [ ] **Step 1: Write the failing route-guard test**

Create `backend/tests/test_admin_route_guard.py`:

```python
"""Every admin route independently refuses non-admins.

The route list is read from the application itself, so an endpoint added later
without the platform dependency fails here — nobody has to remember to add it
to this file.
"""

from __future__ import annotations

import re
import uuid

import pytest
from fastapi.routing import APIRoute
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from admin_factories import create_customer, create_customer_tenant

pytestmark = pytest.mark.asyncio

_PARAM = re.compile(r"\{[^}]+\}")


def _admin_routes(app) -> list[tuple[str, str]]:
    routes: list[tuple[str, str]] = []
    for route in app.routes:
        if isinstance(route, APIRoute) and route.path.startswith("/api/v1/admin"):
            for method in sorted(route.methods - {"HEAD", "OPTIONS"}):
                routes.append((method, _PARAM.sub(str(uuid.uuid4()), route.path)))
    return routes


async def test_admin_routes_exist(client: AsyncClient) -> None:
    assert len(_admin_routes(client._transport.app)) >= 2  # noqa: SLF001


async def test_every_admin_route_rejects_anonymous_callers(client: AsyncClient) -> None:
    for method, path in _admin_routes(client._transport.app):  # noqa: SLF001
        r = await client.request(method, path, json={})
        assert r.status_code == 401, f"{method} {path} answered {r.status_code} without a token"


@pytest.mark.parametrize("role", ["owner", "admin", "analyst", "viewer"])
async def test_every_admin_route_rejects_customer_roles(
    client: AsyncClient, db_session: AsyncSession, role: str
) -> None:
    tenant = await create_customer_tenant(db_session)
    customer = await create_customer(db_session, tenant, role=role)
    for method, path in _admin_routes(client._transport.app):  # noqa: SLF001
        r = await client.request(method, path, json={}, headers=customer.headers)
        assert r.status_code == 403, f"{method} {path} gave a {role} a {r.status_code}"
```

Create `backend/tests/test_admin_session.py`:

```python
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from admin_factories import create_platform_admin

pytestmark = pytest.mark.asyncio


async def test_me_describes_the_principal(client: AsyncClient, db_session: AsyncSession) -> None:
    ops = await create_platform_admin(db_session, "platform_support")
    r = await client.get("/api/v1/admin/me", headers=ops.headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["email"] == ops.email
    assert body["role"] == "platform_support"
    assert sorted(body["permissions"]) == ["platform:read", "support:open"]
    assert body["mfa_required"] is False
    assert body["mfa_satisfied"] is True
    assert body["environment"] == "development"


async def test_console_sign_in_is_audited(client: AsyncClient, db_session: AsyncSession) -> None:
    ops = await create_platform_admin(db_session)
    r = await client.post("/api/v1/admin/session", headers=ops.headers)
    assert r.status_code == 200, r.text
    count = await db_session.scalar(
        text(
            "SELECT count(*) FROM platform_audit_events "
            "WHERE actor_user_id = :u AND action = 'platform.console.sign_in'"
        ),
        {"u": str(ops.user_id)},
    )
    assert count == 1


async def test_admin_routes_are_not_behind_the_paywall(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The operator tenant has no subscription; the console must still work."""
    ops = await create_platform_admin(db_session)
    assert (await client.get("/api/v1/admin/me", headers=ops.headers)).status_code == 200
```

- [ ] **Step 2: Run to see failures**

Run: `uv run pytest tests/test_admin_route_guard.py tests/test_admin_session.py -v`
Expected: FAIL — `test_admin_routes_exist` asserts `0 >= 2`; `/api/v1/admin/me` is 401/404.

- [ ] **Step 3: Create the schemas module**

Create `backend/app/schemas/admin.py`:

```python
"""Request/response models for /api/v1/admin.

Every admin response is one of these — never an ORM object or a raw dict — so
the set of fields that can leave the server is written down here and nowhere
else. None of them may ever carry: password_hash, mfa_secret, firebase_uid,
integration state/credentials, access tokens, or token hashes
(tests/test_admin_secrets.py enforces this).
"""

from __future__ import annotations

import uuid
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

from app.models.platform import PlatformRole

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


class PlatformMeOut(BaseModel):
    user_id: uuid.UUID
    email: str
    full_name: str
    role: PlatformRole
    permissions: list[str]
    mfa_required: bool
    mfa_satisfied: bool
    environment: str


class ReasonIn(BaseModel):
    reason: str = Field(min_length=10, max_length=500)
```

- [ ] **Step 4: Create the session router and the router builder**

Create `backend/app/routers/admin/session.py`:

```python
"""Who am I, and record that I opened the console."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.config import get_settings
from app.core.platform_authz import PlatformPrincipal, ReadPrincipal, require_platform_role
from app.schemas.admin import PlatformMeOut
from app.services.admin.audit import record_platform_event
from app.services.admin.data_access import platform_write

# /me is mounted on a router whose dependency checks the role but NOT MFA, so
# an operator without a second factor can be told to enrol one.
me_router = APIRouter(tags=["platform-admin"])
router = APIRouter(tags=["platform-admin"])


def _me(principal: PlatformPrincipal) -> PlatformMeOut:
    return PlatformMeOut(
        user_id=principal.user_id,
        email=principal.email,
        full_name=principal.full_name,
        role=principal.role,
        permissions=sorted(p.value for p in principal.permissions),
        mfa_required=principal.mfa_required,
        mfa_satisfied=principal.mfa_satisfied,
        environment=get_settings().app_env,
    )


@me_router.get("/me", response_model=PlatformMeOut)
async def me(principal: PlatformPrincipal = Depends(require_platform_role)) -> PlatformMeOut:
    return _me(principal)


@router.post("/session", response_model=PlatformMeOut)
async def record_console_sign_in(request: Request, principal: ReadPrincipal) -> PlatformMeOut:
    async with platform_write(request.app.state.db, principal) as session:
        await record_platform_event(
            session, principal, action="platform.console.sign_in", target_type="platform_console"
        )
    return _me(principal)
```

Create `backend/app/routers/admin/__init__.py`:

```python
"""The /api/v1/admin router.

Two mounts, both under /admin:

* ``/me`` — platform role required, MFA reported but not enforced.
* everything else — ``require_platform_admin`` (role + MFA) attached once at
  include time, so a new endpoint inherits it by construction; each endpoint
  additionally declares its own permission.

Not behind the customer paywall: operators are not customers.
"""

from __future__ import annotations

from types import ModuleType

from fastapi import APIRouter, Depends

from app.core.platform_authz import require_platform_admin, require_platform_role
from app.routers.admin import session

# Each area module exposes `router`. Later tasks append their module here.
ROUTER_MODULES: list[ModuleType] = [session]


def build_admin_router() -> APIRouter:
    root = APIRouter(prefix="/admin")
    root.include_router(session.me_router, dependencies=[Depends(require_platform_role)])
    secured = APIRouter(dependencies=[Depends(require_platform_admin)])
    for module in ROUTER_MODULES:
        secured.include_router(module.router)
    root.include_router(secured)
    return root
```

- [ ] **Step 5: Mount it and make admin writes heavy**

In `backend/app/main.py`, directly after `app.include_router(billing_router, prefix=api_prefix)`, add:

```python
    # ── Platform admin console ───────────────────────────────────────────────
    # Deliberately NOT behind `gated`: operators are not customers, and the
    # operator tenant has no subscription. Every route in it requires a
    # database-checked platform role instead (core/platform_authz.py).
    from app.routers.admin import build_admin_router

    app.include_router(build_admin_router(), prefix=api_prefix)
```

In `backend/app/middleware/rate_limit.py`, replace `_is_heavy` and its call site:

```python
    def _is_heavy(self, path: str, method: str = "GET") -> bool:
        if any(path.startswith(prefix) for prefix in _HEAVY_PREFIXES):
            return True
        # Platform-console writes: low volume by nature, and each one changes a
        # customer workspace — a tight bucket costs operators nothing.
        return path.startswith("/api/v1/admin/") and method in _WRITE_METHODS
```

Add near `_HEAVY_PREFIXES`:

```python
_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
```

Find the existing `self._is_heavy(path)` call in `dispatch` and change it to `self._is_heavy(path, request.method)`.

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/test_admin_route_guard.py tests/test_admin_session.py tests/test_rate_limit.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/schemas/admin.py backend/app/routers/admin/__init__.py \
  backend/app/routers/admin/session.py backend/app/main.py backend/app/middleware/rate_limit.py \
  backend/tests/test_admin_route_guard.py backend/tests/test_admin_session.py
git commit -m "feat(admin): /api/v1/admin router with me/session and an automatic route guard"
```

---

### Task 1.6: Operator bootstrap CLI

**Files:**
- Create: `backend/app/services/admin/operator.py`
- Create: `backend/scripts/create_platform_admin.py`
- Test: `backend/tests/test_admin_operator.py`

**Interfaces:**
- Produces:
  - `async def ensure_operator_tenant(session) -> Tenant` — returns the operator tenant, creating it (slug from settings, `is_operator=True`, `status=active`, no onboarding key, no subscription) if missing. Raises `ValueError` if a *customer* tenant already uses the operator slug.
  - `async def grant_platform_role(session, *, email: str, full_name: str, role: PlatformRole, password_hash: str | None, firebase_uid: str | None, granted_by: uuid.UUID | None = None) -> PlatformAdmin` — creates the operator user if missing, upserts the role, reactivates if inactive.
  - `async def deactivate_platform_role(session, *, email: str) -> bool`.
  - CLI: `uv run python -m scripts.create_platform_admin --email E --name N --role R [--password-stdin] [--deactivate]`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_admin_operator.py`:

```python
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.database import Database
from app.models.platform import PlatformAdmin, PlatformRole
from app.models.tenant import Tenant, User
from app.services.admin.operator import (
    deactivate_platform_role,
    ensure_operator_tenant,
    grant_platform_role,
)

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def db(setup_schema):
    get_settings.cache_clear()
    database = Database(get_settings())
    yield database
    await database.close()


async def test_operator_tenant_is_created_once(db: Database) -> None:
    async with db.session_no_rls() as s:
        first = await ensure_operator_tenant(s)
    async with db.session_no_rls() as s:
        second = await ensure_operator_tenant(s)
    assert first.id == second.id
    assert first.is_operator is True
    assert first.slug == get_settings().platform_operator_tenant_slug
    assert "onboarding" not in (first.settings or {})


async def test_granting_creates_the_operator_user_and_role(
    db: Database, db_session: AsyncSession
) -> None:
    email = f"ops-{uuid.uuid4().hex[:8]}@sanket.test"
    async with db.session_no_rls() as s:
        row = await grant_platform_role(
            s, email=email, full_name="Ops One", role=PlatformRole.platform_super_admin,
            password_hash=None, firebase_uid=None,
        )
        assert row.role is PlatformRole.platform_super_admin
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    tenant = await db_session.get(Tenant, user.tenant_id)
    assert tenant is not None and tenant.is_operator


async def test_granting_again_changes_the_role_and_reactivates(db: Database) -> None:
    email = f"ops-{uuid.uuid4().hex[:8]}@sanket.test"
    async with db.session_no_rls() as s:
        await grant_platform_role(
            s, email=email, full_name="Ops Two", role=PlatformRole.platform_support,
            password_hash=None, firebase_uid=None,
        )
    async with db.session_no_rls() as s:
        assert await deactivate_platform_role(s, email=email) is True
    async with db.session_no_rls() as s:
        row = await grant_platform_role(
            s, email=email, full_name="Ops Two", role=PlatformRole.platform_admin,
            password_hash=None, firebase_uid=None,
        )
        assert row.role is PlatformRole.platform_admin
        assert row.is_active is True


async def test_a_customer_email_cannot_be_granted(db: Database, db_session: AsyncSession) -> None:
    """The email belongs to a customer user: refuse rather than create a twin."""
    tid = uuid.uuid4()
    email = f"cust-{tid.hex[:8]}@customer.test"
    await db_session.execute(
        text(
            "INSERT INTO tenants (id, slug, display_name, tier, status, industry) "
            "VALUES (:id, :slug, 'Cust', 'growth', 'active', 'fashion')"
        ),
        {"id": str(tid), "slug": f"c-{tid.hex[:8]}"},
    )
    await db_session.execute(
        text(
            "INSERT INTO users (tenant_id, email, full_name, role, active_industry) "
            "VALUES (:t, :e, 'Customer', 'owner', 'fashion')"
        ),
        {"t": str(tid), "e": email},
    )
    await db_session.commit()
    with pytest.raises(ValueError, match="customer"):
        async with db.session_no_rls() as s:
            await grant_platform_role(
                s, email=email, full_name="X", role=PlatformRole.platform_admin,
                password_hash=None, firebase_uid=None,
            )


async def test_deactivating_an_unknown_email_reports_false(db: Database) -> None:
    async with db.session_no_rls() as s:
        assert await deactivate_platform_role(s, email="nobody@nowhere.test") is False


async def test_role_rows_reference_operator_users_only(db_session: AsyncSession) -> None:
    rows = (
        await db_session.execute(
            select(Tenant.is_operator)
            .join(User, User.tenant_id == Tenant.id)
            .join(PlatformAdmin, PlatformAdmin.user_id == User.id)
        )
    ).scalars().all()
    assert all(rows)
```

- [ ] **Step 2: Run to see failures**

Run: `uv run pytest tests/test_admin_operator.py -v`
Expected: FAIL — `No module named 'app.services.admin.operator'`.

- [ ] **Step 3: Implement the operator service**

Create `backend/app/services/admin/operator.py`:

```python
"""The operator tenant and platform-role grants. CLI-only in this version.

No HTTP endpoint grants a platform role, so nothing reachable from a browser
can escalate itself; this module is called from scripts/create_platform_admin.py
by someone who already holds database credentials.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.enums import IndustryCode, TenantStatus, TenantTier, UserRole
from app.models.platform import PlatformAdmin, PlatformRole
from app.models.tenant import Tenant, User


async def ensure_operator_tenant(session: AsyncSession) -> Tenant:
    existing = await session.scalar(select(Tenant).where(Tenant.is_operator.is_(True)))
    if existing is not None:
        return existing
    slug = get_settings().platform_operator_tenant_slug
    clash = await session.scalar(select(Tenant).where(Tenant.slug == slug))
    if clash is not None:
        raise ValueError(
            f"A customer tenant already uses the operator slug '{slug}'. "
            "Set PLATFORM_OPERATOR_TENANT_SLUG to an unused slug."
        )
    tenant = Tenant(
        id=uuid.uuid4(),
        slug=slug,
        display_name="SANKET Platform",
        tier=TenantTier.enterprise,
        status=TenantStatus.active,
        # Required by the schema; meaningless here. Operators never use modules.
        industry=IndustryCode.fashion,
        max_skus=0,
        max_users=500,
        data_retention_days=3650,
        # No `onboarding` key → never routed into the customer setup wizard.
        settings={},
        is_operator=True,
    )
    session.add(tenant)
    await session.flush()
    return tenant


async def grant_platform_role(
    session: AsyncSession,
    *,
    email: str,
    full_name: str,
    role: PlatformRole,
    password_hash: str | None,
    firebase_uid: str | None,
    granted_by: uuid.UUID | None = None,
) -> PlatformAdmin:
    operator = await ensure_operator_tenant(session)
    user = await session.scalar(select(User).where(User.email == email))
    if user is not None and user.tenant_id != operator.id:
        raise ValueError(
            f"{email} belongs to a customer workspace. Platform roles are held only "
            "by operator-tenant accounts; use a separate SANKET staff address."
        )
    if user is None:
        user = User(
            id=uuid.uuid4(),
            tenant_id=operator.id,
            email=email,
            full_name=full_name,
            role=UserRole.admin,
            password_hash=password_hash,
            firebase_uid=firebase_uid,
            is_active=True,
        )
        session.add(user)
        await session.flush()
    else:
        user.is_active = True
        if password_hash:
            user.password_hash = password_hash
        if firebase_uid:
            user.firebase_uid = firebase_uid

    row = await session.scalar(select(PlatformAdmin).where(PlatformAdmin.user_id == user.id))
    if row is None:
        row = PlatformAdmin(user_id=user.id, role=role, is_active=True, granted_by=granted_by)
        session.add(row)
    else:
        row.role = role
        row.is_active = True
        row.granted_by = granted_by
    await session.flush()
    return row


async def deactivate_platform_role(session: AsyncSession, *, email: str) -> bool:
    user = await session.scalar(select(User).where(User.email == email))
    if user is None:
        return False
    row = await session.scalar(select(PlatformAdmin).where(PlatformAdmin.user_id == user.id))
    if row is None:
        return False
    row.is_active = False
    await session.flush()
    return True
```

- [ ] **Step 4: Write the CLI**

Create `backend/scripts/create_platform_admin.py`:

```python
"""Grant or revoke a SANKET platform-console role.

    cd backend
    uv run python -m scripts.create_platform_admin --email ops@sanket.app \
        --name "Ops Person" --role platform_super_admin --password-stdin

* Dev (no Firebase): --password-stdin reads a password from stdin and stores an
  Argon2 hash so the operator can use dev-login with the operator workspace.
* Firebase: the account is created (or found) in Firebase; set its password
  there (or pass --password-stdin to set it now). Production requires MFA — the
  operator enrols a second factor at /admin/security after first sign-in.
* --deactivate removes console access immediately (the next request is refused).

Connects with DATABASE_URL as the application role and uses the same privileged
session every other cross-tenant server path uses. It never needs a superuser.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.config import get_settings
from app.core.database import Database
from app.core.firebase_auth import get_verifier
from app.core.security import hash_password
from app.models.platform import PlatformRole
from app.services.admin.operator import deactivate_platform_role, grant_platform_role


def _parse(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--email", required=True)
    p.add_argument("--name", default="SANKET Operator")
    p.add_argument("--role", choices=[r.value for r in PlatformRole], default="platform_admin")
    p.add_argument("--password-stdin", action="store_true")
    p.add_argument("--deactivate", action="store_true")
    return p.parse_args(argv)


async def _run(args: argparse.Namespace) -> int:
    import app.models  # noqa: F401 - register every mapper

    settings = get_settings()
    db = Database(settings)
    try:
        if args.deactivate:
            async with db.session_no_rls() as session:
                changed = await deactivate_platform_role(session, email=args.email)
            print("deactivated" if changed else "no platform role found for that email")
            return 0 if changed else 1

        password = sys.stdin.readline().rstrip("\n") if args.password_stdin else None
        if password is not None and len(password) < 12:
            print("password must be at least 12 characters", file=sys.stderr)
            return 2

        firebase_uid = None
        if settings.firebase_enabled:
            firebase_uid = get_verifier().create_or_get_user(
                email=args.email,
                password=password,
                display_name=args.name,
                reset_password=password is not None,
            )
        password_hash = (
            hash_password(password, settings)
            if password is not None and not settings.firebase_enabled
            else None
        )
        async with db.session_no_rls() as session:
            row = await grant_platform_role(
                session,
                email=args.email,
                full_name=args.name,
                role=PlatformRole(args.role),
                password_hash=password_hash,
                firebase_uid=firebase_uid,
            )
            role = row.role.value
        print(f"{args.email}: {role} (active)")
        print(f"sign in at /admin/login (workspace: {settings.platform_operator_tenant_slug})")
        return 0
    finally:
        await db.close()


def main() -> None:
    raise SystemExit(asyncio.run(_run(_parse(sys.argv[1:]))))


if __name__ == "__main__":
    main()
```

(Check `backend/scripts/` is importable as a package: if `backend/scripts/__init__.py` does not exist, create it empty.)

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_admin_operator.py -v`
Expected: all PASS.

- [ ] **Step 6: Smoke-test the CLI's argument parsing**

Run: `uv run python -m scripts.create_platform_admin --help`
Expected: usage text listing `--email`, `--role {platform_super_admin,platform_admin,platform_support}`.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/admin/operator.py backend/scripts/create_platform_admin.py \
  backend/tests/test_admin_operator.py
git add backend/scripts/__init__.py 2>/dev/null || true
git commit -m "feat(admin): operator tenant bootstrap and platform-role CLI"
```

---

# M2 — Backend read side

### Task 2.1: Tenant directory — list, filters, slug availability

**Files:**
- Modify: `backend/tests/admin_factories.py` (add `create_sku`)
- Modify: `backend/app/core/entitlement.py` (add `evaluate_entitlement`)
- Create: `backend/app/services/admin/directory.py`
- Modify: `backend/app/schemas/admin.py` (add `TenantListItemOut`, `SlugAvailabilityOut`)
- Create: `backend/app/routers/admin/tenants.py`
- Modify: `backend/app/routers/admin/__init__.py` (append `tenants` to `ROUTER_MODULES`)
- Test: `backend/tests/test_admin_tenants_read.py`

**Interfaces:**
- Produces:
  - `app.core.entitlement.evaluate_entitlement(status: SubscriptionStatus | None, period_end: datetime | None, *, now: datetime | None = None) -> bool`
  - `directory.subscription_state(status, period_end, *, plan_price_cents: int | None, plan_razorpay_id: str | None, now: datetime) -> str` — one of `none, active, trialing, expired, pending_payment, pending_contract, past_due, paused, cancelled`
  - `directory.activity_bucket(last: datetime | None, now: datetime) -> str` — `7d, 30d, dormant, never`
  - `directory.tenant_health(*, integration_errors: int, failed_jobs_24h: int, stale_jobs: int, sub_state: str, over_limit: bool) -> str` — `green, yellow, red`
  - `directory.stale_condition(now)` — SQL expression over `HybridForecastRun`
  - `directory.escape_like(value: str) -> str`
  - `directory.reserved_slugs() -> frozenset[str]`
  - `@dataclass(frozen=True) directory.TenantRow` (fields listed in the code below)
  - `async directory.tenant_rows(session, *, tenant_ids: list[UUID] | None = None) -> list[TenantRow]`
  - `@dataclass(frozen=True) directory.TenantFilters(q, industry, status, subscription, onboarding, activity, health)`
  - `directory.select_page(rows, filters, sort: str, page: int, page_size: int) -> tuple[list[TenantRow], int]`
  - `routers.admin.tenants.router` (prefix `/tenants`)

- [ ] **Step 1: Add a SKU factory, then write the failing tests**

Append to `backend/tests/admin_factories.py`:

```python
async def create_sku(
    db: AsyncSession, tenant_id: uuid.UUID, *, industry: str = "fashion", code: str | None = None
) -> uuid.UUID:
    """One product + one active SKU (products.name/category are the only
    required product columns)."""
    product_id, sku_id = uuid.uuid4(), uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO products (id, tenant_id, industry, name, category) "
            "VALUES (:p, :t, CAST(:i AS industry_code), 'Test product', 'Test')"
        ),
        {"p": str(product_id), "t": str(tenant_id), "i": industry},
    )
    await db.execute(
        text(
            "INSERT INTO skus (id, tenant_id, product_id, industry, sku_code) "
            "VALUES (:s, :t, :p, CAST(:i AS industry_code), :c)"
        ),
        {
            "s": str(sku_id),
            "t": str(tenant_id),
            "p": str(product_id),
            "i": industry,
            "c": code or f"SKU-{sku_id.hex[:8]}",
        },
    )
    await db.commit()
    return sku_id
```

Create `backend/tests/test_admin_tenants_read.py`:

```python
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from admin_factories import create_customer, create_customer_tenant, create_platform_admin, create_sku
from app.config import get_settings
from app.core.entitlement import evaluate_entitlement
from app.models.billing import SubscriptionStatus
from app.services.admin.directory import activity_bucket, subscription_state, tenant_health

pytestmark = pytest.mark.asyncio

NOW = datetime(2026, 9, 10, 12, tzinfo=UTC)


# ── Pure rules ───────────────────────────────────────────────────────────────


async def test_entitlement_rule() -> None:
    later = NOW + timedelta(days=1)
    assert evaluate_entitlement(SubscriptionStatus.active, later, now=NOW)
    assert evaluate_entitlement(SubscriptionStatus.trialing, later, now=NOW)
    assert not evaluate_entitlement(SubscriptionStatus.active, NOW - timedelta(seconds=1), now=NOW)
    assert not evaluate_entitlement(SubscriptionStatus.past_due, later, now=NOW)
    assert not evaluate_entitlement(None, None, now=NOW)


@pytest.mark.parametrize(
    ("status", "delta", "price", "rzp", "expected"),
    [
        (None, None, None, None, "none"),
        (SubscriptionStatus.active, 1, 499500, "plan_x", "active"),
        (SubscriptionStatus.trialing, 1, 499500, "plan_x", "trialing"),
        (SubscriptionStatus.active, -1, 499500, "plan_x", "expired"),
        (SubscriptionStatus.incomplete, 1, 0, None, "pending_contract"),
        (SubscriptionStatus.incomplete, 1, 499500, "plan_x", "pending_payment"),
        (SubscriptionStatus.past_due, 1, 499500, "plan_x", "past_due"),
        (SubscriptionStatus.cancelled, -1, 499500, "plan_x", "cancelled"),
    ],
)
async def test_subscription_state(status, delta, price, rzp, expected) -> None:
    end = NOW + timedelta(days=delta) if delta is not None else None
    state = subscription_state(status, end, plan_price_cents=price, plan_razorpay_id=rzp, now=NOW)
    assert state == expected


async def test_activity_buckets() -> None:
    assert activity_bucket(None, NOW) == "never"
    assert activity_bucket(NOW - timedelta(days=2), NOW) == "7d"
    assert activity_bucket(NOW - timedelta(days=20), NOW) == "30d"
    assert activity_bucket(NOW - timedelta(days=90), NOW) == "dormant"


async def test_health_rule() -> None:
    base = {"integration_errors": 0, "failed_jobs_24h": 0, "stale_jobs": 0, "over_limit": False}
    assert tenant_health(**base, sub_state="active") == "green"
    assert tenant_health(**base, sub_state="none") == "yellow"
    assert tenant_health(**{**base, "stale_jobs": 1}, sub_state="active") == "yellow"
    assert tenant_health(**{**base, "over_limit": True}, sub_state="active") == "yellow"
    assert tenant_health(**{**base, "integration_errors": 1}, sub_state="active") == "red"
    assert tenant_health(**{**base, "failed_jobs_24h": 2}, sub_state="active") == "red"
    assert tenant_health(**base, sub_state="past_due") == "red"


# ── Endpoint ─────────────────────────────────────────────────────────────────


async def _items(client: AsyncClient, headers: dict, **params) -> dict:
    r = await client.get("/api/v1/admin/tenants", params=params, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def test_list_shows_derived_columns(client: AsyncClient, db_session: AsyncSession) -> None:
    ops = await create_platform_admin(db_session, "platform_support")
    tid = await create_customer_tenant(db_session, industry="fashion")
    await create_customer(db_session, tid, role="owner")
    await create_sku(db_session, tid)

    body = await _items(client, ops.headers, q=str(tid))
    assert body["total"] == 1
    row = body["items"][0]
    assert row["id"] == str(tid)
    assert row["user_count"] == 1
    assert row["sku_count"] == 1
    assert row["plan_id"] == "growth_monthly"
    assert row["subscription_state"] == "active"
    assert row["health"] == "green"
    assert row["activity"] == "never"
    assert row["onboarding_status"] == "complete"


async def test_operator_tenant_is_never_listed(client: AsyncClient, db_session: AsyncSession) -> None:
    ops = await create_platform_admin(db_session)
    body = await _items(client, ops.headers, page_size=100, q=get_settings().platform_operator_tenant_slug)
    assert all(item["id"] != str(ops.tenant_id) for item in body["items"])


async def test_filters(client: AsyncClient, db_session: AsyncSession) -> None:
    ops = await create_platform_admin(db_session)
    tag = uuid.uuid4().hex[:6]
    pharma = await create_customer_tenant(db_session, slug=f"flt-{tag}-pharma", industry="pharma")
    unpaid = await create_customer_tenant(db_session, slug=f"flt-{tag}-unpaid", subscribed=False)
    suspended = await create_customer_tenant(db_session, slug=f"flt-{tag}-susp", status="suspended")
    broken = await create_customer_tenant(db_session, slug=f"flt-{tag}-broken")
    await db_session.execute(
        text(
            "INSERT INTO integration_connections (tenant_id, provider, status, target_industry, "
            "error_message, last_sync_stats, state) "
            "VALUES (:t, 'shopify', 'error', 'fashion', 'token expired', '{}'::jsonb, '{}'::jsonb)"
        ),
        {"t": str(broken)},
    )
    await db_session.commit()

    def ids(body: dict) -> set[str]:
        return {i["id"] for i in body["items"]}

    assert ids(await _items(client, ops.headers, q=f"flt-{tag}", industry="pharma")) == {str(pharma)}
    assert ids(await _items(client, ops.headers, q=f"flt-{tag}", subscription="none")) == {str(unpaid)}
    assert ids(await _items(client, ops.headers, q=f"flt-{tag}", status="suspended")) == {str(suspended)}
    assert ids(await _items(client, ops.headers, q=f"flt-{tag}", health="red")) == {str(broken)}


async def test_pagination(client: AsyncClient, db_session: AsyncSession) -> None:
    ops = await create_platform_admin(db_session)
    tag = uuid.uuid4().hex[:6]
    for i in range(3):
        await create_customer_tenant(db_session, slug=f"pg-{tag}-{i}")
    first = await _items(client, ops.headers, q=f"pg-{tag}", page_size=2, page=1, sort="name")
    second = await _items(client, ops.headers, q=f"pg-{tag}", page_size=2, page=2, sort="name")
    assert first["total"] == 3
    assert len(first["items"]) == 2
    assert len(second["items"]) == 1
    names = [i["slug"] for i in first["items"] + second["items"]]
    assert names == sorted(names)


async def test_slug_availability(client: AsyncClient, db_session: AsyncSession) -> None:
    ops = await create_platform_admin(db_session)
    taken = await create_customer_tenant(db_session)
    slug = (await db_session.execute(text("SELECT slug FROM tenants WHERE id = :t"), {"t": str(taken)})).scalar_one()

    async def check(value: str) -> dict:
        r = await client.get("/api/v1/admin/tenants/slug-available", params={"slug": value}, headers=ops.headers)
        assert r.status_code == 200, r.text
        return r.json()

    assert (await check(slug))["available"] is False
    assert (await check(get_settings().platform_operator_tenant_slug))["reason"] == "reserved"
    assert (await check(get_settings().sandbox_tenant_slug))["reason"] == "reserved"
    assert (await check(f"fresh-{uuid.uuid4().hex[:8]}"))["available"] is True
    bad = await client.get("/api/v1/admin/tenants/slug-available", params={"slug": "Bad Slug"}, headers=ops.headers)
    assert bad.status_code == 422
```

- [ ] **Step 2: Run to see failures**

Run: `uv run pytest tests/test_admin_tenants_read.py -v`
Expected: FAIL — `ImportError: cannot import name 'evaluate_entitlement'`.

- [ ] **Step 3: Add `evaluate_entitlement`**

In `backend/app/core/entitlement.py`, add after `ENTITLED_STATUSES`:

```python
def evaluate_entitlement(
    status: SubscriptionStatus | None,
    period_end: datetime | None,
    *,
    now: datetime | None = None,
) -> bool:
    """Whether a subscription in this state grants access right now.

    The rule ``require_active_subscription`` enforces, as a pure function, so the
    platform console can *show* entitlement without re-deriving it. The two must
    never disagree: change one, change both.
    """
    if status is None or period_end is None:
        return False
    return status in ENTITLED_STATUSES and period_end > (now or datetime.now(tz=UTC))
```

- [ ] **Step 4: Implement the directory service**

Create `backend/app/services/admin/directory.py`:

```python
"""Cross-tenant directory for the platform console.

Runs in ``platform_read`` (read-only bypass). The tenant list is aggregated in
one SQL pass and then filtered, sorted and paged in Python: subscription state,
health and activity are *rules*, and keeping each rule in exactly one Python
function is what makes the list, the dashboard and the detail page agree.
Comfortable into the low thousands of tenants.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.entitlement import evaluate_entitlement
from app.models.billing import Plan, Subscription, SubscriptionStatus
from app.models.integration import IntegrationConnection
from app.models.invite import Invite, InviteStatus
from app.models.product import Sku
from app.models.tenant import Tenant, User
from app.models.trend import HybridForecastRun

STALE_PENDING = timedelta(minutes=15)
STALE_RUNNING = timedelta(minutes=20)
NEAR_LIMIT = 0.8


def subscription_state(
    status: SubscriptionStatus | None,
    period_end: datetime | None,
    *,
    plan_price_cents: int | None,
    plan_razorpay_id: str | None,
    now: datetime,
) -> str:
    if status is None:
        return "none"
    if evaluate_entitlement(status, period_end, now=now):
        return "trialing" if status is SubscriptionStatus.trialing else "active"
    if status in (SubscriptionStatus.active, SubscriptionStatus.trialing):
        return "expired"
    if status is SubscriptionStatus.incomplete:
        custom = (plan_price_cents or 0) == 0 and not plan_razorpay_id
        return "pending_contract" if custom else "pending_payment"
    return status.value  # past_due, paused, cancelled


def activity_bucket(last: datetime | None, now: datetime) -> str:
    if last is None:
        return "never"
    age = now - last
    if age <= timedelta(days=7):
        return "7d"
    if age <= timedelta(days=30):
        return "30d"
    return "dormant"


def tenant_health(
    *,
    integration_errors: int,
    failed_jobs_24h: int,
    stale_jobs: int,
    sub_state: str,
    over_limit: bool,
) -> str:
    if integration_errors or failed_jobs_24h or sub_state == "past_due":
        return "red"
    if stale_jobs or over_limit or sub_state not in ("active", "trialing"):
        return "yellow"
    return "green"


def stale_condition(now: datetime):  # noqa: ANN201 - SQLAlchemy expression
    return or_(
        and_(
            HybridForecastRun.status == "pending",
            HybridForecastRun.created_at < now - STALE_PENDING,
        ),
        and_(
            HybridForecastRun.status == "running",
            HybridForecastRun.created_at < now - STALE_RUNNING,
        ),
    )


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def reserved_slugs() -> frozenset[str]:
    settings = get_settings()
    return frozenset({settings.platform_operator_tenant_slug, settings.sandbox_tenant_slug})


@dataclass(frozen=True)
class TenantRow:
    id: uuid.UUID
    slug: str
    display_name: str
    industry: str
    status: str
    created_at: datetime
    home_region: str
    max_skus: int
    max_users: int
    onboarding_status: str
    user_count: int
    sku_count: int
    pending_invites: int
    last_activity_at: datetime | None
    plan_id: str | None
    plan_name: str | None
    subscription_status: str | None
    subscription_state: str
    current_period_end: datetime | None
    integration_errors: int
    failed_jobs_24h: int
    stale_jobs: int
    is_sandbox: bool
    activity: str
    health: str
    over_limit: bool
    near_limit: bool


async def tenant_rows(
    session: AsyncSession, *, tenant_ids: list[uuid.UUID] | None = None
) -> list[TenantRow]:
    now = datetime.now(tz=UTC)
    users = (
        select(
            User.tenant_id.label("tid"),
            func.count().filter(User.is_active.is_(True)).label("n"),
            func.max(User.last_login_at).label("last_login"),
        )
        .group_by(User.tenant_id)
        .subquery()
    )
    skus = (
        select(Sku.tenant_id.label("tid"), func.count().label("n"))
        .where(Sku.is_active.is_(True))
        .group_by(Sku.tenant_id)
        .subquery()
    )
    invites = (
        select(Invite.tenant_id.label("tid"), func.count().label("n"))
        .where(Invite.status == InviteStatus.pending)
        .group_by(Invite.tenant_id)
        .subquery()
    )
    ranked = select(
        Subscription.tenant_id.label("tid"),
        Subscription.plan_id.label("plan_id"),
        Subscription.status.label("sub_status"),
        Subscription.current_period_end.label("period_end"),
        func.row_number()
        .over(partition_by=Subscription.tenant_id, order_by=Subscription.created_at.desc())
        .label("rn"),
    ).subquery()
    latest = select(ranked).where(ranked.c.rn == 1).subquery()
    integ = (
        select(IntegrationConnection.tenant_id.label("tid"), func.count().label("n"))
        .where(IntegrationConnection.status == "error")
        .group_by(IntegrationConnection.tenant_id)
        .subquery()
    )
    jobs = (
        select(
            HybridForecastRun.tenant_id.label("tid"),
            func.count()
            .filter(
                and_(
                    HybridForecastRun.status == "failed",
                    HybridForecastRun.created_at >= now - timedelta(hours=24),
                )
            )
            .label("failed"),
            func.count().filter(stale_condition(now)).label("stale"),
        )
        .group_by(HybridForecastRun.tenant_id)
        .subquery()
    )
    onboarding = func.coalesce(Tenant.settings.op("#>>")("{onboarding,status}"), "complete")
    stmt = (
        select(
            Tenant.id,
            Tenant.slug,
            Tenant.display_name,
            Tenant.industry,
            Tenant.status,
            Tenant.created_at,
            Tenant.home_region,
            Tenant.max_skus,
            Tenant.max_users,
            onboarding.label("onboarding_status"),
            func.coalesce(users.c.n, 0).label("user_count"),
            users.c.last_login,
            func.coalesce(skus.c.n, 0).label("sku_count"),
            func.coalesce(invites.c.n, 0).label("pending_invites"),
            latest.c.plan_id,
            latest.c.sub_status,
            latest.c.period_end,
            Plan.display_name.label("plan_name"),
            Plan.base_price_cents,
            Plan.razorpay_plan_id,
            func.coalesce(integ.c.n, 0).label("integration_errors"),
            func.coalesce(jobs.c.failed, 0).label("failed_jobs"),
            func.coalesce(jobs.c.stale, 0).label("stale_jobs"),
        )
        .outerjoin(users, users.c.tid == Tenant.id)
        .outerjoin(skus, skus.c.tid == Tenant.id)
        .outerjoin(invites, invites.c.tid == Tenant.id)
        .outerjoin(latest, latest.c.tid == Tenant.id)
        .outerjoin(Plan, Plan.id == latest.c.plan_id)
        .outerjoin(integ, integ.c.tid == Tenant.id)
        .outerjoin(jobs, jobs.c.tid == Tenant.id)
        .where(Tenant.is_operator.is_(False))
    )
    if tenant_ids is not None:
        stmt = stmt.where(Tenant.id.in_(tenant_ids))

    sandbox = get_settings().sandbox_tenant_slug
    out: list[TenantRow] = []
    for r in (await session.execute(stmt)).all():
        status = SubscriptionStatus(r.sub_status) if r.sub_status is not None else None
        state = subscription_state(
            status,
            r.period_end,
            plan_price_cents=r.base_price_cents,
            plan_razorpay_id=r.razorpay_plan_id,
            now=now,
        )
        over = r.sku_count > r.max_skus or r.user_count > r.max_users
        near = over or (
            (r.max_skus > 0 and r.sku_count >= NEAR_LIMIT * r.max_skus)
            or (r.max_users > 0 and r.user_count >= NEAR_LIMIT * r.max_users)
        )
        out.append(
            TenantRow(
                id=r.id,
                slug=str(r.slug),
                display_name=r.display_name,
                industry=getattr(r.industry, "value", str(r.industry)),
                status=getattr(r.status, "value", str(r.status)),
                created_at=r.created_at,
                home_region=str(r.home_region),
                max_skus=r.max_skus,
                max_users=r.max_users,
                onboarding_status=str(r.onboarding_status),
                user_count=r.user_count,
                sku_count=r.sku_count,
                pending_invites=r.pending_invites,
                last_activity_at=r.last_login,
                plan_id=r.plan_id,
                plan_name=r.plan_name,
                subscription_status=status.value if status else None,
                subscription_state=state,
                current_period_end=r.period_end,
                integration_errors=r.integration_errors,
                failed_jobs_24h=r.failed_jobs,
                stale_jobs=r.stale_jobs,
                is_sandbox=str(r.slug) == sandbox,
                activity=activity_bucket(r.last_login, now),
                health=tenant_health(
                    integration_errors=r.integration_errors,
                    failed_jobs_24h=r.failed_jobs,
                    stale_jobs=r.stale_jobs,
                    sub_state=state,
                    over_limit=over,
                ),
                over_limit=over,
                near_limit=near,
            )
        )
    return out


@dataclass(frozen=True)
class TenantFilters:
    q: str | None = None
    industry: str | None = None
    status: str | None = None
    subscription: str | None = None
    onboarding: str | None = None
    activity: str | None = None
    health: str | None = None


def _matches(row: TenantRow, f: TenantFilters) -> bool:
    if f.q:
        needle = f.q.strip().lower()
        try:
            if uuid.UUID(needle) != row.id:
                return False
        except ValueError:
            if needle not in row.slug.lower() and needle not in row.display_name.lower():
                return False
    checks = (
        (f.industry, row.industry),
        (f.status, row.status),
        (f.subscription, row.subscription_state),
        (f.onboarding, row.onboarding_status),
        (f.activity, row.activity),
        (f.health, row.health),
    )
    return all(wanted is None or wanted == actual for wanted, actual in checks)


_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
SORTS = {
    "created_desc": (lambda r: r.created_at, True),
    "name": (lambda r: r.display_name.lower(), False),
    "last_activity": (lambda r: r.last_activity_at or _EPOCH, True),
    "users": (lambda r: r.user_count, True),
    "skus": (lambda r: r.sku_count, True),
}


def select_page(
    rows: list[TenantRow], filters: TenantFilters, sort: str, page: int, page_size: int
) -> tuple[list[TenantRow], int]:
    matched = [r for r in rows if _matches(r, filters)]
    key, reverse = SORTS.get(sort, SORTS["created_desc"])
    matched.sort(key=key, reverse=reverse)
    start = (page - 1) * page_size
    return matched[start : start + page_size], len(matched)
```

- [ ] **Step 5: Add the schemas**

Append to `backend/app/schemas/admin.py` (add `from datetime import datetime` to the imports):

```python
class TenantListItemOut(BaseModel):
    model_config = {"from_attributes": True}

    id: uuid.UUID
    slug: str
    display_name: str
    industry: str
    status: str
    is_sandbox: bool
    created_at: datetime
    home_region: str
    last_activity_at: datetime | None
    activity: str
    user_count: int
    pending_invites: int
    sku_count: int
    max_skus: int
    max_users: int
    plan_id: str | None
    plan_name: str | None
    subscription_state: str
    current_period_end: datetime | None
    onboarding_status: str
    health: str
    over_limit: bool
    near_limit: bool
    integration_errors: int
    failed_jobs_24h: int
    stale_jobs: int


class SlugAvailabilityOut(BaseModel):
    slug: str
    available: bool
    reason: str | None = None
```

- [ ] **Step 6: Add the router**

Create `backend/app/routers/admin/tenants.py`:

```python
"""Tenants — directory, availability, overview, lifecycle.

Route order matters: literal paths (`/slug-available`) are declared before
`/{tenant_id}` so they are not captured as an id.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from app.core.platform_authz import ReadPrincipal
from app.models.enums import IndustryCode, TenantStatus
from app.models.tenant import Tenant
from app.schemas.admin import Page, SlugAvailabilityOut, TenantListItemOut
from app.services.admin import directory
from app.services.admin.data_access import platform_read

router = APIRouter(prefix="/tenants", tags=["platform-admin"])

SLUG_PATTERN = r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$"
SubscriptionFilter = Literal[
    "none", "active", "trialing", "expired", "pending_payment",
    "pending_contract", "past_due", "paused", "cancelled",
]
SortKey = Literal["created_desc", "name", "last_activity", "users", "skus"]


@router.get("", response_model=Page[TenantListItemOut])
async def list_tenants(
    request: Request,
    principal: ReadPrincipal,
    q: Annotated[str | None, Query(max_length=100)] = None,
    industry: IndustryCode | None = None,
    status: TenantStatus | None = None,
    subscription: SubscriptionFilter | None = None,
    onboarding: Literal["in_progress", "complete", "skipped"] | None = None,
    activity: Literal["7d", "30d", "dormant", "never"] | None = None,
    health: Literal["green", "yellow", "red"] | None = None,
    sort: SortKey = "created_desc",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Page[TenantListItemOut]:
    async with platform_read(request.app.state.db, principal) as session:
        rows = await directory.tenant_rows(session)
    filters = directory.TenantFilters(
        q=q,
        industry=industry.value if industry else None,
        status=status.value if status else None,
        subscription=subscription,
        onboarding=onboarding,
        activity=activity,
        health=health,
    )
    items, total = directory.select_page(rows, filters, sort, page, page_size)
    return Page[TenantListItemOut](
        items=[TenantListItemOut.model_validate(r) for r in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/slug-available", response_model=SlugAvailabilityOut)
async def slug_available(
    request: Request,
    principal: ReadPrincipal,
    slug: Annotated[str, Query(min_length=2, max_length=63, pattern=SLUG_PATTERN)],
) -> SlugAvailabilityOut:
    if slug in directory.reserved_slugs():
        return SlugAvailabilityOut(slug=slug, available=False, reason="reserved")
    async with platform_read(request.app.state.db, principal) as session:
        taken = await session.scalar(select(Tenant.id).where(Tenant.slug == slug))
    return SlugAvailabilityOut(
        slug=slug, available=taken is None, reason="taken" if taken is not None else None
    )
```

In `backend/app/routers/admin/__init__.py`, change the import to `from app.routers.admin import session, tenants` and `ROUTER_MODULES: list[ModuleType] = [session, tenants]`.

- [ ] **Step 7: Run the tests**

Run: `uv run pytest tests/test_admin_tenants_read.py tests/test_admin_route_guard.py tests/test_entitlement.py -v`
Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/core/entitlement.py backend/app/services/admin/directory.py \
  backend/app/schemas/admin.py backend/app/routers/admin/tenants.py \
  backend/app/routers/admin/__init__.py backend/tests/admin_factories.py \
  backend/tests/test_admin_tenants_read.py
git commit -m "feat(admin): tenant directory with derived subscription, health and activity"
```

---

### Task 2.2: Tenant overview (audited view) and the extracted industry lock rule

**Files:**
- Create: `backend/app/services/industry_correction.py` (first half: `DATA_TABLES`, `lock_reason`)
- Modify: `backend/app/routers/industry_router.py` (use `lock_reason`; delete `_DATA_TABLES`, `_lock_reason`)
- Create: `backend/app/services/admin/tenants.py` (`tenant_overview`, `summarize_subscription`)
- Modify: `backend/app/schemas/admin.py` (profile, subscription summary, overview models)
- Modify: `backend/app/routers/admin/tenants.py` (GET `/{tenant_id}`)
- Test: `backend/tests/test_admin_tenant_overview.py`

**Interfaces:**
- Produces:
  - `app.services.industry_correction.DATA_TABLES: tuple[str, ...]`, `async lock_reason(session, tenant: Tenant) -> str | None`
  - `app.services.admin.tenants.summarize_subscription(sub: Subscription | None, plan: Plan | None, *, now: datetime) -> SubscriptionSummaryOut | None`
  - `async app.services.admin.tenants.tenant_overview(db, principal, tenant_id) -> TenantOverviewOut`
  - Schemas: `TenantProfileOut`, `SubscriptionSummaryOut`, `TenantUsageSummaryOut`, `JobSummaryOut`, `IntegrationSummaryOut`, `TenantOverviewOut` (fields in Step 4).

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_admin_tenant_overview.py`:

```python
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from admin_factories import create_customer, create_customer_tenant, create_platform_admin

pytestmark = pytest.mark.asyncio


async def test_overview(client: AsyncClient, db_session: AsyncSession) -> None:
    ops = await create_platform_admin(db_session, "platform_support")
    tid = await create_customer_tenant(db_session, industry="pharma")
    await create_customer(db_session, tid, role="owner", industry="pharma")
    await db_session.execute(
        text(
            "UPDATE tenants SET settings = jsonb_build_object('profile', "
            "jsonb_build_object('legal_name', 'Overview Pharma Pvt Ltd', 'timezone', 'Asia/Kolkata')) "
            "WHERE id = :t"
        ),
        {"t": str(tid)},
    )
    await db_session.execute(
        text(
            "INSERT INTO hybrid_forecast_runs (tenant_id, industry, horizon_weeks, status, error) "
            "VALUES (:t, 'pharma', 52, 'failed', 'ML service unavailable')"
        ),
        {"t": str(tid)},
    )
    await db_session.commit()

    r = await client.get(f"/api/v1/admin/tenants/{tid}", headers=ops.headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == str(tid)
    assert body["industry"] == "pharma"
    assert body["industry_display_name"]
    assert body["profile"]["legal_name"] == "Overview Pharma Pvt Ltd"
    assert body["profile"]["timezone"] == "Asia/Kolkata"
    assert body["subscription"]["plan_id"] == "growth_monthly"
    assert body["subscription"]["entitled"] is True
    assert body["usage"]["active_users"] == 1
    assert body["recent_jobs"][0]["status"] == "failed"
    assert body["recent_jobs"][0]["error"] == "ML service unavailable"
    # The factory writes no `onboarding` key, which load_onboarding_state
    # treats as complete — so this workspace's industry is locked.
    assert body["industry_locked"] is True
    assert body["industry_lock_reason"] == "setup is already complete"


async def test_overview_is_audited(client: AsyncClient, db_session: AsyncSession) -> None:
    ops = await create_platform_admin(db_session)
    tid = await create_customer_tenant(db_session)
    await client.get(f"/api/v1/admin/tenants/{tid}", headers=ops.headers)
    count = await db_session.scalar(
        text(
            "SELECT count(*) FROM platform_audit_events "
            "WHERE action = 'platform.tenant.view' AND tenant_id = :t AND actor_user_id = :u"
        ),
        {"t": str(tid), "u": str(ops.user_id)},
    )
    assert count == 1


async def test_operator_tenant_is_not_viewable(client: AsyncClient, db_session: AsyncSession) -> None:
    ops = await create_platform_admin(db_session)
    r = await client.get(f"/api/v1/admin/tenants/{ops.tenant_id}", headers=ops.headers)
    assert r.status_code == 404


async def test_unknown_tenant_is_404(client: AsyncClient, db_session: AsyncSession) -> None:
    ops = await create_platform_admin(db_session)
    r = await client.get(f"/api/v1/admin/tenants/{uuid.uuid4()}", headers=ops.headers)
    assert r.status_code == 404
```

- [ ] **Step 2: Run to see failures**

Run: `uv run pytest tests/test_admin_tenant_overview.py -v`
Expected: FAIL — 404/405 for `GET /api/v1/admin/tenants/{id}` (route missing).

- [ ] **Step 3: Extract the lock rule**

Create `backend/app/services/industry_correction.py`:

```python
"""When a workspace's industry may still be corrected — shared by the customer
setup wizard (routers/industry_router.py) and the platform console.

A workspace is scoped to one industry. It may be corrected only until setup
completes or real data arrives; after that a change would silently reinterpret
data ingested under the old industry, so it is refused (409) everywhere.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from app.models.tenant import Tenant
from app.schemas.onboarding import load_onboarding_state

# Tables whose emptiness defines "this workspace holds no real data yet".
DATA_TABLES: tuple[str, ...] = (
    "products",
    "skus",
    "historical_sales",
    "integration_connections",
)


async def lock_reason(session: Any, tenant: Tenant) -> str | None:
    """Why this workspace's industry can no longer change, or None if it can.

    Read from the database, never from a token claim.
    """
    if load_onboarding_state(tenant.settings).status == "complete":
        return "setup is already complete"
    for table in DATA_TABLES:
        exists = await session.scalar(
            text(f"SELECT 1 FROM {table} WHERE tenant_id = :tid LIMIT 1"),  # noqa: S608
            {"tid": str(tenant.id)},
        )
        if exists:
            return "this workspace already holds data"
    return None
```

In `backend/app/routers/industry_router.py`: delete `_DATA_TABLES` and `_lock_reason` (with their comments), add `from app.services.industry_correction import lock_reason`, and change `locked = await _lock_reason(session, tenant)` to `locked = await lock_reason(session, tenant)`. Remove `text` from the `sqlalchemy` import if nothing else there uses it.

- [ ] **Step 4: Add the schemas**

Append to `backend/app/schemas/admin.py`:

```python
class TenantProfileOut(BaseModel):
    legal_name: str | None = None
    company_identifier: str | None = None
    primary_contact_name: str | None = None
    primary_contact_email: str | None = None
    timezone: str | None = None


class SubscriptionSummaryOut(BaseModel):
    id: uuid.UUID
    plan_id: str
    plan_name: str | None
    plan_price_cents: int | None
    billing_interval: str | None
    status: str
    state: str
    entitled: bool
    current_period_start: datetime
    current_period_end: datetime
    cancel_at_period_end: bool
    cancelled_at: datetime | None
    razorpay_subscription_id: str | None
    contract: dict | None


class TenantUsageSummaryOut(BaseModel):
    active_users: int
    pending_invites: int
    max_users: int
    active_skus: int
    max_skus: int


class JobSummaryOut(BaseModel):
    id: uuid.UUID
    status: str
    horizon_weeks: int
    trigger_source: str
    created_at: datetime
    completed_at: datetime | None
    error: str | None


class IntegrationSummaryOut(BaseModel):
    provider: str
    status: str
    last_sync_at: datetime | None
    has_error: bool


class TenantOverviewOut(BaseModel):
    id: uuid.UUID
    slug: str
    display_name: str
    industry: str
    industry_display_name: str
    status: str
    is_sandbox: bool
    created_at: datetime
    updated_at: datetime
    home_region: str
    max_skus: int
    max_users: int
    data_retention_days: int
    trial_ends_at: datetime | None
    contract_ends_at: datetime | None
    profile: TenantProfileOut
    onboarding_status: str
    onboarding_completed_at: datetime | None
    industry_locked: bool
    industry_lock_reason: str | None
    subscription: SubscriptionSummaryOut | None
    usage: TenantUsageSummaryOut
    last_activity_at: datetime | None
    recent_jobs: list[JobSummaryOut]
    integrations: list[IntegrationSummaryOut]
```

- [ ] **Step 5: Implement the overview service**

Create `backend/app/services/admin/tenants.py`:

```python
"""Per-tenant platform views and actions. Everything here runs in
``tenant_scope`` (RLS-scoped to the tenant in the URL) unless noted."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select

from app.config import get_settings
from app.core.entitlement import evaluate_entitlement
from app.core.platform_authz import PlatformPrincipal
from app.models.billing import Plan, Subscription
from app.models.integration import IntegrationConnection
from app.models.invite import Invite, InviteStatus
from app.models.product import Sku
from app.models.tenant import User
from app.models.trend import HybridForecastRun
from app.schemas.admin import (
    IntegrationSummaryOut,
    JobSummaryOut,
    SubscriptionSummaryOut,
    TenantOverviewOut,
    TenantProfileOut,
    TenantUsageSummaryOut,
)
from app.schemas.onboarding import load_onboarding_state
from app.services.admin.audit import record_read_event
from app.services.admin.data_access import tenant_scope
from app.services.admin.directory import subscription_state
from app.services.industry_context import get_industry_context
from app.services.industry_correction import lock_reason


def summarize_subscription(
    sub: Subscription | None, plan: Plan | None, *, now: datetime
) -> SubscriptionSummaryOut | None:
    if sub is None:
        return None
    meta = sub.subscription_metadata or {}
    return SubscriptionSummaryOut(
        id=sub.id,
        plan_id=sub.plan_id,
        plan_name=plan.display_name if plan else None,
        plan_price_cents=plan.base_price_cents if plan else None,
        billing_interval=plan.billing_interval if plan else None,
        status=sub.status.value,
        state=subscription_state(
            sub.status,
            sub.current_period_end,
            plan_price_cents=plan.base_price_cents if plan else None,
            plan_razorpay_id=plan.razorpay_plan_id if plan else None,
            now=now,
        ),
        entitled=evaluate_entitlement(sub.status, sub.current_period_end, now=now),
        current_period_start=sub.current_period_start,
        current_period_end=sub.current_period_end,
        cancel_at_period_end=sub.cancel_at_period_end,
        cancelled_at=sub.cancelled_at,
        razorpay_subscription_id=sub.razorpay_subscription_id,
        contract=meta.get("contract"),
    )


async def _count(session: Any, stmt: Any) -> int:
    return int(await session.scalar(stmt) or 0)


async def tenant_overview(
    db: Any, principal: PlatformPrincipal, tenant_id: uuid.UUID
) -> TenantOverviewOut:
    now = datetime.now(tz=UTC)
    async with tenant_scope(db, principal, tenant_id) as (session, tenant):
        locked = await lock_reason(session, tenant)
        sub = await session.scalar(
            select(Subscription)
            .where(Subscription.tenant_id == tenant_id)
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
        plan = await session.get(Plan, sub.plan_id) if sub is not None else None
        active_users = await _count(
            session,
            select(func.count()).select_from(User).where(
                User.tenant_id == tenant_id, User.is_active.is_(True)
            ),
        )
        last_login = await session.scalar(
            select(func.max(User.last_login_at)).where(User.tenant_id == tenant_id)
        )
        pending = await _count(
            session,
            select(func.count()).select_from(Invite).where(
                Invite.tenant_id == tenant_id, Invite.status == InviteStatus.pending
            ),
        )
        skus = await _count(
            session,
            select(func.count()).select_from(Sku).where(
                Sku.tenant_id == tenant_id, Sku.is_active.is_(True)
            ),
        )
        runs = (
            await session.scalars(
                select(HybridForecastRun)
                .where(HybridForecastRun.tenant_id == tenant_id)
                .order_by(HybridForecastRun.created_at.desc())
                .limit(5)
            )
        ).all()
        conns = (
            await session.scalars(
                select(IntegrationConnection)
                .where(IntegrationConnection.tenant_id == tenant_id)
                .order_by(IntegrationConnection.provider)
            )
        ).all()
        onboarding = load_onboarding_state(tenant.settings)
        overview = TenantOverviewOut(
            id=tenant.id,
            slug=str(tenant.slug),
            display_name=tenant.display_name,
            industry=tenant.industry.value,
            industry_display_name=get_industry_context(tenant.industry.value).display_name,
            status=tenant.status.value,
            is_sandbox=str(tenant.slug) == get_settings().sandbox_tenant_slug,
            created_at=tenant.created_at,
            updated_at=tenant.updated_at,
            home_region=str(tenant.home_region),
            max_skus=tenant.max_skus,
            max_users=tenant.max_users,
            data_retention_days=tenant.data_retention_days,
            trial_ends_at=tenant.trial_ends_at,
            contract_ends_at=tenant.contract_ends_at,
            profile=TenantProfileOut.model_validate((tenant.settings or {}).get("profile") or {}),
            onboarding_status=onboarding.status,
            onboarding_completed_at=onboarding.completed_at,
            industry_locked=locked is not None,
            industry_lock_reason=locked,
            subscription=summarize_subscription(sub, plan, now=now),
            usage=TenantUsageSummaryOut(
                active_users=active_users,
                pending_invites=pending,
                max_users=tenant.max_users,
                active_skus=skus,
                max_skus=tenant.max_skus,
            ),
            last_activity_at=last_login,
            recent_jobs=[
                JobSummaryOut(
                    id=run.id,
                    status=run.status,
                    horizon_weeks=run.horizon_weeks,
                    trigger_source=run.trigger_source,
                    created_at=run.created_at,
                    completed_at=run.completed_at,
                    error=(run.error or None) and run.error[:500],
                )
                for run in runs
            ],
            integrations=[
                IntegrationSummaryOut(
                    provider=c.provider,
                    status=c.status,
                    last_sync_at=c.last_sync_at,
                    has_error=c.status == "error" or bool(c.error_message),
                )
                for c in conns
            ],
        )
    await record_read_event(
        db,
        principal,
        action="platform.tenant.view",
        target_type="tenant",
        target_id=str(tenant_id),
        tenant_id=tenant_id,
    )
    return overview
```

- [ ] **Step 6: Add the route**

Append to `backend/app/routers/admin/tenants.py` (after `slug_available`; add `import uuid`, `TenantOverviewOut` to the schema import and `from app.services.admin import tenants as tenant_service`):

```python
@router.get("/{tenant_id}", response_model=TenantOverviewOut)
async def tenant_overview(
    tenant_id: uuid.UUID, request: Request, principal: ReadPrincipal
) -> TenantOverviewOut:
    return await tenant_service.tenant_overview(request.app.state.db, principal, tenant_id)
```

- [ ] **Step 7: Run the tests (including the industry suite, to prove the extraction changed nothing)**

Run: `uv run pytest tests/test_admin_tenant_overview.py tests/test_industry_scope.py tests/test_industry_migration.py -v`
Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/industry_correction.py backend/app/routers/industry_router.py \
  backend/app/services/admin/tenants.py backend/app/schemas/admin.py \
  backend/app/routers/admin/tenants.py backend/tests/test_admin_tenant_overview.py
git commit -m "feat(admin): audited tenant overview; share the industry lock rule"
```

---

### Task 2.3: Users — directory, tenant members, account activity

**Files:**
- Create: `backend/app/services/admin/users.py` (read functions)
- Modify: `backend/app/schemas/admin.py`
- Create: `backend/app/routers/admin/users.py`
- Modify: `backend/app/routers/admin/__init__.py` (append `users`)
- Test: `backend/tests/test_admin_users_read.py`

**Interfaces:**
- Produces:
  - `async users.directory(db, principal, *, q, tenant_id, role, status, page, page_size) -> Page[DirectoryUserOut]`
  - `async users.tenant_members(db, principal, tenant_id) -> TenantUsersOut`
  - `async users.user_activity(db, principal, tenant_id, user_id) -> list[ActivityEventOut]`
  - Schemas `DirectoryUserOut`, `MemberOut`, `PendingInviteOut`, `TenantUsersOut`, `ActivityEventOut`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_admin_users_read.py`:

```python
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from admin_factories import create_customer, create_customer_tenant, create_platform_admin

pytestmark = pytest.mark.asyncio

_SECRETS = ("password_hash", "mfa_secret", "firebase_uid", "token_hash")


async def test_directory_searches_across_tenants(client: AsyncClient, db_session: AsyncSession) -> None:
    ops = await create_platform_admin(db_session, "platform_support")
    a = await create_customer_tenant(db_session)
    b = await create_customer_tenant(db_session)
    ua = await create_customer(db_session, a)
    ub = await create_customer(db_session, b, role="viewer")

    r = await client.get("/api/v1/admin/users", params={"q": ua.email}, headers=ops.headers)
    assert r.status_code == 200, r.text
    assert [i["email"] for i in r.json()["items"]] == [ua.email]

    r = await client.get("/api/v1/admin/users", params={"tenant_id": str(b)}, headers=ops.headers)
    body = r.json()
    assert {i["email"] for i in body["items"]} == {ub.email}
    assert body["items"][0]["tenant_id"] == str(b)
    assert not any(k in body["items"][0] for k in _SECRETS)


async def test_directory_never_lists_operators(client: AsyncClient, db_session: AsyncSession) -> None:
    ops = await create_platform_admin(db_session)
    r = await client.get("/api/v1/admin/users", params={"q": ops.email}, headers=ops.headers)
    assert r.json()["total"] == 0


async def test_tenant_members_and_invites(client: AsyncClient, db_session: AsyncSession) -> None:
    ops = await create_platform_admin(db_session)
    tid = await create_customer_tenant(db_session)
    owner = await create_customer(db_session, tid)
    await db_session.execute(
        text(
            "INSERT INTO invites (tenant_id, email, role, status, token_hash, expires_at, invitee_name) "
            "VALUES (:t, :e, 'viewer', 'pending', :h, now() + interval '7 days', 'Pending Person')"
        ),
        {"t": str(tid), "e": f"inv-{uuid.uuid4().hex[:6]}@example.test", "h": uuid.uuid4().hex},
    )
    await db_session.commit()

    r = await client.get(f"/api/v1/admin/tenants/{tid}/users", headers=ops.headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert [m["email"] for m in body["members"]] == [owner.email]
    assert body["invites"][0]["invitee_name"] == "Pending Person"
    assert body["seats_used"] == 2
    assert "token_hash" not in body["invites"][0]
    assert not any(k in body["members"][0] for k in _SECRETS)


async def test_activity_shows_sign_in_events_only(client: AsyncClient, db_session: AsyncSession) -> None:
    ops = await create_platform_admin(db_session)
    tid = await create_customer_tenant(db_session)
    user = await create_customer(db_session, tid)
    for action in ("user.login", "product.update"):
        await db_session.execute(
            text(
                "INSERT INTO audit_log (tenant_id, user_id, action, entity_type) "
                "VALUES (:t, :u, :a, 'x')"
            ),
            {"t": str(tid), "u": str(user.user_id), "a": action},
        )
    await db_session.commit()
    r = await client.get(
        f"/api/v1/admin/tenants/{tid}/users/{user.user_id}/activity", headers=ops.headers
    )
    assert r.status_code == 200, r.text
    assert [e["action"] for e in r.json()] == ["user.login"]


async def test_activity_for_another_tenants_user_is_404(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    ops = await create_platform_admin(db_session)
    a = await create_customer_tenant(db_session)
    b = await create_customer_tenant(db_session)
    stranger = await create_customer(db_session, b)
    r = await client.get(
        f"/api/v1/admin/tenants/{a}/users/{stranger.user_id}/activity", headers=ops.headers
    )
    assert r.status_code == 404
```

- [ ] **Step 2: Run to see failures**

Run: `uv run pytest tests/test_admin_users_read.py -v`
Expected: FAIL — 404 on `/api/v1/admin/users`.

- [ ] **Step 3: Add the schemas**

Append to `backend/app/schemas/admin.py`:

```python
class DirectoryUserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime
    tenant_id: uuid.UUID
    tenant_slug: str
    tenant_name: str


class MemberOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime
    has_sso_identity: bool


class PendingInviteOut(BaseModel):
    id: uuid.UUID
    email: str
    invitee_name: str | None
    role: str
    status: str
    expires_at: datetime
    created_at: datetime


class TenantUsersOut(BaseModel):
    members: list[MemberOut]
    invites: list[PendingInviteOut]
    seats_used: int
    seats_total: int


class ActivityEventOut(BaseModel):
    occurred_at: datetime
    action: str
    ip_address: str | None
    user_agent: str | None
```

- [ ] **Step 4: Implement the read service**

Create `backend/app/services/admin/users.py`:

```python
"""Customer users as seen by the platform console. Customer roles
(owner/admin/analyst/viewer) are preserved exactly; platform roles never appear
here."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, or_, select

from app.core.exceptions import NotFoundError
from app.core.platform_authz import PlatformPrincipal
from app.models.audit import AuditLog
from app.models.invite import Invite, InviteStatus
from app.models.tenant import Tenant, User
from app.schemas.admin import (
    ActivityEventOut,
    DirectoryUserOut,
    MemberOut,
    Page,
    PendingInviteOut,
    TenantUsersOut,
)
from app.services.admin.data_access import platform_read, tenant_scope
from app.services.admin.directory import escape_like


def _member(u: User) -> MemberOut:
    return MemberOut(
        id=u.id,
        email=str(u.email),
        full_name=u.full_name,
        role=u.role.value,
        is_active=u.is_active,
        last_login_at=u.last_login_at,
        created_at=u.created_at,
        has_sso_identity=u.firebase_uid is not None,
    )


async def directory(
    db: Any,
    principal: PlatformPrincipal,
    *,
    q: str | None,
    tenant_id: uuid.UUID | None,
    role: str | None,
    status: str | None,
    page: int,
    page_size: int,
) -> Page[DirectoryUserOut]:
    stmt = (
        select(
            User.id,
            User.email,
            User.full_name,
            User.role,
            User.is_active,
            User.last_login_at,
            User.created_at,
            Tenant.id.label("tenant_id"),
            Tenant.slug.label("tenant_slug"),
            Tenant.display_name.label("tenant_name"),
        )
        .join(Tenant, Tenant.id == User.tenant_id)
        .where(Tenant.is_operator.is_(False))
    )
    if q:
        like = f"%{escape_like(q.strip())}%"
        stmt = stmt.where(
            or_(User.email.ilike(like, escape="\\"), User.full_name.ilike(like, escape="\\"))
        )
    if tenant_id is not None:
        stmt = stmt.where(User.tenant_id == tenant_id)
    if role is not None:
        stmt = stmt.where(User.role == role)
    if status == "active":
        stmt = stmt.where(User.is_active.is_(True))
    elif status == "disabled":
        stmt = stmt.where(User.is_active.is_(False))

    async with platform_read(db, principal) as session:
        total = int(await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = (
            await session.execute(
                stmt.order_by(User.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    return Page[DirectoryUserOut](
        items=[
            DirectoryUserOut(
                id=r.id,
                email=str(r.email),
                full_name=r.full_name,
                role=getattr(r.role, "value", str(r.role)),
                is_active=r.is_active,
                last_login_at=r.last_login_at,
                created_at=r.created_at,
                tenant_id=r.tenant_id,
                tenant_slug=str(r.tenant_slug),
                tenant_name=r.tenant_name,
            )
            for r in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


async def tenant_members(
    db: Any, principal: PlatformPrincipal, tenant_id: uuid.UUID
) -> TenantUsersOut:
    async with tenant_scope(db, principal, tenant_id) as (session, tenant):
        members = (
            await session.scalars(
                select(User).where(User.tenant_id == tenant_id).order_by(User.created_at)
            )
        ).all()
        invites = (
            await session.scalars(
                select(Invite)
                .where(Invite.tenant_id == tenant_id, Invite.status == InviteStatus.pending)
                .order_by(Invite.created_at.desc())
            )
        ).all()
        active = sum(1 for m in members if m.is_active)
        return TenantUsersOut(
            members=[_member(m) for m in members],
            invites=[
                PendingInviteOut(
                    id=i.id,
                    email=str(i.email),
                    invitee_name=i.invitee_name,
                    role=i.role.value,
                    status=i.status.value,
                    expires_at=i.expires_at,
                    created_at=i.created_at,
                )
                for i in invites
            ],
            seats_used=active + len(invites),
            seats_total=tenant.max_users,
        )


async def user_activity(
    db: Any, principal: PlatformPrincipal, tenant_id: uuid.UUID, user_id: uuid.UUID
) -> list[ActivityEventOut]:
    """Sign-in lifecycle events only (`user.*`). The full audit log is
    customer data and sits behind a support session."""
    async with tenant_scope(db, principal, tenant_id) as (session, _tenant):
        user = await session.get(User, user_id)
        if user is None or user.tenant_id != tenant_id:
            raise NotFoundError("User")
        rows = (
            await session.scalars(
                select(AuditLog)
                .where(
                    AuditLog.tenant_id == tenant_id,
                    AuditLog.user_id == user_id,
                    AuditLog.action.like("user.%"),
                )
                .order_by(AuditLog.occurred_at.desc())
                .limit(100)
            )
        ).all()
        return [
            ActivityEventOut(
                occurred_at=r.occurred_at,
                action=r.action,
                ip_address=str(r.ip_address) if r.ip_address else None,
                user_agent=r.user_agent,
            )
            for r in rows
        ]
```

- [ ] **Step 5: Add the router**

Create `backend/app/routers/admin/users.py`:

```python
from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request

from app.core.platform_authz import ReadPrincipal
from app.models.enums import UserRole
from app.schemas.admin import ActivityEventOut, DirectoryUserOut, Page, TenantUsersOut
from app.services.admin import users as user_service

router = APIRouter(tags=["platform-admin"])


@router.get("/users", response_model=Page[DirectoryUserOut])
async def users_directory(
    request: Request,
    principal: ReadPrincipal,
    q: Annotated[str | None, Query(max_length=200)] = None,
    tenant_id: uuid.UUID | None = None,
    role: UserRole | None = None,
    status: Literal["active", "disabled"] | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Page[DirectoryUserOut]:
    return await user_service.directory(
        request.app.state.db,
        principal,
        q=q,
        tenant_id=tenant_id,
        role=role.value if role else None,
        status=status,
        page=page,
        page_size=page_size,
    )


@router.get("/tenants/{tenant_id}/users", response_model=TenantUsersOut)
async def tenant_users(
    tenant_id: uuid.UUID, request: Request, principal: ReadPrincipal
) -> TenantUsersOut:
    return await user_service.tenant_members(request.app.state.db, principal, tenant_id)


@router.get(
    "/tenants/{tenant_id}/users/{user_id}/activity", response_model=list[ActivityEventOut]
)
async def user_activity(
    tenant_id: uuid.UUID, user_id: uuid.UUID, request: Request, principal: ReadPrincipal
) -> list[ActivityEventOut]:
    return await user_service.user_activity(request.app.state.db, principal, tenant_id, user_id)
```

Append `users` to `ROUTER_MODULES` (and the import) in `routers/admin/__init__.py`.

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/test_admin_users_read.py tests/test_admin_route_guard.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/admin/users.py backend/app/schemas/admin.py \
  backend/app/routers/admin/users.py backend/app/routers/admin/__init__.py \
  backend/tests/test_admin_users_read.py
git commit -m "feat(admin): users directory, tenant members and sign-in activity"
```

---

### Task 2.4: Integrations and signals (read-only health views)

**Files:**
- Create: `backend/app/services/admin/integrations.py`
- Create: `backend/app/services/admin/signals.py`
- Modify: `backend/app/schemas/admin.py`
- Create: `backend/app/routers/admin/integrations.py`, `backend/app/routers/admin/signals.py`
- Modify: `backend/app/routers/admin/__init__.py` (append both)
- Test: `backend/tests/test_admin_integrations_signals.py`

**Interfaces:**
- Produces: `integrations.sync_schedule(provider, status, last_sync_at, settings) -> tuple[str, datetime | None]`; `async integrations.list_connections(db, principal, *, status, provider, page, page_size) -> Page[IntegrationOut]`; `async integrations.tenant_connections(db, principal, tenant_id) -> list[IntegrationOut]`; `async signals.tenant_signals(db, principal, tenant_id) -> SignalsOut`; schemas `IntegrationOut`, `SignalSourceCountOut`, `SignalsOut`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_admin_integrations_signals.py`:

```python
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from admin_factories import create_customer_tenant, create_platform_admin
from app.config import get_settings
from app.services.admin.integrations import sync_schedule

pytestmark = pytest.mark.asyncio


async def test_sync_schedule() -> None:
    settings = get_settings()
    last = datetime(2026, 9, 10, 10, tzinfo=UTC)
    mode, nxt = sync_schedule("shopify", "connected", last, settings)
    assert mode == ("poll" if settings.shopify_poll_enabled else "manual")
    if settings.shopify_poll_enabled:
        assert nxt == last + timedelta(seconds=settings.shopify_poll_interval_s)
    assert sync_schedule("csv_upload", "connected", last, settings) == ("upload", None)
    assert sync_schedule("rest_api", "connected", last, settings) == ("push", None)
    assert sync_schedule("postgres", "error", last, settings) == ("manual", None)


async def test_connections_never_expose_credentials(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    ops = await create_platform_admin(db_session, "platform_support")
    tid = await create_customer_tenant(db_session)
    await db_session.execute(
        text(
            "INSERT INTO integration_connections (tenant_id, provider, status, target_industry, "
            "error_message, access_token_encrypted, last_sync_stats, state) VALUES "
            "(:t, 'shopify', 'error', 'fashion', 'Invalid API key', 'ENCRYPTED-SECRET', "
            "'{\"orders\": 12}'::jsonb, '{\"credentials_enc\": {\"key\": \"ENCRYPTED-SECRET\"}}'::jsonb)"
        ),
        {"t": str(tid)},
    )
    await db_session.commit()

    r = await client.get("/api/v1/admin/integrations", params={"status": "error"}, headers=ops.headers)
    assert r.status_code == 200, r.text
    assert "ENCRYPTED-SECRET" not in r.text
    ours = [i for i in r.json()["items"] if i["tenant_id"] == str(tid)]
    assert ours[0]["error_message"] == "Invalid API key"
    assert ours[0]["last_sync_stats"] == {"orders": 12}

    r = await client.get(f"/api/v1/admin/tenants/{tid}/integrations", headers=ops.headers)
    assert r.status_code == 200
    assert "ENCRYPTED-SECRET" not in r.text
    assert "state" not in r.json()[0]


async def test_tenant_signals(client: AsyncClient, db_session: AsyncSession) -> None:
    ops = await create_platform_admin(db_session)
    tid = await create_customer_tenant(db_session, industry="fashion")
    # captured_at inside an existing monthly partition; ingested_at defaults to now().
    await db_session.execute(
        text(
            "INSERT INTO trend_signals (tenant_id, industry, source, kind, series_key, "
            "normalized_score, captured_at) VALUES "
            "(:t, 'fashion', 'rss', 'news_sentiment', :k, 0.2, '2026-08-15')"
        ),
        {"t": str(tid), "k": f"test:{uuid.uuid4().hex[:6]}"},
    )
    await db_session.commit()
    r = await client.get(f"/api/v1/admin/tenants/{tid}/signals", headers=ops.headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["industry"] == "fashion"
    assert body["required_signal_types"]
    assert body["effective_horizon_weeks"] >= 1
    tenant_rss = [s for s in body["sources"] if s["source"] == "rss" and s["scope"] == "tenant"]
    assert tenant_rss and tenant_rss[0]["last_30d"] >= 1
```

- [ ] **Step 2: Run to see failures**

Run: `uv run pytest tests/test_admin_integrations_signals.py -v`
Expected: FAIL — `No module named 'app.services.admin.integrations'`.

- [ ] **Step 3: Add the schemas**

Append to `backend/app/schemas/admin.py`:

```python
class IntegrationOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    tenant_slug: str
    tenant_name: str
    provider: str
    status: str
    target_industry: str
    last_sync_at: datetime | None
    last_sync_status: str | None
    last_sync_stats: dict[str, int]
    error_message: str | None
    sync_mode: str
    next_sync_estimate: datetime | None
    updated_at: datetime


class SignalSourceCountOut(BaseModel):
    source: str
    scope: str  # tenant | global
    last_7d: int
    last_30d: int
    latest_ingested_at: datetime | None


class SignalsOut(BaseModel):
    industry: str
    required_signal_types: list[str]
    custom_signal_types: list[str]
    active_signal_types: list[str]
    effective_horizon_weeks: int
    focus_keywords: list[str]
    focus_categories: list[str]
    sources: list[SignalSourceCountOut]
```

- [ ] **Step 4: Implement the services**

Create `backend/app/services/admin/integrations.py`:

```python
"""Integration health across tenants. Reads name every column explicitly:
`state` (encrypted credentials, cursors) and `access_token_encrypted` are
never selected, so they cannot leak even through a serialisation mistake."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select

from app.config import Settings, get_settings
from app.core.platform_authz import PlatformPrincipal
from app.models.integration import IntegrationConnection
from app.models.tenant import Tenant
from app.schemas.admin import IntegrationOut, Page
from app.services.admin.data_access import platform_read, tenant_scope

_UPLOADS = frozenset({"csv_upload", "excel_upload"})
_PUSH = frozenset({"rest_api", "webhooks"})

_COLUMNS = (
    IntegrationConnection.id,
    IntegrationConnection.tenant_id,
    IntegrationConnection.provider,
    IntegrationConnection.status,
    IntegrationConnection.target_industry,
    IntegrationConnection.last_sync_at,
    IntegrationConnection.last_sync_status,
    IntegrationConnection.last_sync_stats,
    IntegrationConnection.error_message,
    IntegrationConnection.updated_at,
    Tenant.slug.label("tenant_slug"),
    Tenant.display_name.label("tenant_name"),
)


def sync_schedule(
    provider: str, status: str, last_sync_at: datetime | None, settings: Settings
) -> tuple[str, datetime | None]:
    if provider == "shopify":
        if not settings.shopify_poll_enabled:
            return "manual", None
        if status in ("connected", "syncing") and last_sync_at is not None:
            return "poll", last_sync_at + timedelta(seconds=settings.shopify_poll_interval_s)
        return "poll", None
    if provider in _UPLOADS:
        return "upload", None
    if provider in _PUSH:
        return "push", None
    return "manual", None


def _out(r: Any, settings: Settings) -> IntegrationOut:
    mode, nxt = sync_schedule(r.provider, r.status, r.last_sync_at, settings)
    stats = {k: int(v) for k, v in (r.last_sync_stats or {}).items() if isinstance(v, int | float)}
    return IntegrationOut(
        id=r.id,
        tenant_id=r.tenant_id,
        tenant_slug=str(r.tenant_slug),
        tenant_name=r.tenant_name,
        provider=r.provider,
        status=r.status,
        target_industry=getattr(r.target_industry, "value", str(r.target_industry)),
        last_sync_at=r.last_sync_at,
        last_sync_status=r.last_sync_status,
        last_sync_stats=stats,
        error_message=(r.error_message or None) and r.error_message[:300],
        sync_mode=mode,
        next_sync_estimate=nxt,
        updated_at=r.updated_at,
    )


async def list_connections(
    db: Any,
    principal: PlatformPrincipal,
    *,
    status: str | None,
    provider: str | None,
    page: int,
    page_size: int,
) -> Page[IntegrationOut]:
    stmt = (
        select(*_COLUMNS)
        .join(Tenant, Tenant.id == IntegrationConnection.tenant_id)
        .where(Tenant.is_operator.is_(False))
    )
    if status:
        stmt = stmt.where(IntegrationConnection.status == status)
    if provider:
        stmt = stmt.where(IntegrationConnection.provider == provider)
    settings = get_settings()
    async with platform_read(db, principal) as session:
        total = int(await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = (
            await session.execute(
                stmt.order_by(IntegrationConnection.updated_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    return Page[IntegrationOut](
        items=[_out(r, settings) for r in rows], total=total, page=page, page_size=page_size
    )


async def tenant_connections(
    db: Any, principal: PlatformPrincipal, tenant_id: uuid.UUID
) -> list[IntegrationOut]:
    settings = get_settings()
    async with tenant_scope(db, principal, tenant_id) as (session, _tenant):
        rows = (
            await session.execute(
                select(*_COLUMNS)
                .join(Tenant, Tenant.id == IntegrationConnection.tenant_id)
                .where(IntegrationConnection.tenant_id == tenant_id)
                .order_by(IntegrationConnection.provider)
            )
        ).all()
    return [_out(r, settings) for r in rows]
```

Create `backend/app/services/admin/signals.py`:

```python
"""Signal configuration and ingestion counts for one tenant.

`trend_signals` rows with a NULL tenant are global (visible to every tenant of
the industry); the tenant session's RLS already includes them, so both scopes
are counted in one tenant-scoped query."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import case, func, select

from app.core.platform_authz import PlatformPrincipal
from app.models.industry import IndustryProfile
from app.models.trend import TrendSignal
from app.schemas.admin import SignalsOut, SignalSourceCountOut
from app.services.admin.data_access import tenant_scope
from app.services.industry_config import resolve_effective_config
from app.services.industry_context import get_industry_context


async def tenant_signals(
    db: Any, principal: PlatformPrincipal, tenant_id: uuid.UUID
) -> SignalsOut:
    now = datetime.now(tz=UTC)
    d7, d30 = now - timedelta(days=7), now - timedelta(days=30)
    async with tenant_scope(db, principal, tenant_id) as (session, tenant):
        code = tenant.industry.value
        config = await resolve_effective_config(session, tenant_id, code)
        profile = await session.scalar(
            select(IndustryProfile).where(
                IndustryProfile.tenant_id == tenant_id, IndustryProfile.industry == tenant.industry
            )
        )
        scope = case((TrendSignal.tenant_id.is_(None), "global"), else_="tenant")
        rows = (
            await session.execute(
                select(
                    TrendSignal.source,
                    scope.label("scope"),
                    func.count().filter(TrendSignal.ingested_at >= d7).label("last_7d"),
                    func.count().label("last_30d"),
                    func.max(TrendSignal.ingested_at).label("latest"),
                )
                .where(TrendSignal.industry == tenant.industry, TrendSignal.ingested_at >= d30)
                .group_by(TrendSignal.source, scope)
                .order_by(TrendSignal.source)
            )
        ).all()
    return SignalsOut(
        industry=code,
        required_signal_types=list(get_industry_context(code).required_signal_types),
        custom_signal_types=[str(getattr(s, "value", s)) for s in (profile.custom_signal_types if profile else [])],
        active_signal_types=list(config.active_signal_types),
        effective_horizon_weeks=config.effective_horizon,
        focus_keywords=list(config.focus.keywords),
        focus_categories=list(config.focus.categories),
        sources=[
            SignalSourceCountOut(
                source=getattr(r.source, "value", str(r.source)),
                scope=r.scope,
                last_7d=r.last_7d,
                last_30d=r.last_30d,
                latest_ingested_at=r.latest,
            )
            for r in rows
        ],
    )
```

- [ ] **Step 5: Add the routers**

Create `backend/app/routers/admin/integrations.py`:

```python
from __future__ import annotations

import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request

from app.core.platform_authz import ReadPrincipal
from app.schemas.admin import IntegrationOut, Page
from app.services.admin import integrations as integration_service

router = APIRouter(tags=["platform-admin"])


@router.get("/integrations", response_model=Page[IntegrationOut])
async def list_integrations(
    request: Request,
    principal: ReadPrincipal,
    status: Literal["connected", "syncing", "error", "disconnected"] | None = None,
    provider: Annotated[str | None, Query(max_length=64)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Page[IntegrationOut]:
    return await integration_service.list_connections(
        request.app.state.db, principal, status=status, provider=provider,
        page=page, page_size=page_size,
    )


@router.get("/tenants/{tenant_id}/integrations", response_model=list[IntegrationOut])
async def tenant_integrations(
    tenant_id: uuid.UUID, request: Request, principal: ReadPrincipal
) -> list[IntegrationOut]:
    return await integration_service.tenant_connections(request.app.state.db, principal, tenant_id)
```

Create `backend/app/routers/admin/signals.py`:

```python
from __future__ import annotations

import uuid

from fastapi import APIRouter, Request

from app.core.platform_authz import ReadPrincipal
from app.schemas.admin import SignalsOut
from app.services.admin.signals import tenant_signals

router = APIRouter(tags=["platform-admin"])


@router.get("/tenants/{tenant_id}/signals", response_model=SignalsOut)
async def signals(tenant_id: uuid.UUID, request: Request, principal: ReadPrincipal) -> SignalsOut:
    return await tenant_signals(request.app.state.db, principal, tenant_id)
```

Append `integrations` and `signals` to `ROUTER_MODULES`.

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/test_admin_integrations_signals.py tests/test_admin_route_guard.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/admin/integrations.py backend/app/services/admin/signals.py \
  backend/app/schemas/admin.py backend/app/routers/admin/integrations.py \
  backend/app/routers/admin/signals.py backend/app/routers/admin/__init__.py \
  backend/tests/test_admin_integrations_signals.py
git commit -m "feat(admin): integration health and signal ingestion views"
```

---

### Task 2.5: Forecast jobs — list and detail

**Files:**
- Create: `backend/app/services/admin/jobs.py` (read functions)
- Modify: `backend/app/schemas/admin.py`
- Create: `backend/app/routers/admin/jobs.py`
- Modify: `backend/app/routers/admin/__init__.py` (append `jobs`)
- Test: `backend/tests/test_admin_jobs_read.py`

**Interfaces:**
- Produces: `JOB_TYPE = "forecast.hybrid"`; `async jobs.list_jobs(db, principal, *, tenant_id, status, job_type, date_from, date_to, page, page_size) -> Page[JobOut]`; `async jobs.job_detail(db, principal, job_id) -> JobDetailOut`; schemas `JobOut`, `JobResultSummaryOut`, `JobDetailOut`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_admin_jobs_read.py`:

```python
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from admin_factories import create_customer_tenant, create_platform_admin

pytestmark = pytest.mark.asyncio


async def _run(db: AsyncSession, tenant: uuid.UUID, status: str, *, minutes_ago: int = 0,
               error: str | None = None, result: str | None = None) -> uuid.UUID:
    rid = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO hybrid_forecast_runs (id, tenant_id, industry, horizon_weeks, status, "
            "error, result, request_params, created_at, completed_at) VALUES "
            "(:id, :t, 'fashion', 12, :s, :e, CAST(:r AS jsonb), '{\"horizon_weeks\": 12}'::jsonb, "
            "now() - make_interval(mins => :m), "
            "CASE WHEN :s IN ('completed','failed') THEN now() ELSE NULL END)"
        ),
        {"id": str(rid), "t": str(tenant), "s": status, "e": error, "r": result, "m": minutes_ago},
    )
    await db.commit()
    return rid


async def test_list_filters_and_stale_flag(client: AsyncClient, db_session: AsyncSession) -> None:
    ops = await create_platform_admin(db_session, "platform_support")
    tid = await create_customer_tenant(db_session)
    failed = await _run(db_session, tid, "failed", error="ML service unavailable")
    stale = await _run(db_session, tid, "pending", minutes_ago=30)

    r = await client.get("/api/v1/admin/jobs", params={"tenant_id": str(tid)}, headers=ops.headers)
    assert r.status_code == 200, r.text
    by_id = {i["id"]: i for i in r.json()["items"]}
    assert by_id[str(failed)]["error"] == "ML service unavailable"
    assert by_id[str(failed)]["type"] == "forecast.hybrid"
    assert by_id[str(stale)]["is_stale"] is True

    r = await client.get(
        "/api/v1/admin/jobs", params={"tenant_id": str(tid), "status": "failed"}, headers=ops.headers
    )
    assert [i["id"] for i in r.json()["items"]] == [str(failed)]

    r = await client.get(
        "/api/v1/admin/jobs", params={"tenant_id": str(tid), "status": "stale"}, headers=ops.headers
    )
    assert [i["id"] for i in r.json()["items"]] == [str(stale)]

    r = await client.get(
        "/api/v1/admin/jobs", params={"tenant_id": str(tid), "type": "integration.sync"},
        headers=ops.headers,
    )
    assert r.json()["total"] == 0


async def test_detail_summarises_without_the_payload(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    ops = await create_platform_admin(db_session)
    tid = await create_customer_tenant(db_session)
    rid = await _run(
        db_session, tid, "completed",
        result='{"data_source": "chronos_zero_shot", "series": [{"sku_id": "x"}], "alerts_generated": 2}',
    )
    r = await client.get(f"/api/v1/admin/jobs/{rid}", headers=ops.headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["request_params"] == {"horizon_weeks": 12}
    assert body["result_summary"] == {"series": 1, "data_source": "chronos_zero_shot", "alerts_generated": 2}
    assert "result" not in body


async def test_unknown_job_is_404(client: AsyncClient, db_session: AsyncSession) -> None:
    ops = await create_platform_admin(db_session)
    assert (await client.get(f"/api/v1/admin/jobs/{uuid.uuid4()}", headers=ops.headers)).status_code == 404
```

- [ ] **Step 2: Run to see failures**

Run: `uv run pytest tests/test_admin_jobs_read.py -v`
Expected: FAIL — 404 on `/api/v1/admin/jobs`.

- [ ] **Step 3: Add the schemas**

Append to `backend/app/schemas/admin.py`:

```python
class JobOut(BaseModel):
    id: uuid.UUID
    type: str
    tenant_id: uuid.UUID
    tenant_slug: str
    tenant_name: str
    industry: str
    status: str
    horizon_weeks: int
    created_at: datetime
    completed_at: datetime | None
    duration_seconds: float | None
    error: str | None
    trigger_source: str
    triggered_by_email: str | None
    retry_of: uuid.UUID | None
    is_stale: bool


class JobResultSummaryOut(BaseModel):
    series: int | None
    data_source: str | None
    alerts_generated: int | None


class JobDetailOut(JobOut):
    request_params: dict
    result_summary: JobResultSummaryOut | None
```

- [ ] **Step 4: Implement the service**

Create `backend/app/services/admin/jobs.py`:

```python
"""Forecast jobs across tenants.

The only queued job type in SANKET is the hybrid forecast
(`hybrid_forecast_runs` + arq `run_hybrid_forecast`). Integration syncs run as
in-process tasks whose state lives on `integration_connections`, so they are
shown under Integrations, not here — asking for another type returns nothing
rather than a fabricated list.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import aliased

from app.core.exceptions import NotFoundError
from app.core.platform_authz import PlatformPrincipal
from app.models.tenant import Tenant, User
from app.models.trend import HybridForecastRun
from app.schemas.admin import JobDetailOut, JobOut, JobResultSummaryOut, Page
from app.services.admin.data_access import platform_read
from app.services.admin.directory import STALE_PENDING, STALE_RUNNING, stale_condition

JOB_TYPE = "forecast.hybrid"

_Trigger = aliased(User)
_COLUMNS = (
    HybridForecastRun.id,
    HybridForecastRun.tenant_id,
    HybridForecastRun.industry,
    HybridForecastRun.status,
    HybridForecastRun.horizon_weeks,
    HybridForecastRun.created_at,
    HybridForecastRun.completed_at,
    HybridForecastRun.error,
    HybridForecastRun.trigger_source,
    HybridForecastRun.retry_of,
    Tenant.slug.label("tenant_slug"),
    Tenant.display_name.label("tenant_name"),
    _Trigger.email.label("triggered_by_email"),
)


def _is_stale(status: str, created_at: datetime, now: datetime) -> bool:
    created = created_at if created_at.tzinfo else created_at.replace(tzinfo=UTC)
    return (status == "pending" and now - created > STALE_PENDING) or (
        status == "running" and now - created > STALE_RUNNING
    )


def _job(r: Any, now: datetime) -> dict[str, Any]:
    duration = None
    if r.completed_at is not None and r.created_at is not None:
        created = r.created_at if r.created_at.tzinfo else r.created_at.replace(tzinfo=UTC)
        duration = (r.completed_at - created).total_seconds()
    return {
        "id": r.id,
        "type": JOB_TYPE,
        "tenant_id": r.tenant_id,
        "tenant_slug": str(r.tenant_slug),
        "tenant_name": r.tenant_name,
        "industry": getattr(r.industry, "value", str(r.industry)),
        "status": r.status,
        "horizon_weeks": r.horizon_weeks,
        "created_at": r.created_at,
        "completed_at": r.completed_at,
        "duration_seconds": duration,
        "error": (r.error or None) and r.error[:500],
        "trigger_source": r.trigger_source,
        "triggered_by_email": str(r.triggered_by_email) if r.triggered_by_email else None,
        "retry_of": r.retry_of,
        "is_stale": _is_stale(r.status, r.created_at, now),
    }


def _base():  # noqa: ANN202
    return (
        select(*_COLUMNS)
        .join(Tenant, Tenant.id == HybridForecastRun.tenant_id)
        .outerjoin(_Trigger, _Trigger.id == HybridForecastRun.triggered_by)
        .where(Tenant.is_operator.is_(False))
    )


async def list_jobs(
    db: Any,
    principal: PlatformPrincipal,
    *,
    tenant_id: uuid.UUID | None,
    status: str | None,
    job_type: str | None,
    date_from: date | None,
    date_to: date | None,
    page: int,
    page_size: int,
) -> Page[JobOut]:
    if job_type is not None and job_type != JOB_TYPE:
        return Page[JobOut](items=[], total=0, page=page, page_size=page_size)
    now = datetime.now(tz=UTC)
    stmt = _base()
    if tenant_id is not None:
        stmt = stmt.where(HybridForecastRun.tenant_id == tenant_id)
    if status == "stale":
        stmt = stmt.where(stale_condition(now))
    elif status is not None:
        stmt = stmt.where(HybridForecastRun.status == status)
    if date_from is not None:
        stmt = stmt.where(HybridForecastRun.created_at >= datetime.combine(date_from, time.min, UTC))
    if date_to is not None:
        end = datetime.combine(date_to, time.min, UTC) + timedelta(days=1)
        stmt = stmt.where(HybridForecastRun.created_at < end)
    async with platform_read(db, principal) as session:
        total = int(await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = (
            await session.execute(
                stmt.order_by(HybridForecastRun.created_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    return Page[JobOut](
        items=[JobOut(**_job(r, now)) for r in rows], total=total, page=page, page_size=page_size
    )


async def job_detail(db: Any, principal: PlatformPrincipal, job_id: uuid.UUID) -> JobDetailOut:
    now = datetime.now(tz=UTC)
    series = func.jsonb_array_length(HybridForecastRun.result["series"])
    async with platform_read(db, principal) as session:
        row = (
            await session.execute(
                _base()
                .add_columns(
                    HybridForecastRun.request_params,
                    HybridForecastRun.result.is_not(None).label("has_result"),
                    series.label("series"),
                    HybridForecastRun.result["data_source"].astext.label("data_source"),
                    HybridForecastRun.result["alerts_generated"].astext.label("alerts"),
                )
                .where(HybridForecastRun.id == job_id)
            )
        ).first()
    if row is None:
        raise NotFoundError("Job")
    summary = None
    if row.has_result:
        summary = JobResultSummaryOut(
            series=row.series,
            data_source=row.data_source,
            alerts_generated=int(row.alerts) if row.alerts is not None else None,
        )
    return JobDetailOut(
        **_job(row, now), request_params=row.request_params or {}, result_summary=summary
    )
```

- [ ] **Step 5: Add the router**

Create `backend/app/routers/admin/jobs.py`:

```python
from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request

from app.core.platform_authz import ReadPrincipal
from app.schemas.admin import JobDetailOut, JobOut, Page
from app.services.admin import jobs as job_service

router = APIRouter(tags=["platform-admin"])


@router.get("/jobs", response_model=Page[JobOut])
async def list_jobs(
    request: Request,
    principal: ReadPrincipal,
    tenant_id: uuid.UUID | None = None,
    status: Literal["pending", "running", "completed", "failed", "stale"] | None = None,
    type: Annotated[str | None, Query(max_length=64)] = None,  # noqa: A002 - public query name
    date_from: date | None = None,
    date_to: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> Page[JobOut]:
    return await job_service.list_jobs(
        request.app.state.db, principal, tenant_id=tenant_id, status=status, job_type=type,
        date_from=date_from, date_to=date_to, page=page, page_size=page_size,
    )


@router.get("/jobs/{job_id}", response_model=JobDetailOut)
async def job_detail(job_id: uuid.UUID, request: Request, principal: ReadPrincipal) -> JobDetailOut:
    return await job_service.job_detail(request.app.state.db, principal, job_id)
```

Append `jobs` to `ROUTER_MODULES`.

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/test_admin_jobs_read.py tests/test_admin_route_guard.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/admin/jobs.py backend/app/schemas/admin.py \
  backend/app/routers/admin/jobs.py backend/app/routers/admin/__init__.py \
  backend/tests/test_admin_jobs_read.py
git commit -m "feat(admin): forecast job list and detail across tenants"
```

---

### Task 2.6: Support sessions and the gated customer-data views

**Files:**
- Create: `backend/app/services/admin/support.py`
- Create: `backend/app/services/admin/data.py` (read half: `data_summary`, `data_quality`)
- Modify: `backend/app/schemas/admin.py`
- Create: `backend/app/routers/admin/support.py`, `backend/app/routers/admin/data.py`, `backend/app/routers/admin/audit.py` (tenant audit only in this task)
- Modify: `backend/app/routers/admin/__init__.py`
- Test: `backend/tests/test_admin_support.py`

**Interfaces:**
- Produces:
  - `support.SUPPORT_SESSION_REQUIRED = "support_session_required"`
  - `async support.open_session(db, principal, tenant_id, *, reason: str, minutes: int) -> SupportSessionOut`
  - `async support.active_session(db, principal, tenant_id) -> SupportSessionOut | None`
  - `async support.end_session(db, principal, session_id) -> SupportSessionOut`
  - `async support.require_support_session(tenant_id: uuid.UUID, request: Request, principal: ReadPrincipal) -> SupportSessionOut` and `ActiveSupportSession = Annotated[SupportSessionOut, Depends(require_support_session)]`
  - `async data.data_summary(db, principal, tenant_id) -> DataSummaryOut`; `async data.data_quality(db, principal, tenant_id) -> dict`
  - `async tenant_audit(db, principal, tenant_id, *, action, page, page_size) -> Page[TenantAuditEntryOut]` (in `routers/admin/audit.py` via service `services/admin/audit_views.py`)
  - Schemas `SupportSessionIn`, `SupportSessionOut`, `ImportSummaryOut`, `DataQualitySummaryOut`, `DataSummaryOut`, `TenantAuditEntryOut`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_admin_support.py`:

```python
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from admin_factories import create_customer_tenant, create_platform_admin

pytestmark = pytest.mark.asyncio

GATED = ("audit", "data/quality")


async def _open(client: AsyncClient, headers: dict, tenant: uuid.UUID, **body) -> dict:
    payload = {"reason": "Investigating a failed CSV import", "minutes": 30, **body}
    r = await client.post(f"/api/v1/admin/tenants/{tenant}/support-sessions", json=payload, headers=headers)
    return {"status": r.status_code, "body": r.json()}


async def test_gated_views_need_a_session(client: AsyncClient, db_session: AsyncSession) -> None:
    ops = await create_platform_admin(db_session, "platform_support")
    tid = await create_customer_tenant(db_session)
    for path in GATED:
        r = await client.get(f"/api/v1/admin/tenants/{tid}/{path}", headers=ops.headers)
        assert r.status_code == 403, path
        assert r.json()["detail"] == "support_session_required"

    opened = await _open(client, ops.headers, tid)
    assert opened["status"] == 201, opened
    assert opened["body"]["active"] is True
    assert 0 < opened["body"]["seconds_remaining"] <= 30 * 60

    for path in GATED:
        r = await client.get(f"/api/v1/admin/tenants/{tid}/{path}", headers=ops.headers)
        assert r.status_code == 200, (path, r.text)


async def test_a_session_is_personal_and_per_tenant(client: AsyncClient, db_session: AsyncSession) -> None:
    alice = await create_platform_admin(db_session)
    bob = await create_platform_admin(db_session)
    a = await create_customer_tenant(db_session)
    b = await create_customer_tenant(db_session)
    assert (await _open(client, alice.headers, a))["status"] == 201
    assert (await client.get(f"/api/v1/admin/tenants/{a}/audit", headers=bob.headers)).status_code == 403
    assert (await client.get(f"/api/v1/admin/tenants/{b}/audit", headers=alice.headers)).status_code == 403


async def test_expired_sessions_do_not_count(client: AsyncClient, db_session: AsyncSession) -> None:
    ops = await create_platform_admin(db_session)
    tid = await create_customer_tenant(db_session)
    await db_session.execute(
        text(
            "INSERT INTO support_access_sessions (tenant_id, admin_user_id, reason, created_at, expires_at) "
            "VALUES (:t, :u, 'an old investigation', now() - interval '1 hour', now() - interval '30 minutes')"
        ),
        {"t": str(tid), "u": str(ops.user_id)},
    )
    await db_session.commit()
    assert (await client.get(f"/api/v1/admin/tenants/{tid}/audit", headers=ops.headers)).status_code == 403


async def test_session_limits(client: AsyncClient, db_session: AsyncSession) -> None:
    ops = await create_platform_admin(db_session)
    tid = await create_customer_tenant(db_session)
    assert (await _open(client, ops.headers, tid, minutes=121))["status"] == 422
    assert (await _open(client, ops.headers, tid, reason="short"))["status"] == 422
    assert (await _open(client, ops.headers, tid))["status"] == 201
    assert (await _open(client, ops.headers, tid))["status"] == 409


async def test_ending_a_session_relocks_and_both_logs_record_it(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    ops = await create_platform_admin(db_session)
    tid = await create_customer_tenant(db_session)
    sid = (await _open(client, ops.headers, tid))["body"]["id"]

    active = await client.get(f"/api/v1/admin/tenants/{tid}/support-sessions/active", headers=ops.headers)
    assert active.json()["id"] == sid

    r = await client.post(f"/api/v1/admin/support-sessions/{sid}/end", headers=ops.headers)
    assert r.status_code == 200, r.text
    assert r.json()["active"] is False
    assert (await client.get(f"/api/v1/admin/tenants/{tid}/audit", headers=ops.headers)).status_code == 403
    none_active = await client.get(f"/api/v1/admin/tenants/{tid}/support-sessions/active", headers=ops.headers)
    assert none_active.json() is None

    platform = await db_session.scalar(
        text(
            "SELECT count(*) FROM platform_audit_events WHERE tenant_id = :t "
            "AND action IN ('platform.support_session.open', 'platform.support_session.end')"
        ),
        {"t": str(tid)},
    )
    mirrored = await db_session.scalar(
        text(
            "SELECT count(*) FROM audit_log WHERE tenant_id = :t "
            "AND action IN ('platform.support_session.open', 'platform.support_session.end')"
        ),
        {"t": str(tid)},
    )
    assert platform == 2
    assert mirrored == 2


async def test_another_operator_cannot_end_my_session(client: AsyncClient, db_session: AsyncSession) -> None:
    alice = await create_platform_admin(db_session)
    bob = await create_platform_admin(db_session)
    tid = await create_customer_tenant(db_session)
    sid = (await _open(client, alice.headers, tid))["body"]["id"]
    r = await client.post(f"/api/v1/admin/support-sessions/{sid}/end", headers=bob.headers)
    assert r.status_code == 404


async def test_data_summary_is_open_metadata(client: AsyncClient, db_session: AsyncSession) -> None:
    ops = await create_platform_admin(db_session, "platform_support")
    tid = await create_customer_tenant(db_session)
    r = await client.get(f"/api/v1/admin/tenants/{tid}/data", headers=ops.headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sales_rows"] == 0
    assert body["active_skus"] == 0
    assert "health_score" in body["quality"]
    assert "findings" not in body["quality"]
```

- [ ] **Step 2: Run to see failures**

Run: `uv run pytest tests/test_admin_support.py -v`
Expected: FAIL — 404s for the new routes.

- [ ] **Step 3: Add the schemas**

Append to `backend/app/schemas/admin.py`:

```python
class SupportSessionIn(BaseModel):
    reason: str = Field(min_length=10, max_length=500)
    minutes: int = Field(ge=1, le=120)


class SupportSessionOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    admin_user_id: uuid.UUID
    reason: str
    created_at: datetime
    expires_at: datetime
    ended_at: datetime | None
    active: bool
    seconds_remaining: int


class ImportSummaryOut(BaseModel):
    provider: str
    last_sync_at: datetime | None
    last_sync_status: str | None
    stats: dict[str, int]


class DataQualitySummaryOut(BaseModel):
    health_score: int
    grade: str
    critical: int
    warnings: int
    issues_found: int


class DataSummaryOut(BaseModel):
    products: int
    active_skus: int
    sales_rows: int
    inventory_rows: int
    first_sale_at: datetime | None
    last_sale_at: datetime | None
    weeks_covered: int
    last_imports: list[ImportSummaryOut]
    quality: DataQualitySummaryOut


class TenantAuditEntryOut(BaseModel):
    id: int
    occurred_at: datetime
    user_id: uuid.UUID | None
    action: str
    entity_type: str
    entity_id: str | None
    old_value: dict | None
    new_value: dict | None
    ip_address: str | None
    request_id: str | None
```

- [ ] **Step 4: Implement the support service**

Create `backend/app/services/admin/support.py`:

```python
"""Time-limited support sessions (spec §6.5).

A session is personal (owner = the operator who opened it), per tenant,
reason-bearing, and capped at PLATFORM_SUPPORT_SESSION_MAX_MINUTES (the
database also caps it at two hours). It unlocks *reads* of customer data only.
Opening and ending are recorded in both the platform log and the customer's
own audit log.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import Depends, Request
from sqlalchemy import func, select

from app.config import get_settings
from app.core.exceptions import ConflictError, NotFoundError, PermissionDeniedError, ValidationError
from app.core.platform_authz import PlatformPrincipal, ReadPrincipal
from app.models.platform import PlatformRole, SupportAccessSession
from app.models.tenant import Tenant
from app.schemas.admin import SupportSessionOut
from app.services.admin.audit import record_platform_event
from app.services.admin.data_access import platform_read, platform_write

SUPPORT_SESSION_REQUIRED = "support_session_required"


def _out(row: SupportAccessSession, now: datetime) -> SupportSessionOut:
    active = row.ended_at is None and row.expires_at > now
    return SupportSessionOut(
        id=row.id,
        tenant_id=row.tenant_id,
        admin_user_id=row.admin_user_id,
        reason=row.reason,
        created_at=row.created_at,
        expires_at=row.expires_at,
        ended_at=row.ended_at,
        active=active,
        seconds_remaining=max(0, int((row.expires_at - now).total_seconds())) if active else 0,
    )


def _live(tenant_id: uuid.UUID, admin_user_id: uuid.UUID):  # noqa: ANN202
    return select(SupportAccessSession).where(
        SupportAccessSession.tenant_id == tenant_id,
        SupportAccessSession.admin_user_id == admin_user_id,
        SupportAccessSession.ended_at.is_(None),
        SupportAccessSession.expires_at > func.now(),
    )


async def open_session(
    db: Any, principal: PlatformPrincipal, tenant_id: uuid.UUID, *, reason: str, minutes: int
) -> SupportSessionOut:
    limit = get_settings().platform_support_session_max_minutes
    if minutes > limit:
        raise ValidationError(f"Support sessions may last at most {limit} minutes")
    async with platform_write(db, principal) as session:
        tenant = await session.get(Tenant, tenant_id)
        if tenant is None or tenant.is_operator:
            raise NotFoundError("Tenant")
        existing = await session.scalar(_live(tenant_id, principal.user_id))
        if existing is not None:
            raise ConflictError(
                f"You already have a support session for this tenant until "
                f"{existing.expires_at.isoformat()}"
            )
        row = SupportAccessSession(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            admin_user_id=principal.user_id,
            reason=reason.strip(),
            # DB clock for both ends, so the 2-hour CHECK compares like with like.
            expires_at=func.now() + timedelta(minutes=minutes),
        )
        session.add(row)
        await session.flush()
        await session.refresh(row)
        await record_platform_event(
            session,
            principal,
            action="platform.support_session.open",
            target_type="support_session",
            target_id=str(row.id),
            tenant=tenant,
            detail={"reason": row.reason, "minutes": minutes, "expires_at": row.expires_at},
            mirror=True,
        )
        return _out(row, datetime.now(tz=UTC))


async def active_session(
    db: Any, principal: PlatformPrincipal, tenant_id: uuid.UUID
) -> SupportSessionOut | None:
    async with platform_read(db, principal) as session:
        row = await session.scalar(
            _live(tenant_id, principal.user_id).order_by(SupportAccessSession.expires_at.desc())
        )
        return _out(row, datetime.now(tz=UTC)) if row is not None else None


async def end_session(
    db: Any, principal: PlatformPrincipal, session_id: uuid.UUID
) -> SupportSessionOut:
    async with platform_write(db, principal) as session:
        row = await session.get(SupportAccessSession, session_id)
        mine = row is not None and (
            row.admin_user_id == principal.user_id
            or principal.role is PlatformRole.platform_super_admin
        )
        if not mine:
            raise NotFoundError("Support session")
        if row.ended_at is None:
            row.ended_at = func.now()
            row.ended_by = principal.user_id
            await session.flush()
            await session.refresh(row)
            tenant = await session.get(Tenant, row.tenant_id)
            await record_platform_event(
                session,
                principal,
                action="platform.support_session.end",
                target_type="support_session",
                target_id=str(row.id),
                tenant=tenant,
                mirror=True,
            )
        return _out(row, datetime.now(tz=UTC))


async def require_support_session(
    tenant_id: uuid.UUID, request: Request, principal: ReadPrincipal
) -> SupportSessionOut:
    found = await active_session(request.app.state.db, principal, tenant_id)
    if found is None:
        raise PermissionDeniedError(SUPPORT_SESSION_REQUIRED)
    return found


ActiveSupportSession = Annotated[SupportSessionOut, Depends(require_support_session)]
```

- [ ] **Step 5: Implement the data read service and tenant audit view**

Create `backend/app/services/admin/data.py`:

```python
"""A tenant's data, as far as the console may see it.

`data_summary` is metadata (counts, dates, scores) and is always visible.
`data_quality` returns findings that include SKU codes — customer data — and is
reachable only behind a support session (see routers/admin/data.py).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select

from app.core.platform_authz import PlatformPrincipal
from app.models.integration import IntegrationConnection
from app.models.inventory import InventoryLevel
from app.models.product import Product, Sku
from app.models.sales import HistoricalSale
from app.schemas.admin import DataQualitySummaryOut, DataSummaryOut, ImportSummaryOut
from app.services import data_quality_audit
from app.services.admin.data_access import tenant_scope

UPLOAD_PROVIDERS = ("csv_upload", "excel_upload")


async def data_summary(
    db: Any, principal: PlatformPrincipal, tenant_id: uuid.UUID
) -> DataSummaryOut:
    async with tenant_scope(db, principal, tenant_id) as (session, tenant):
        ind = tenant.industry

        async def count(stmt: Any) -> int:
            return int(await session.scalar(stmt) or 0)

        products = await count(select(func.count()).select_from(Product).where(Product.tenant_id == tenant_id))
        skus = await count(
            select(func.count()).select_from(Sku).where(Sku.tenant_id == tenant_id, Sku.is_active.is_(True))
        )
        sales = await count(
            select(func.count()).select_from(HistoricalSale).where(HistoricalSale.tenant_id == tenant_id)
        )
        inventory = await count(
            select(func.count()).select_from(InventoryLevel).where(InventoryLevel.tenant_id == tenant_id)
        )
        first_sale, last_sale = (
            await session.execute(
                select(func.min(HistoricalSale.sale_time), func.max(HistoricalSale.sale_time)).where(
                    HistoricalSale.tenant_id == tenant_id
                )
            )
        ).one()
        weeks = await count(
            select(func.count(func.distinct(func.date_trunc("week", HistoricalSale.sale_time)))).where(
                HistoricalSale.tenant_id == tenant_id,
                HistoricalSale.industry == ind,
                HistoricalSale.sale_time >= datetime.now(UTC) - timedelta(weeks=156),
            )
        )
        uploads = (
            await session.execute(
                select(
                    IntegrationConnection.provider,
                    IntegrationConnection.last_sync_at,
                    IntegrationConnection.last_sync_status,
                    IntegrationConnection.last_sync_stats,
                ).where(
                    IntegrationConnection.tenant_id == tenant_id,
                    IntegrationConnection.provider.in_(UPLOAD_PROVIDERS),
                )
            )
        ).all()
        quality = await data_quality_audit.audit(session, tenant_id=tenant_id, industry=ind.value)
    return DataSummaryOut(
        products=products,
        active_skus=skus,
        sales_rows=sales,
        inventory_rows=inventory,
        first_sale_at=first_sale,
        last_sale_at=last_sale,
        weeks_covered=weeks,
        last_imports=[
            ImportSummaryOut(
                provider=u.provider,
                last_sync_at=u.last_sync_at,
                last_sync_status=u.last_sync_status,
                stats={k: int(v) for k, v in (u.last_sync_stats or {}).items() if isinstance(v, int | float)},
            )
            for u in uploads
        ],
        quality=DataQualitySummaryOut(
            health_score=quality["health_score"],
            grade=quality["grade"],
            critical=quality["critical"],
            warnings=quality["warnings"],
            issues_found=quality["issues_found"],
        ),
    )


async def data_quality(db: Any, principal: PlatformPrincipal, tenant_id: uuid.UUID) -> dict:
    async with tenant_scope(db, principal, tenant_id) as (session, tenant):
        return await data_quality_audit.audit(
            session, tenant_id=tenant_id, industry=tenant.industry.value
        )
```

Create `backend/app/services/admin/audit_views.py`:

```python
"""Read views over the two audit logs."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import func, select

from app.core.platform_authz import PlatformPrincipal
from app.models.audit import AuditLog
from app.schemas.admin import Page, TenantAuditEntryOut
from app.services.admin.data_access import tenant_scope
from app.services.admin.directory import escape_like


async def tenant_audit(
    db: Any,
    principal: PlatformPrincipal,
    tenant_id: uuid.UUID,
    *,
    action: str | None,
    page: int,
    page_size: int,
) -> Page[TenantAuditEntryOut]:
    async with tenant_scope(db, principal, tenant_id) as (session, _tenant):
        stmt = select(AuditLog).where(AuditLog.tenant_id == tenant_id)
        if action:
            stmt = stmt.where(AuditLog.action.like(f"{escape_like(action)}%", escape="\\"))
        total = int(await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = (
            await session.scalars(
                stmt.order_by(AuditLog.occurred_at.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
        items = [
            TenantAuditEntryOut(
                id=r.id,
                occurred_at=r.occurred_at,
                user_id=r.user_id,
                action=r.action,
                entity_type=r.entity_type,
                entity_id=r.entity_id,
                old_value=r.old_value,
                new_value=r.new_value,
                ip_address=str(r.ip_address) if r.ip_address else None,
                request_id=r.request_id,
            )
            for r in rows
        ]
    return Page[TenantAuditEntryOut](items=items, total=total, page=page, page_size=page_size)
```

- [ ] **Step 6: Add the routers**

Create `backend/app/routers/admin/support.py`:

```python
from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, status

from app.core.platform_authz import SupportPrincipal
from app.schemas.admin import SupportSessionIn, SupportSessionOut
from app.services.admin import support as support_service

router = APIRouter(tags=["platform-admin"])


@router.post(
    "/tenants/{tenant_id}/support-sessions",
    response_model=SupportSessionOut,
    status_code=status.HTTP_201_CREATED,
)
async def open_support_session(
    tenant_id: uuid.UUID, body: SupportSessionIn, request: Request, principal: SupportPrincipal
) -> SupportSessionOut:
    return await support_service.open_session(
        request.app.state.db, principal, tenant_id, reason=body.reason, minutes=body.minutes
    )


@router.get("/tenants/{tenant_id}/support-sessions/active", response_model=SupportSessionOut | None)
async def my_active_session(
    tenant_id: uuid.UUID, request: Request, principal: SupportPrincipal
) -> SupportSessionOut | None:
    return await support_service.active_session(request.app.state.db, principal, tenant_id)


@router.post("/support-sessions/{session_id}/end", response_model=SupportSessionOut)
async def end_support_session(
    session_id: uuid.UUID, request: Request, principal: SupportPrincipal
) -> SupportSessionOut:
    return await support_service.end_session(request.app.state.db, principal, session_id)
```

Create `backend/app/routers/admin/data.py`:

```python
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Request

from app.core.platform_authz import ReadPrincipal
from app.schemas.admin import DataSummaryOut
from app.services.admin import data as data_service
from app.services.admin.support import ActiveSupportSession

router = APIRouter(tags=["platform-admin"])


@router.get("/tenants/{tenant_id}/data", response_model=DataSummaryOut)
async def data_summary(tenant_id: uuid.UUID, request: Request, principal: ReadPrincipal) -> DataSummaryOut:
    return await data_service.data_summary(request.app.state.db, principal, tenant_id)


@router.get("/tenants/{tenant_id}/data/quality")
async def data_quality(
    tenant_id: uuid.UUID,
    request: Request,
    principal: ReadPrincipal,
    _support: ActiveSupportSession,
) -> dict[str, Any]:
    return await data_service.data_quality(request.app.state.db, principal, tenant_id)
```

Create `backend/app/routers/admin/audit.py`:

```python
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.core.platform_authz import ReadPrincipal
from app.schemas.admin import Page, TenantAuditEntryOut
from app.services.admin.audit_views import tenant_audit
from app.services.admin.support import ActiveSupportSession

router = APIRouter(tags=["platform-admin"])


@router.get("/tenants/{tenant_id}/audit", response_model=Page[TenantAuditEntryOut])
async def tenant_audit_log(
    tenant_id: uuid.UUID,
    request: Request,
    principal: ReadPrincipal,
    _support: ActiveSupportSession,
    action: Annotated[str | None, Query(max_length=100)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> Page[TenantAuditEntryOut]:
    return await tenant_audit(
        request.app.state.db, principal, tenant_id, action=action, page=page, page_size=page_size
    )
```

Append `support`, `data`, `audit` to `ROUTER_MODULES`.

- [ ] **Step 7: Run the tests**

Run: `uv run pytest tests/test_admin_support.py tests/test_admin_route_guard.py -v`
Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/admin/support.py backend/app/services/admin/data.py \
  backend/app/services/admin/audit_views.py backend/app/schemas/admin.py \
  backend/app/routers/admin/support.py backend/app/routers/admin/data.py \
  backend/app/routers/admin/audit.py backend/app/routers/admin/__init__.py \
  backend/tests/test_admin_support.py
git commit -m "feat(admin): time-limited support sessions gate customer-data views"
```

---

### Task 2.7: Platform audit log view

**Files:**
- Modify: `backend/app/services/admin/audit_views.py` (add `platform_audit`)
- Modify: `backend/app/schemas/admin.py` (add `PlatformAuditOut`)
- Modify: `backend/app/routers/admin/audit.py` (GET `/audit`)
- Test: `backend/tests/test_admin_platform_audit.py`

**Interfaces:**
- Produces: `async audit_views.platform_audit(db, principal, *, actor, action, tenant_id, outcome, date_from, date_to, page, page_size) -> Page[PlatformAuditOut]`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_admin_platform_audit.py`:

```python
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from admin_factories import create_customer, create_customer_tenant, create_platform_admin

pytestmark = pytest.mark.asyncio


async def test_platform_audit_lists_and_filters(client: AsyncClient, db_session: AsyncSession) -> None:
    ops = await create_platform_admin(db_session, "platform_support")
    await client.post("/api/v1/admin/session", headers=ops.headers)
    tenant = await create_customer_tenant(db_session)
    customer = await create_customer(db_session, tenant)
    await client.get("/api/v1/admin/tenants", headers=customer.headers)  # denied → recorded

    r = await client.get("/api/v1/admin/audit", params={"actor": ops.email}, headers=ops.headers)
    assert r.status_code == 200, r.text
    assert "platform.console.sign_in" in [e["action"] for e in r.json()["items"]]

    r = await client.get(
        "/api/v1/admin/audit", params={"outcome": "denied", "actor": str(customer.user_id)},
        headers=ops.headers,
    )
    items = r.json()["items"]
    assert items and all(e["outcome"] == "denied" for e in items)

    r = await client.get("/api/v1/admin/audit", params={"action": "platform.console"}, headers=ops.headers)
    assert all(e["action"].startswith("platform.console") for e in r.json()["items"])
```

- [ ] **Step 2: Run to see it fail**

Run: `uv run pytest tests/test_admin_platform_audit.py -v`
Expected: FAIL — 404 on `/api/v1/admin/audit`.

- [ ] **Step 3: Implement**

Append to `backend/app/schemas/admin.py`:

```python
class PlatformAuditOut(BaseModel):
    id: int
    occurred_at: datetime
    actor_user_id: uuid.UUID | None
    actor_email: str | None
    actor_role: str | None
    action: str
    target_type: str
    target_id: str | None
    tenant_id: uuid.UUID | None
    tenant_slug: str | None
    outcome: str
    detail: dict
    ip_address: str | None
    request_id: str | None
```

Append to `backend/app/services/admin/audit_views.py` (add imports: `from datetime import UTC, date, datetime, time, timedelta`, `from sqlalchemy import or_`, `from app.models.platform import PlatformAuditEvent`, `from app.models.tenant import Tenant`, `from app.schemas.admin import PlatformAuditOut`, `from app.services.admin.data_access import platform_read`):

```python
async def platform_audit(
    db: Any,
    principal: PlatformPrincipal,
    *,
    actor: str | None,
    action: str | None,
    tenant_id: uuid.UUID | None,
    outcome: str | None,
    date_from: date | None,
    date_to: date | None,
    page: int,
    page_size: int,
) -> Page[PlatformAuditOut]:
    stmt = select(PlatformAuditEvent, Tenant.slug.label("tenant_slug")).outerjoin(
        Tenant, Tenant.id == PlatformAuditEvent.tenant_id
    )
    if actor:
        try:
            stmt = stmt.where(PlatformAuditEvent.actor_user_id == uuid.UUID(actor))
        except ValueError:
            stmt = stmt.where(
                PlatformAuditEvent.actor_email.ilike(f"%{escape_like(actor)}%", escape="\\")
            )
    if action:
        stmt = stmt.where(PlatformAuditEvent.action.like(f"{escape_like(action)}%", escape="\\"))
    if tenant_id is not None:
        stmt = stmt.where(PlatformAuditEvent.tenant_id == tenant_id)
    if outcome:
        stmt = stmt.where(PlatformAuditEvent.outcome == outcome)
    if date_from is not None:
        stmt = stmt.where(PlatformAuditEvent.occurred_at >= datetime.combine(date_from, time.min, UTC))
    if date_to is not None:
        stmt = stmt.where(
            PlatformAuditEvent.occurred_at < datetime.combine(date_to, time.min, UTC) + timedelta(days=1)
        )
    async with platform_read(db, principal) as session:
        total = int(await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
        rows = (
            await session.execute(
                stmt.order_by(PlatformAuditEvent.occurred_at.desc(), PlatformAuditEvent.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    return Page[PlatformAuditOut](
        items=[
            PlatformAuditOut(
                id=e.id,
                occurred_at=e.occurred_at,
                actor_user_id=e.actor_user_id,
                actor_email=str(e.actor_email) if e.actor_email else None,
                actor_role=e.actor_role,
                action=e.action,
                target_type=e.target_type,
                target_id=e.target_id,
                tenant_id=e.tenant_id,
                tenant_slug=str(slug) if slug else None,
                outcome=e.outcome,
                detail=e.detail or {},
                ip_address=str(e.ip_address) if e.ip_address else None,
                request_id=e.request_id,
            )
            for e, slug in rows
        ],
        total=total,
        page=page,
        page_size=page_size,
    )
```

(`or_` is not needed; do not import it.)

Append to `backend/app/routers/admin/audit.py` (add `from datetime import date`, `from typing import Literal`, `PlatformAuditOut` import, and `platform_audit` import):

```python
@router.get("/audit", response_model=Page[PlatformAuditOut])
async def platform_audit_log(
    request: Request,
    principal: ReadPrincipal,
    actor: Annotated[str | None, Query(max_length=200)] = None,
    action: Annotated[str | None, Query(max_length=100)] = None,
    tenant_id: uuid.UUID | None = None,
    outcome: Literal["success", "failure", "denied"] | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 50,
) -> Page[PlatformAuditOut]:
    return await platform_audit(
        request.app.state.db, principal, actor=actor, action=action, tenant_id=tenant_id,
        outcome=outcome, date_from=date_from, date_to=date_to, page=page, page_size=page_size,
    )
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_admin_platform_audit.py tests/test_admin_route_guard.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/admin/audit_views.py backend/app/schemas/admin.py \
  backend/app/routers/admin/audit.py backend/tests/test_admin_platform_audit.py
git commit -m "feat(admin): searchable platform audit log"
```

---

### Task 2.8: Dashboard and notifications

**Files:**
- Create: `backend/app/services/admin/metrics.py` (dashboard + notifications)
- Modify: `backend/app/schemas/admin.py`
- Create: `backend/app/routers/admin/dashboard.py`
- Modify: `backend/app/routers/admin/__init__.py`
- Test: `backend/tests/test_admin_dashboard.py`

**Interfaces:**
- Produces: `async metrics.dashboard(db, principal) -> DashboardOut`; `async metrics.notifications(db, principal) -> list[NotificationOut]`; schemas `DashboardMetricsOut`, `RecentEventOut`, `RecentActivityOut`, `DashboardOut`, `NotificationOut`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_admin_dashboard.py`:

```python
"""Dashboard numbers must equal the definitions in spec §8.4.

The database is shared across the suite, so each metric is checked against the
same definition computed directly in SQL rather than against a fixed number.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from admin_factories import create_customer_tenant, create_platform_admin
from app.config import get_settings

pytestmark = pytest.mark.asyncio

_CUSTOMER = "t.is_operator = FALSE AND t.slug <> :sandbox"


async def _scalar(db: AsyncSession, sql: str) -> int:
    return int(await db.scalar(text(sql), {"sandbox": get_settings().sandbox_tenant_slug}) or 0)


async def test_dashboard_matches_definitions(client: AsyncClient, db_session: AsyncSession) -> None:
    ops = await create_platform_admin(db_session, "platform_support")
    await create_customer_tenant(db_session)
    await create_customer_tenant(db_session, status="suspended", subscribed=False)

    r = await client.get("/api/v1/admin/dashboard", headers=ops.headers)
    assert r.status_code == 200, r.text
    m = r.json()["metrics"]

    assert m["total_tenants"] == await _scalar(db_session, f"SELECT count(*) FROM tenants t WHERE {_CUSTOMER}")
    assert m["suspended_tenants"] == await _scalar(
        db_session, f"SELECT count(*) FROM tenants t WHERE {_CUSTOMER} AND t.status = 'suspended'"
    )
    assert m["active_subscriptions"] == await _scalar(
        db_session,
        "SELECT count(*) FROM subscriptions s JOIN tenants t ON t.id = s.tenant_id "
        f"WHERE {_CUSTOMER} AND s.status = 'active' AND s.current_period_end > now()",
    )
    assert m["total_users"] == await _scalar(
        db_session,
        f"SELECT count(*) FROM users u JOIN tenants t ON t.id = u.tenant_id WHERE {_CUSTOMER} AND u.is_active",
    )
    assert m["mrr_paise"] == await _scalar(
        db_session,
        "SELECT COALESCE(SUM(CASE WHEN p.billing_interval = 'year' THEN p.base_price_cents / 12 "
        "ELSE p.base_price_cents END), 0) FROM subscriptions s JOIN plans p ON p.id = s.plan_id "
        f"JOIN tenants t ON t.id = s.tenant_id WHERE {_CUSTOMER} AND s.status = 'active' "
        "AND s.current_period_end > now()",
    )
    assert m["currency"] == "INR"
    assert isinstance(r.json()["recent_events"], list)
    assert isinstance(r.json()["recent_activity"], list)


async def test_notifications_flag_failures(client: AsyncClient, db_session: AsyncSession) -> None:
    ops = await create_platform_admin(db_session)
    tid = await create_customer_tenant(db_session)
    await db_session.execute(
        text(
            "INSERT INTO hybrid_forecast_runs (tenant_id, industry, horizon_weeks, status, error) "
            "VALUES (:t, 'fashion', 12, 'failed', 'boom')"
        ),
        {"t": str(tid)},
    )
    await db_session.commit()
    r = await client.get("/api/v1/admin/notifications", headers=ops.headers)
    assert r.status_code == 200, r.text
    kinds = {n["kind"]: n for n in r.json()}
    assert kinds["jobs_failed"]["severity"] == "critical"
    assert kinds["jobs_failed"]["count"] >= 1
    assert kinds["jobs_failed"]["link"] == "/admin/jobs?status=failed"
```

- [ ] **Step 2: Run to see failures**

Run: `uv run pytest tests/test_admin_dashboard.py -v`
Expected: FAIL — 404 on `/api/v1/admin/dashboard`.

- [ ] **Step 3: Add the schemas**

Append to `backend/app/schemas/admin.py`:

```python
class DashboardMetricsOut(BaseModel):
    total_tenants: int
    internal_tenants: int
    active_tenants: int
    trial_tenants: int
    suspended_tenants: int
    archived_tenants: int
    active_subscriptions: int
    active_contracts: int
    mrr_paise: int
    currency: str
    total_users: int
    total_skus: int
    forecast_jobs_today: int
    failed_jobs_24h: int
    pending_jobs: int
    stale_jobs: int
    integration_failures: int


class RecentEventOut(BaseModel):
    occurred_at: datetime
    actor_email: str | None
    action: str
    target_type: str
    tenant_id: uuid.UUID | None
    outcome: str


class RecentActivityOut(BaseModel):
    occurred_at: datetime
    tenant_id: uuid.UUID
    tenant_slug: str
    tenant_name: str
    action: str
    entity_type: str


class DashboardOut(BaseModel):
    metrics: DashboardMetricsOut
    recent_events: list[RecentEventOut]
    recent_activity: list[RecentActivityOut]
    generated_at: datetime


class NotificationOut(BaseModel):
    kind: str
    severity: str  # critical | warning
    title: str
    detail: str
    link: str
    count: int
```

- [ ] **Step 4: Implement the metrics service**

Create `backend/app/services/admin/metrics.py`:

```python
"""Platform metrics. Every number is a definition from spec §8.4 applied to
real rows; the operator tenant and the public sandbox are excluded from
customer metrics and reported separately as internal."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, case, func, select

from app.config import get_settings
from app.core.platform_authz import PlatformPrincipal
from app.models.audit import AuditLog
from app.models.billing import Plan, Subscription, SubscriptionStatus
from app.models.enums import TenantStatus
from app.models.integration import IntegrationConnection
from app.models.platform import PlatformAuditEvent
from app.models.product import Sku
from app.models.tenant import Tenant, User
from app.models.trend import HybridForecastRun
from app.schemas.admin import (
    DashboardMetricsOut,
    DashboardOut,
    NotificationOut,
    RecentActivityOut,
    RecentEventOut,
)
from app.services.admin.data_access import platform_read
from app.services.admin.directory import stale_condition, tenant_rows


def _customer():  # noqa: ANN202
    return and_(Tenant.is_operator.is_(False), Tenant.slug != get_settings().sandbox_tenant_slug)


async def _count(session: Any, stmt: Any) -> int:
    return int(await session.scalar(stmt) or 0)


async def _metrics(session: Any, now: datetime) -> DashboardMetricsOut:
    customer = _customer()
    live = and_(Subscription.current_period_end > now)
    status_counts = dict(
        (
            await session.execute(
                select(Tenant.status, func.count()).where(customer).group_by(Tenant.status)
            )
        ).all()
    )
    total = sum(status_counts.values())
    internal = await _count(
        session, select(func.count()).select_from(Tenant).where(~customer)
    )
    entitled_join = (
        select(func.count(func.distinct(Subscription.tenant_id)))
        .join(Tenant, Tenant.id == Subscription.tenant_id)
        .where(customer, live)
    )
    active_tenants = await _count(
        session,
        entitled_join.where(
            Subscription.status.in_((SubscriptionStatus.active, SubscriptionStatus.trialing)),
            Tenant.status.not_in((TenantStatus.suspended, TenantStatus.cancelled)),
        ),
    )
    trial_tenants = await _count(
        session, entitled_join.where(Subscription.status == SubscriptionStatus.trialing)
    )
    active_subs = (
        select(Subscription, Plan)
        .join(Plan, Plan.id == Subscription.plan_id)
        .join(Tenant, Tenant.id == Subscription.tenant_id)
        .where(customer, live, Subscription.status == SubscriptionStatus.active)
        .subquery()
    )
    monthly = case(
        (active_subs.c.billing_interval == "year", active_subs.c.base_price_cents / 12),
        else_=active_subs.c.base_price_cents,
    )
    active_count, mrr, contracts = (
        await session.execute(
            select(
                func.count(),
                func.coalesce(func.sum(monthly), 0),
                func.count().filter(active_subs.c.base_price_cents == 0),
            ).select_from(active_subs)
        )
    ).one()
    users = await _count(
        session,
        select(func.count()).select_from(User).join(Tenant, Tenant.id == User.tenant_id).where(
            customer, User.is_active.is_(True)
        ),
    )
    skus = await _count(
        session,
        select(func.count()).select_from(Sku).join(Tenant, Tenant.id == Sku.tenant_id).where(
            customer, Sku.is_active.is_(True)
        ),
    )
    runs = (
        select(HybridForecastRun)
        .join(Tenant, Tenant.id == HybridForecastRun.tenant_id)
        .where(Tenant.is_operator.is_(False))
        .subquery()
    )
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    jobs_today, failed, pending = (
        await session.execute(
            select(
                func.count().filter(runs.c.created_at >= today),
                func.count().filter(
                    and_(runs.c.status == "failed", runs.c.created_at >= now - timedelta(hours=24))
                ),
                func.count().filter(runs.c.status.in_(("pending", "running"))),
            ).select_from(runs)
        )
    ).one()
    stale = await _count(
        session,
        select(func.count())
        .select_from(HybridForecastRun)
        .join(Tenant, Tenant.id == HybridForecastRun.tenant_id)
        .where(Tenant.is_operator.is_(False), stale_condition(now)),
    )
    integration_failures = await _count(
        session,
        select(func.count())
        .select_from(IntegrationConnection)
        .join(Tenant, Tenant.id == IntegrationConnection.tenant_id)
        .where(customer, IntegrationConnection.status == "error"),
    )
    return DashboardMetricsOut(
        total_tenants=total,
        internal_tenants=internal,
        active_tenants=active_tenants,
        trial_tenants=trial_tenants,
        suspended_tenants=int(status_counts.get(TenantStatus.suspended, 0)),
        archived_tenants=int(status_counts.get(TenantStatus.cancelled, 0)),
        active_subscriptions=int(active_count),
        active_contracts=int(contracts),
        mrr_paise=int(mrr),
        currency="INR",
        total_users=users,
        total_skus=skus,
        forecast_jobs_today=int(jobs_today),
        failed_jobs_24h=int(failed),
        pending_jobs=int(pending),
        stale_jobs=stale,
        integration_failures=integration_failures,
    )


async def dashboard(db: Any, principal: PlatformPrincipal) -> DashboardOut:
    now = datetime.now(tz=UTC)
    async with platform_read(db, principal) as session:
        metrics = await _metrics(session, now)
        events = (
            await session.scalars(
                select(PlatformAuditEvent).order_by(PlatformAuditEvent.occurred_at.desc()).limit(20)
            )
        ).all()
        activity = (
            await session.execute(
                select(
                    AuditLog.occurred_at,
                    AuditLog.tenant_id,
                    AuditLog.action,
                    AuditLog.entity_type,
                    Tenant.slug,
                    Tenant.display_name,
                )
                .join(Tenant, Tenant.id == AuditLog.tenant_id)
                .where(_customer())
                .order_by(AuditLog.occurred_at.desc())
                .limit(20)
            )
        ).all()
    return DashboardOut(
        metrics=metrics,
        recent_events=[
            RecentEventOut(
                occurred_at=e.occurred_at,
                actor_email=str(e.actor_email) if e.actor_email else None,
                action=e.action,
                target_type=e.target_type,
                tenant_id=e.tenant_id,
                outcome=e.outcome,
            )
            for e in events
        ],
        recent_activity=[
            RecentActivityOut(
                occurred_at=a.occurred_at,
                tenant_id=a.tenant_id,
                tenant_slug=str(a.slug),
                tenant_name=a.display_name,
                action=a.action,
                entity_type=a.entity_type,
            )
            for a in activity
        ],
        generated_at=now,
    )


async def notifications(db: Any, principal: PlatformPrincipal) -> list[NotificationOut]:
    now = datetime.now(tz=UTC)
    async with platform_read(db, principal) as session:
        m = await _metrics(session, now)
        rows = await tenant_rows(session)
    over = sum(1 for r in rows if r.over_limit)
    past_due = sum(1 for r in rows if r.subscription_state == "past_due")
    out: list[NotificationOut] = []

    def add(kind: str, severity: str, count: int, title: str, detail: str, link: str) -> None:
        if count:
            out.append(NotificationOut(kind=kind, severity=severity, title=title,
                                       detail=detail, link=link, count=count))

    add("jobs_failed", "critical", m.failed_jobs_24h, "Forecast jobs failed",
        f"{m.failed_jobs_24h} forecast job(s) failed in the last 24 hours", "/admin/jobs?status=failed")
    add("integrations_failed", "critical", m.integration_failures, "Integrations failing",
        f"{m.integration_failures} connection(s) are in an error state", "/admin/integrations?status=error")
    add("jobs_stale", "warning", m.stale_jobs, "Forecast jobs stuck",
        f"{m.stale_jobs} job(s) have been queued or running unusually long", "/admin/jobs?status=stale")
    add("tenants_over_limit", "warning", over, "Tenants over a limit",
        f"{over} tenant(s) exceed their SKU or seat limit", "/admin/usage?near_limit=over")
    add("subscriptions_past_due", "warning", past_due, "Payments past due",
        f"{past_due} subscription(s) are past due", "/admin/subscriptions?state=past_due")
    return out
```

- [ ] **Step 5: Add the router**

Create `backend/app/routers/admin/dashboard.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Request

from app.core.platform_authz import ReadPrincipal
from app.schemas.admin import DashboardOut, NotificationOut
from app.services.admin import metrics

router = APIRouter(tags=["platform-admin"])


@router.get("/dashboard", response_model=DashboardOut)
async def dashboard(request: Request, principal: ReadPrincipal) -> DashboardOut:
    return await metrics.dashboard(request.app.state.db, principal)


@router.get("/notifications", response_model=list[NotificationOut])
async def notifications(request: Request, principal: ReadPrincipal) -> list[NotificationOut]:
    return await metrics.notifications(request.app.state.db, principal)
```

Append `dashboard` to `ROUTER_MODULES`.

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/test_admin_dashboard.py tests/test_admin_route_guard.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/admin/metrics.py backend/app/schemas/admin.py \
  backend/app/routers/admin/dashboard.py backend/app/routers/admin/__init__.py \
  backend/tests/test_admin_dashboard.py
git commit -m "feat(admin): platform dashboard and computed notifications from real rows"
```

---

### Task 2.9: Global search

**Files:**
- Modify: `backend/app/services/admin/directory.py` (add `search`)
- Modify: `backend/app/schemas/admin.py`
- Create: `backend/app/routers/admin/search.py`
- Modify: `backend/app/routers/admin/__init__.py`
- Test: `backend/tests/test_admin_search.py`

**Interfaces:**
- Produces: `async directory.search(session, q: str, *, limit: int = 10) -> SearchOut`; schemas `SearchTenantHitOut`, `SearchUserHitOut`, `SearchOut`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_admin_search.py`:

```python
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from admin_factories import create_customer, create_customer_tenant, create_platform_admin

pytestmark = pytest.mark.asyncio


async def test_search_finds_tenants_and_users(client: AsyncClient, db_session: AsyncSession) -> None:
    ops = await create_platform_admin(db_session, "platform_support")
    tag = uuid.uuid4().hex[:6]
    tid = await create_customer_tenant(db_session, slug=f"chandler-{tag}", display_name=f"Chandler {tag}")
    user = await create_customer(db_session, tid)

    r = await client.get("/api/v1/admin/search", params={"q": f"chandler {tag}"}, headers=ops.headers)
    assert r.status_code == 200, r.text
    assert [t["id"] for t in r.json()["tenants"]] == [str(tid)]

    r = await client.get("/api/v1/admin/search", params={"q": str(tid)}, headers=ops.headers)
    assert [t["id"] for t in r.json()["tenants"]] == [str(tid)]

    r = await client.get("/api/v1/admin/search", params={"q": user.email}, headers=ops.headers)
    hits = r.json()["users"]
    assert hits[0]["email"] == user.email
    assert hits[0]["tenant_id"] == str(tid)


async def test_search_is_audited_and_validated(client: AsyncClient, db_session: AsyncSession) -> None:
    ops = await create_platform_admin(db_session)
    assert (await client.get("/api/v1/admin/search", params={"q": "a"}, headers=ops.headers)).status_code == 422
    await client.get("/api/v1/admin/search", params={"q": "zz-nothing"}, headers=ops.headers)
    count = await db_session.scalar(
        text(
            "SELECT count(*) FROM platform_audit_events WHERE actor_user_id = :u "
            "AND action = 'platform.search' AND detail->>'q' = 'zz-nothing'"
        ),
        {"u": str(ops.user_id)},
    )
    assert count == 1


async def test_search_escapes_wildcards(client: AsyncClient, db_session: AsyncSession) -> None:
    ops = await create_platform_admin(db_session)
    r = await client.get("/api/v1/admin/search", params={"q": "%%"}, headers=ops.headers)
    assert r.status_code == 200
    assert r.json() == {"tenants": [], "users": []}
```

- [ ] **Step 2: Run to see failures**

Run: `uv run pytest tests/test_admin_search.py -v`
Expected: FAIL — 404 on `/api/v1/admin/search`.

- [ ] **Step 3: Implement**

Append to `backend/app/schemas/admin.py`:

```python
class SearchTenantHitOut(BaseModel):
    id: uuid.UUID
    slug: str
    display_name: str
    industry: str
    status: str


class SearchUserHitOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    tenant_id: uuid.UUID
    tenant_slug: str
    tenant_name: str


class SearchOut(BaseModel):
    tenants: list[SearchTenantHitOut]
    users: list[SearchUserHitOut]
```

Append to `backend/app/services/admin/directory.py` (add `from app.schemas.admin import SearchOut, SearchTenantHitOut, SearchUserHitOut`):

```python
async def search(session: AsyncSession, q: str, *, limit: int = 10) -> SearchOut:
    needle = q.strip()
    like = f"%{escape_like(needle)}%"
    tenant_stmt = select(
        Tenant.id, Tenant.slug, Tenant.display_name, Tenant.industry, Tenant.status
    ).where(Tenant.is_operator.is_(False))
    try:
        tenant_stmt = tenant_stmt.where(Tenant.id == uuid.UUID(needle))
    except ValueError:
        tenant_stmt = tenant_stmt.where(
            or_(
                Tenant.slug.ilike(like, escape="\\"),
                Tenant.display_name.ilike(like, escape="\\"),
            )
        )
    tenants = (await session.execute(tenant_stmt.order_by(Tenant.display_name).limit(limit))).all()
    users = (
        await session.execute(
            select(
                User.id, User.email, User.full_name, User.role,
                Tenant.id.label("tenant_id"), Tenant.slug, Tenant.display_name,
            )
            .join(Tenant, Tenant.id == User.tenant_id)
            .where(Tenant.is_operator.is_(False), User.email.ilike(like, escape="\\"))
            .order_by(User.email)
            .limit(limit)
        )
    ).all()
    return SearchOut(
        tenants=[
            SearchTenantHitOut(
                id=t.id, slug=str(t.slug), display_name=t.display_name,
                industry=t.industry.value, status=t.status.value,
            )
            for t in tenants
        ],
        users=[
            SearchUserHitOut(
                id=u.id, email=str(u.email), full_name=u.full_name, role=u.role.value,
                tenant_id=u.tenant_id, tenant_slug=str(u.slug), tenant_name=u.display_name,
            )
            for u in users
        ],
    )
```

Create `backend/app/routers/admin/search.py`:

```python
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.core.platform_authz import ReadPrincipal
from app.schemas.admin import SearchOut
from app.services.admin import directory
from app.services.admin.audit import record_read_event
from app.services.admin.data_access import platform_read

router = APIRouter(tags=["platform-admin"])


@router.get("/search", response_model=SearchOut)
async def search(
    request: Request,
    principal: ReadPrincipal,
    q: Annotated[str, Query(min_length=2, max_length=200)],
) -> SearchOut:
    db = request.app.state.db
    async with platform_read(db, principal) as session:
        result = await directory.search(session, q)
    # Who looked for whom is itself worth knowing; recorded before returning.
    await record_read_event(db, principal, action="platform.search", target_type="search",
                            detail={"q": q.strip()[:200]})
    return result
```

Append `search` to `ROUTER_MODULES`.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_admin_search.py tests/test_admin_route_guard.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/admin/directory.py backend/app/schemas/admin.py \
  backend/app/routers/admin/search.py backend/app/routers/admin/__init__.py \
  backend/tests/test_admin_search.py
git commit -m "feat(admin): audited global search across tenants and users"
```

---

### Task 2.10: System health

**Files:**
- Create: `backend/app/services/admin/health.py`
- Modify: `backend/app/schemas/admin.py`
- Create: `backend/app/routers/admin/health.py`
- Modify: `backend/app/routers/admin/__init__.py`
- Modify: `backend/app/workers/forecast_worker.py` (`health_check_interval = 60`)
- Test: `backend/tests/test_admin_health.py`

**Interfaces:**
- Produces: `ARQ_HEALTH_KEY = "arq:queue:health-check"`, `ARQ_QUEUE_KEY = "arq:queue"`, `LEADER_KEY = "sanket:leader:background-singletons"`; `async health.check_all(app_state: Any, settings: Settings) -> HealthOut`; schemas `ComponentHealthOut`, `HealthOut`.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_admin_health.py`:

```python
from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from admin_factories import create_platform_admin
from app.config import get_settings

pytestmark = pytest.mark.asyncio


class FakeRedis:
    def __init__(self, *, heartbeat: str | None, depth: int = 0, leader: bool = True) -> None:
        self.values = {"arq:queue:health-check": heartbeat}
        self.depth = depth
        self.leader = leader

    async def ping(self) -> bool:
        return True

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def zcard(self, key: str) -> int:
        return self.depth

    async def exists(self, key: str) -> int:
        return 1 if (key == "sanket:leader:background-singletons" and self.leader) else 0


def _components(body: dict) -> dict:
    return {c["name"]: c for c in body["components"]}


async def test_health_without_redis(client: AsyncClient, db_session: AsyncSession, monkeypatch) -> None:
    ops = await create_platform_admin(db_session, "platform_support")
    monkeypatch.setattr(get_settings(), "ml_api_url", "http://127.0.0.1:9")
    app = client._transport.app  # noqa: SLF001
    app.state.redis = None
    r = await client.get("/api/v1/admin/health", headers=ops.headers)
    assert r.status_code == 200, r.text
    c = _components(r.json())
    assert c["api"]["status"] == "green"
    # The test container connects as a superuser: isolation is NOT enforced,
    # and the console must say so in red rather than report green.
    assert c["database"]["status"] == "red"
    assert "SUPERUSER" in c["database"]["reason"]
    assert c["redis"]["status"] == "yellow"
    assert c["worker"]["status"] == "yellow"
    assert c["ml"]["status"] == "red"
    assert c["mfa"]["status"] == "green"
    assert r.json()["overall"] == "red"


async def test_worker_status_follows_the_heartbeat(client: AsyncClient, db_session: AsyncSession) -> None:
    ops = await create_platform_admin(db_session)
    app = client._transport.app  # noqa: SLF001
    app.state.redis = FakeRedis(heartbeat=None)
    c = _components((await client.get("/api/v1/admin/health", headers=ops.headers)).json())
    assert c["worker"]["status"] == "red"
    assert c["redis"]["status"] == "green"

    app.state.redis = FakeRedis(heartbeat="Sep-10 12:00:00 j_complete=3 j_failed=0 queued=0")
    c = _components((await client.get("/api/v1/admin/health", headers=ops.headers)).json())
    assert c["worker"]["status"] in ("green", "yellow")  # yellow only if stale jobs exist
    assert c["worker"]["detail"]["queue_depth"] == 0

    app.state.redis = FakeRedis(heartbeat="ok", depth=50)
    c = _components((await client.get("/api/v1/admin/health", headers=ops.headers)).json())
    assert c["worker"]["status"] == "yellow"


async def test_mfa_warning_in_production(client: AsyncClient, db_session: AsyncSession, monkeypatch) -> None:
    from app.services.admin.health import _mfa

    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "platform_admin_require_mfa", False)
    assert _mfa(settings).status == "yellow"
    monkeypatch.setattr(settings, "platform_admin_require_mfa", None)
    assert _mfa(settings).status == "green"
```

- [ ] **Step 2: Run to see failures**

Run: `uv run pytest tests/test_admin_health.py -v`
Expected: FAIL — 404 on `/api/v1/admin/health`.

- [ ] **Step 3: Add the schemas**

Append to `backend/app/schemas/admin.py`:

```python
class ComponentHealthOut(BaseModel):
    name: str
    status: str  # green | yellow | red
    reason: str
    latency_ms: float | None = None
    detail: dict = Field(default_factory=dict)


class HealthOut(BaseModel):
    overall: str
    components: list[ComponentHealthOut]
    checked_at: datetime
```

- [ ] **Step 4: Implement the checks**

Create `backend/app/services/admin/health.py`:

```python
"""Operational health, from real checks (spec §8.5). Nothing is assumed:
a component that cannot be checked is reported as such, never as green."""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select

from app.config import Settings
from app.models.integration import IntegrationConnection
from app.models.tenant import Tenant
from app.models.trend import HybridForecastRun
from app.schemas.admin import ComponentHealthOut, HealthOut
from app.services.admin.directory import stale_condition

ARQ_HEALTH_KEY = "arq:queue:health-check"
ARQ_QUEUE_KEY = "arq:queue"
LEADER_KEY = "sanket:leader:background-singletons"
QUEUE_WARN_DEPTH = 20
_RANK = {"green": 0, "yellow": 1, "red": 2}


def _c(name: str, status: str, reason: str, latency: float | None = None, **detail: Any) -> ComponentHealthOut:
    return ComponentHealthOut(name=name, status=status, reason=reason, latency_ms=latency, detail=detail)


def _api(settings: Settings) -> ComponentHealthOut:
    return _c("api", "green", "Responding", version=settings.app_version,
              git_sha=settings.git_sha, environment=settings.app_env)


async def _database(db: Any) -> ComponentHealthOut:
    start = time.perf_counter()
    ok = await db.healthcheck()
    latency = round((time.perf_counter() - start) * 1000, 1)
    if not ok:
        return _c("database", "red", "Database unreachable", latency)
    try:
        problems = await db.tenant_isolation_problems()
    except Exception as exc:  # noqa: BLE001
        return _c("database", "red", f"Could not verify tenant isolation: {exc}", latency)
    migrations_ok = await db.check_migration_version()
    if problems:
        return _c("database", "red", "Tenant isolation NOT enforced: " + "; ".join(problems),
                  latency, migrations_current=migrations_ok)
    if not migrations_ok:
        return _c("database", "yellow", "Schema is behind the latest migration", latency,
                  migrations_current=False)
    if latency > 500:
        return _c("database", "yellow", f"Slow response ({latency} ms)", latency, migrations_current=True)
    return _c("database", "green", "Reachable; RLS enforced; migrations current", latency,
              migrations_current=True)


async def _redis(redis: Any) -> ComponentHealthOut:
    if redis is None:
        return _c("redis", "yellow", "Not configured — rate limits and realtime run in-process")
    start = time.perf_counter()
    try:
        await asyncio.wait_for(redis.ping(), timeout=2)
    except Exception as exc:  # noqa: BLE001
        return _c("redis", "red", f"Ping failed: {exc}")
    return _c("redis", "green", "Ping OK", round((time.perf_counter() - start) * 1000, 1))


async def _ml(http: Any, settings: Settings) -> ComponentHealthOut:
    url = f"{settings.ml_api_url.rstrip('/')}/health"
    start = time.perf_counter()
    try:
        response = await http.get(url, timeout=2.0)
    except Exception as exc:  # noqa: BLE001
        return _c("ml", "red", f"Unreachable: {type(exc).__name__}")
    latency = round((time.perf_counter() - start) * 1000, 1)
    if response.status_code != 200:
        return _c("ml", "red", f"Health endpoint returned {response.status_code}", latency)
    return _c("ml", "green", "Healthy", latency)


async def _stale_jobs(db: Any, now: datetime) -> int:
    async with db.session_no_rls(read_only=True) as session:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(HybridForecastRun)
                .join(Tenant, Tenant.id == HybridForecastRun.tenant_id)
                .where(Tenant.is_operator.is_(False), stale_condition(now))
            )
            or 0
        )


async def _worker(redis: Any, db: Any, now: datetime) -> ComponentHealthOut:
    stale = await _stale_jobs(db, now)
    if redis is None:
        return _c("worker", "yellow",
                  "No Redis — forecast jobs run in-process in the API (not durable)", stale_jobs=stale)
    try:
        heartbeat = await redis.get(ARQ_HEALTH_KEY)
        depth = int(await redis.zcard(ARQ_QUEUE_KEY) or 0)
    except Exception as exc:  # noqa: BLE001
        return _c("worker", "red", f"Could not read the queue: {exc}", stale_jobs=stale)
    if not heartbeat:
        return _c("worker", "red", "No worker heartbeat in the last ~60 s",
                  queue_depth=depth, stale_jobs=stale)
    if depth > QUEUE_WARN_DEPTH or stale:
        return _c("worker", "yellow", f"Queue depth {depth}, {stale} stale job(s)",
                  heartbeat=heartbeat, queue_depth=depth, stale_jobs=stale)
    return _c("worker", "green", "Heartbeat fresh; queue clear",
              heartbeat=heartbeat, queue_depth=depth, stale_jobs=stale)


async def _integrations(redis: Any, db: Any, now: datetime) -> ComponentHealthOut:
    async with db.session_no_rls(read_only=True) as session:
        errors, oldest = (
            await session.execute(
                select(func.count(), func.min(IntegrationConnection.updated_at))
                .join(Tenant, Tenant.id == IntegrationConnection.tenant_id)
                .where(Tenant.is_operator.is_(False), IntegrationConnection.status == "error")
            )
        ).one()
    leader = None
    if redis is not None:
        try:
            leader = bool(await redis.exists(LEADER_KEY))
        except Exception:  # noqa: BLE001
            leader = False
    detail = {"connections_in_error": int(errors), "leader_lease_held": leader}
    if errors and oldest is not None and now - oldest > timedelta(hours=24):
        return _c("integrations", "red", f"{errors} connection(s) in error, oldest over 24 h", **detail)
    if errors:
        return _c("integrations", "yellow", f"{errors} connection(s) in error", **detail)
    if leader is False:
        return _c("integrations", "yellow", "No replica holds the background-sync leader lease", **detail)
    return _c("integrations", "green", "No connection in error", **detail)


def _mfa(settings: Settings) -> ComponentHealthOut:
    if settings.platform_admin_mfa_required:
        return _c("mfa", "green", "Second factor required for the platform console")
    if settings.is_production:
        return _c("mfa", "yellow", "PLATFORM_ADMIN_REQUIRE_MFA is off in production")
    return _c("mfa", "green", "Not required outside production")


async def check_all(app_state: Any, settings: Settings) -> HealthOut:
    now = datetime.now(tz=UTC)
    redis = getattr(app_state, "redis", None)
    db = app_state.db
    components = [
        _api(settings),
        await _database(db),
        await _redis(redis),
        await _ml(app_state.http, settings),
        await _worker(redis, db, now),
        await _integrations(redis, db, now),
        _mfa(settings),
    ]
    overall = max(components, key=lambda c: _RANK[c.status]).status
    return HealthOut(overall=overall, components=components, checked_at=now)
```

Note: this module opens `session_no_rls(read_only=True)` directly instead of `platform_read` because it runs no per-principal queries and reports only counts; it is called only from the admin router behind `ReadPrincipal`.

- [ ] **Step 5: Add the router and the worker heartbeat**

Create `backend/app/routers/admin/health.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Request

from app.config import get_settings
from app.core.platform_authz import ReadPrincipal
from app.schemas.admin import HealthOut
from app.services.admin.health import check_all

router = APIRouter(tags=["platform-admin"])


@router.get("/health", response_model=HealthOut)
async def platform_health(request: Request, principal: ReadPrincipal) -> HealthOut:
    return await check_all(request.app.state, get_settings())
```

Append `health` to `ROUTER_MODULES`.

In `backend/app/workers/forecast_worker.py`, add to `WorkerSettings`:

```python
    # Write arq's health-check key every 60 s (expires after 61 s) so the
    # platform console can tell a live worker from a dead one. arq's default
    # of one hour made the key useless as a liveness signal.
    health_check_interval = 60
```

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/test_admin_health.py tests/test_admin_route_guard.py -v`
Expected: all PASS.

- [ ] **Step 7: Run the full backend suite (end of M2)**

Run: `uv run pytest -q`
Expected: no failures beyond the M0 baseline.

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/admin/health.py backend/app/schemas/admin.py \
  backend/app/routers/admin/health.py backend/app/routers/admin/__init__.py \
  backend/app/workers/forecast_worker.py backend/tests/test_admin_health.py
git commit -m "feat(admin): real component health checks, including RLS enforcement and worker heartbeat"
```

<!-- PLAN-CONTINUES -->
