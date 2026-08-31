# Industry-Scoped Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every SANKET customer tenant exactly one authoritative industry, chosen at workspace creation, inherited by every member, and enforceable on the server so no URL, header or request body can reach another industry.

**Architecture:** `tenants.industry` (renamed from `active_industry`) becomes the single authority, with `tenants.industries` and `users.active_industry` demoted to database-maintained mirrors via CHECK + triggers. A new `core/industry_scope.py` gate is applied at `include_router` registration so endpoint authors inherit it by construction. The token's `ind` claim stays the request-time source and is revoked-and-reminted on the one path that can change it.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 async, Alembic, PostgreSQL 16 with RLS, pytest + testcontainers; React 18 + TypeScript + Zustand + TanStack Query, Vitest + Testing Library, Playwright.

**Spec:** `docs/superpowers/specs/2026-08-31-industry-scoped-workspace-design.md`

## Global Constraints

- Tenant isolation is enforced by PostgreSQL RLS. **Never bypass RLS with a superuser connection in application code.** Migrations are the documented exception and need `MIGRATION_DATABASE_URL`.
- Frontend icons import from `frontend/src/components/ui/icons.tsx` **only** — never from `lucide-react` or `react-iconly` directly.
- **Fail honestly.** No synthetic fallback data standing in for a real signal.
- Never commit live payment keys. Razorpay test keys are `rzp_test_*`.
- Industry codes come from the canonical `app.models.enums.IndustryCode`: `fashion`, `electronics`, `pharma`, `agrocenter`, `hardware`. No separate frontend list.
- Strict TDD: write the failing test, **run it and observe the failure**, then write the minimum code to pass. Production code written without a failing test that demanded it gets deleted.
- Backend tests need Docker running (testcontainers). Verify with `docker info` before starting.
- Backend commands run from `backend/` with `uv run`. Frontend from `frontend/` with `npm`.

---

## File Structure

**Created**
| Path | Responsibility |
|---|---|
| `backend/alembic/versions/0020_industry_scoped_workspace.py` | Rename, snapshot, constrain, triggers, sandbox tenant |
| `backend/app/core/industry_scope.py` | The single industry authorization primitive |
| `backend/app/services/workspace.py` | One tenant-creation path shared by both signup flows |
| `backend/tests/test_industry_scope.py` | Gate unit + endpoint 403 coverage |
| `backend/tests/test_industry_migration.py` | Constraint and trigger behaviour |
| `backend/tests/test_accept_invite.py` | Invite redemption + inheritance |
| `frontend/src/hooks/useTenantIndustry.ts` | Session-derived industry, the only read path |
| `frontend/src/pages/AcceptInvite.tsx` | Invite redemption page |
| `frontend/src/components/auth/IndustryRoute.tsx` | Route guard for industry-specific routes |
| `frontend/src/stores/industry.test.ts` | Store is read-only, no persistence |
| `frontend/src/pages/Login.test.tsx` | Signup requires industry |
| `frontend/e2e/industry-scope.spec.ts` | The required Playwright journey |

**Deleted**
| Path | Reason |
|---|---|
| `backend/app/routers/cross_industry.py` | Cross-industry is unavailable to one-industry tenants |
| `frontend/src/pages/CrossIndustryCorrelation.tsx` | Unrouted dead page for the above |
| `frontend/src/components/layout/IndustrySwitcher.tsx` | No authenticated switching |

**Modified (principal)**
`backend/app/models/tenant.py`, `backend/app/schemas/{auth,tenant,integrations}.py`, `backend/app/routers/{auth,industry_router,invites,integrations,integrations_hub}.py`, `backend/app/routers/industries/*.py`, `backend/app/middleware/tenant_context.py`, `backend/app/core/firebase_auth.py`, `backend/app/main.py`, `backend/tests/conftest.py`, `frontend/src/stores/{auth,industry}.ts`, `frontend/src/api/client.ts`, `frontend/src/App.tsx`, `frontend/src/pages/{Login,LandingPage,Integrations}.tsx`, `frontend/src/pages/onboarding/StepIndustry.tsx`, `frontend/src/components/layout/{TopBar,Sidebar,AppShell}.tsx`.

---

## Phase A — Database foundation

### Task 1: Migration 0020 — one authoritative industry

**Files:**
- Create: `backend/alembic/versions/0020_industry_scoped_workspace.py`
- Create: `backend/tests/test_industry_migration.py`
- Modify: `backend/tests/conftest.py:172-183` (the `test_tenant_id` fixture inserts three industries and will now violate the new CHECK)

**Interfaces:**
- Consumes: nothing
- Produces: column `tenants.industry`; constraint `ck_tenants_single_industry`; triggers `trg_tenants_mirror_industries`, `trg_users_inherit_industry`; tenant slug `sandbox` with user `sandbox@sanket.app`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_industry_migration.py
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_tenant_industries_mirrors_industry(db_session: AsyncSession) -> None:
    """The array column is maintained by the database, not by application code."""
    tenant_id = uuid.uuid4()
    await db_session.execute(
        text(
            """
            INSERT INTO tenants (id, slug, display_name, tier, status, industry)
            VALUES (:id, :slug, 'Mirror Co', 'growth', 'trial', 'pharma')
            """
        ),
        {"id": str(tenant_id), "slug": f"mirror-{tenant_id.hex[:8]}"},
    )
    await db_session.commit()
    row = await db_session.execute(
        text("SELECT industry::text, industries::text[] FROM tenants WHERE id = :id"),
        {"id": str(tenant_id)},
    )
    industry, industries = row.one()
    assert industry == "pharma"
    assert industries == ["pharma"]


async def test_cannot_grant_a_second_industry(db_session: AsyncSession) -> None:
    """A bug cannot re-grant five industries: the trigger overwrites the attempt."""
    tenant_id = uuid.uuid4()
    await db_session.execute(
        text(
            """
            INSERT INTO tenants (id, slug, display_name, tier, status,
                                 industry, industries)
            VALUES (:id, :slug, 'Greedy Co', 'growth', 'trial', 'fashion',
                    ARRAY['fashion','pharma']::industry_code[])
            """
        ),
        {"id": str(tenant_id), "slug": f"greedy-{tenant_id.hex[:8]}"},
    )
    await db_session.commit()
    industries = await db_session.scalar(
        text("SELECT industries::text[] FROM tenants WHERE id = :id"),
        {"id": str(tenant_id)},
    )
    assert industries == ["fashion"]


async def test_user_inherits_tenant_industry(db_session: AsyncSession) -> None:
    """A user row cannot carry an industry that differs from its tenant."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    await db_session.execute(
        text(
            """
            INSERT INTO tenants (id, slug, display_name, tier, status, industry)
            VALUES (:id, :slug, 'Inherit Co', 'growth', 'trial', 'agrocenter')
            """
        ),
        {"id": str(tenant_id), "slug": f"inherit-{tenant_id.hex[:8]}"},
    )
    await db_session.execute(
        text(
            """
            INSERT INTO users (id, tenant_id, email, full_name, role,
                               active_industry, is_active)
            VALUES (:uid, :tid, 'member@inherit.test', 'Member', 'analyst',
                    'pharma', TRUE)
            """
        ),
        {"uid": str(user_id), "tid": str(tenant_id)},
    )
    await db_session.commit()
    active = await db_session.scalar(
        text("SELECT active_industry::text FROM users WHERE id = :id"),
        {"id": str(user_id)},
    )
    assert active == "agrocenter", "stale user industry must never survive a write"


async def test_sandbox_tenant_exists_and_is_single_industry(
    db_session: AsyncSession,
) -> None:
    row = await db_session.execute(
        text("SELECT industry::text, industries::text[] FROM tenants WHERE slug = 'sandbox'")
    )
    industry, industries = row.one()
    assert industry == "fashion"
    assert industries == ["fashion"]


async def test_legacy_industries_are_preserved_not_deleted(
    db_session: AsyncSession,
) -> None:
    """The migration must not destroy the record of prior multi-industry grants."""
    snapshot = await db_session.scalar(
        text("SELECT settings -> 'legacy_industries' FROM tenants WHERE slug = 'sanket-dev'")
    )
    assert snapshot is not None
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd backend && uv run pytest tests/test_industry_migration.py -v
```

Expected: FAIL — `column "industry" of relation "tenants" does not exist`.

- [ ] **Step 3: Write the migration**

```python
# backend/alembic/versions/0020_industry_scoped_workspace.py
"""Industry-scoped workspaces: one authoritative industry per tenant.

`tenants.active_industry` becomes `tenants.industry` -- the single authority.
`tenants.industries` and `users.active_industry` survive as database-maintained
mirrors so no application bug can silently re-grant several industries, and so
existing rows keep working while the columns are retired in a later release.

Non-destructive: each tenant's prior industry array is snapshotted into
`settings['legacy_industries']`, and `industry_profiles` rows for unselected
industries are left in place.

Revision ID: 0020
Revises: 64b00842a1e6
Create Date: 2026-08-31
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0020"
down_revision: str | None = "64b00842a1e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE tenants RENAME COLUMN active_industry TO industry")

    # Preserve the prior grant before rewriting it. Nothing is deleted.
    op.execute(
        """
        UPDATE tenants
        SET settings = jsonb_set(
            COALESCE(settings, '{}'::jsonb),
            '{legacy_industries}',
            to_jsonb(industries::text[]),
            TRUE
        )
        """
    )
    op.execute("UPDATE tenants SET industries = ARRAY[industry]::industry_code[]")
    op.execute(
        """
        ALTER TABLE tenants
        ADD CONSTRAINT ck_tenants_single_industry
        CHECK (industries = ARRAY[industry]::industry_code[])
        """
    )

    # Every existing member inherits the tenant's industry.
    op.execute(
        """
        UPDATE users u
        SET active_industry = t.industry
        FROM tenants t
        WHERE u.tenant_id = t.id AND u.active_industry IS DISTINCT FROM t.industry
        """
    )

    # SECURITY DEFINER: the users trigger reads `tenants`, which RLS would
    # otherwise hide during a cross-tenant insert (signup runs without an RLS
    # tenant context). This is trigger-level privilege created by a migration,
    # not application code opening a superuser connection.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION tenants_mirror_industries()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        AS $$
        BEGIN
            NEW.industries := ARRAY[NEW.industry]::industry_code[];
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_tenants_mirror_industries
        BEFORE INSERT OR UPDATE ON tenants
        FOR EACH ROW EXECUTE FUNCTION tenants_mirror_industries()
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION users_inherit_industry()
        RETURNS TRIGGER
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, public
        AS $$
        DECLARE
            tenant_industry industry_code;
        BEGIN
            SELECT t.industry INTO tenant_industry
            FROM tenants t WHERE t.id = NEW.tenant_id;
            IF tenant_industry IS NOT NULL THEN
                NEW.active_industry := tenant_industry;
            END IF;
            RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_users_inherit_industry
        BEFORE INSERT OR UPDATE ON users
        FOR EACH ROW EXECUTE FUNCTION users_inherit_industry()
        """
    )

    # Dedicated sandbox tenant. The public demo previously signed anonymous
    # visitors into `sanket-dev`, the shared development tenant.
    op.execute(
        """
        INSERT INTO tenants (id, slug, display_name, tier, status, industry,
                             max_skus, max_users, data_retention_days, settings)
        VALUES (gen_random_uuid(), 'sandbox', 'SANKET Sandbox', 'growth',
                'active', 'fashion', 1000, 1, 365, '{}'::jsonb)
        ON CONFLICT (slug) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO users (id, tenant_id, email, password_hash, full_name,
                           role, active_industry, is_active)
        SELECT gen_random_uuid(), id, 'sandbox@sanket.app', NULL,
               'Sandbox Guest', 'viewer', industry, TRUE
        FROM tenants WHERE slug = 'sandbox'
        ON CONFLICT (tenant_id, email) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_users_inherit_industry ON users")
    op.execute("DROP FUNCTION IF EXISTS users_inherit_industry()")
    op.execute("DROP TRIGGER IF EXISTS trg_tenants_mirror_industries ON tenants")
    op.execute("DROP FUNCTION IF EXISTS tenants_mirror_industries()")
    op.execute("ALTER TABLE tenants DROP CONSTRAINT IF EXISTS ck_tenants_single_industry")
    op.execute(
        """
        UPDATE tenants
        SET industries = ARRAY(
            SELECT jsonb_array_elements_text(settings -> 'legacy_industries')
        )::industry_code[]
        WHERE settings ? 'legacy_industries'
        """
    )
    op.execute("UPDATE tenants SET settings = settings - 'legacy_industries'")
    op.execute("ALTER TABLE tenants RENAME COLUMN industry TO active_industry")
    op.execute("DELETE FROM users WHERE email = 'sandbox@sanket.app'")
    op.execute("DELETE FROM tenants WHERE slug = 'sandbox'")
```

- [ ] **Step 4: Update the test fixture that the new constraint invalidates**

`backend/tests/conftest.py:172-183` currently inserts `ARRAY['fashion','electronics','pharma']` with `active_industry='fashion'`. Replace that INSERT with:

```python
    await db_session.execute(
        text(
            """
            INSERT INTO tenants (id, slug, display_name, tier, status, industry)
            VALUES (:id, 'test-tenant', 'Test Tenant', 'enterprise', 'active',
                    'fashion')
            """
        ),
        {"id": str(tenant_id)},
    )
```

Then add a second fixture in the same file so cross-industry tests have a tenant on the other side:

```python
@pytest_asyncio.fixture
async def pharma_tenant_id(db_session: AsyncSession) -> uuid.UUID:
    """A second tenant scoped to pharma — for industry-boundary assertions."""
    result = await db_session.execute(
        text("SELECT id FROM tenants WHERE slug = 'pharma-tenant'")
    )
    row = result.fetchone()
    if row:
        await grant_active_subscription(db_session, row[0])
        return row[0]

    tenant_id = uuid.uuid4()
    await db_session.execute(
        text(
            """
            INSERT INTO tenants (id, slug, display_name, tier, status, industry)
            VALUES (:id, 'pharma-tenant', 'Pharma Tenant', 'enterprise',
                    'active', 'pharma')
            """
        ),
        {"id": str(tenant_id)},
    )
    await db_session.commit()
    await grant_active_subscription(db_session, tenant_id)
    return tenant_id
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd backend && uv run pytest tests/test_industry_migration.py -v
```

Expected: 5 passed.

- [ ] **Step 6: Verify the downgrade round-trips**

```bash
cd backend && uv run alembic downgrade -1 && uv run alembic upgrade head
```

Expected: both succeed with no error. This proves the migration is reversible.

- [ ] **Step 7: Commit**

```bash
git add backend/alembic/versions/0020_industry_scoped_workspace.py backend/tests/test_industry_migration.py backend/tests/conftest.py
git commit -m "feat(db): one authoritative industry per tenant

Renames tenants.active_industry to tenants.industry and demotes
tenants.industries and users.active_industry to database-maintained
mirrors, so no application bug can re-grant several industries.
Snapshots each tenant's prior array into settings.legacy_industries
rather than deleting it, and adds the dedicated sandbox tenant."
```

---

### Task 2: ORM models and schemas follow the database

**Files:**
- Modify: `backend/app/models/tenant.py:38-44` (Tenant), `:79-81` (User)
- Modify: `backend/app/schemas/tenant.py:14-45`
- Test: `backend/tests/test_industry_migration.py` (add)

**Interfaces:**
- Consumes: `tenants.industry` from Task 1
- Produces: `Tenant.industry: Mapped[IndustryCode]`. `Tenant.industries` and `User.active_industry` **no longer exist as ORM attributes.**

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/test_industry_migration.py
async def test_orm_exposes_one_industry_field(db_session: AsyncSession) -> None:
    """Exactly one authoritative field survives on the model."""
    from app.models.tenant import Tenant, User

    assert hasattr(Tenant, "industry")
    assert not hasattr(Tenant, "industries"), "the mirror column must not be an ORM field"
    assert not hasattr(User, "active_industry"), "users must not carry their own industry"
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && uv run pytest tests/test_industry_migration.py::test_orm_exposes_one_industry_field -v
```

Expected: FAIL — `AssertionError: the mirror column must not be an ORM field`.

- [ ] **Step 3: Edit the models**

In `backend/app/models/tenant.py`, delete the `industries` mapped column and replace `active_industry` on `Tenant` with:

```python
    # The workspace's single authoritative industry. Immutable once onboarding
    # completes or real data arrives — see core/industry_scope.py. The legacy
    # `industries` array column still exists in the database as a trigger-
    # maintained mirror and is deliberately absent here: one authority only.
    industry: Mapped[IndustryCode] = mapped_column(
        SAEnum(IndustryCode, name="industry_code"), nullable=False
    )
```

Delete `User.active_industry` entirely — members inherit from the tenant, enforced by `trg_users_inherit_industry`.

In `backend/app/schemas/tenant.py`: on `TenantOut` replace `industries` + `active_industry` with `industry: IndustryCode`; on `UserOut` delete `active_industry`; on `UserCreate` delete `active_industry`.

- [ ] **Step 4: Run the whole backend suite to find every caller**

```bash
cd backend && uv run pytest -x -q
```

Expected: failures in `routers/auth.py`, `routers/industry_router.py`, `workers/whatsapp_digest.py` and their tests — every place that read the removed attributes. This list is the work for Phases D and E; note it and fix only imports/attribute reads that are pure renames (`tenant.active_industry` → `tenant.industry`) in this task. Leave behavioural changes for their own tasks.

- [ ] **Step 5: Run it again**

```bash
cd backend && uv run pytest tests/test_industry_migration.py -v
```

Expected: 6 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/tenant.py backend/app/schemas/tenant.py backend/tests/test_industry_migration.py
git commit -m "refactor(models): single industry field on Tenant, none on User"
```

---

## Phase B — The authorization gate

### Task 3: `industry_scope` — the primitive

**Files:**
- Create: `backend/app/core/industry_scope.py`
- Create: `backend/tests/test_industry_scope.py`

**Interfaces:**
- Consumes: `request.state.industry_code` (set by `TenantContextMiddleware`)
- Produces:
  - `tenant_industry(request: Request) -> IndustryCode`
  - `TenantIndustry = Annotated[IndustryCode, Depends(tenant_industry)]`
  - `require_industry(code: IndustryCode) -> Any` (returns `Depends(...)`, use directly)
  - `assert_industry(requested: str | IndustryCode | None, tenant: IndustryCode) -> IndustryCode`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_industry_scope.py
from __future__ import annotations

import pytest
from fastapi import Request

from app.core.exceptions import PermissionDeniedError, ValidationError
from app.models.enums import IndustryCode


def _request(industry: str | None, tenant_id: str | None = "t") -> Request:
    scope = {"type": "http", "headers": [], "method": "GET", "path": "/"}
    req = Request(scope)
    req.state.tenant_id = tenant_id
    req.state.industry_code = industry
    return req


def test_tenant_industry_reads_the_verified_claim() -> None:
    from app.core.industry_scope import tenant_industry

    assert tenant_industry(_request("pharma")) is IndustryCode.pharma


def test_assert_industry_allows_the_tenants_own() -> None:
    from app.core.industry_scope import assert_industry

    assert assert_industry("pharma", IndustryCode.pharma) is IndustryCode.pharma


def test_assert_industry_defaults_to_the_tenant_when_absent() -> None:
    """An omitted target industry means the tenant's own — never a client choice."""
    from app.core.industry_scope import assert_industry

    assert assert_industry(None, IndustryCode.hardware) is IndustryCode.hardware


def test_assert_industry_rejects_another_industry() -> None:
    from app.core.industry_scope import assert_industry

    with pytest.raises(PermissionDeniedError) as exc:
        assert_industry("fashion", IndustryCode.pharma)
    assert exc.value.status_code == 403


def test_assert_industry_rejects_an_unknown_code() -> None:
    from app.core.industry_scope import assert_industry

    with pytest.raises(ValidationError):
        assert_industry("crypto", IndustryCode.pharma)
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && uv run pytest tests/test_industry_scope.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.core.industry_scope'`.

- [ ] **Step 3: Write the module**

```python
# backend/app/core/industry_scope.py
"""The industry authorization boundary.

Distinct from tenant isolation. RLS answers *whose company data may this user
read*; this module answers *which product modules may this company access*.
They are different questions and must not be conflated -- RLS stays exactly as
it was.

Before this existed the boundary was not enforced at all: every router under
`routers/industries/` accepted an `ActiveIndustry` dependency and then
hardcoded its own `IndustryCode` in the query without comparing the two, so any
authenticated tenant got a 200 from any industry's endpoints.

`require_industry` is applied at `include_router` registration rather than
per-endpoint, mirroring the subscription paywall in `main.py`: a new endpoint
inherits the gate by construction, because its author never writes it.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, Request

from app.core.exceptions import (
    AuthenticationError,
    PermissionDeniedError,
    ValidationError,
)
from app.models.enums import IndustryCode


def tenant_industry(request: Request) -> IndustryCode:
    """The calling tenant's one authoritative industry.

    Read from the verified token claim populated by ``TenantContextMiddleware``.
    The claim is minted from ``tenants.industry`` at every provisioning path and
    cannot drift once the industry locks, because nothing can change it then.
    """
    if getattr(request.state, "tenant_id", None) is None:
        raise AuthenticationError()
    code = getattr(request.state, "industry_code", None)
    if code is None:
        raise AuthenticationError("Industry context missing from token")
    try:
        return IndustryCode(code)
    except ValueError:
        raise AuthenticationError("Industry context missing from token") from None


TenantIndustry = Annotated[IndustryCode, Depends(tenant_industry)]


def require_industry(code: IndustryCode) -> Any:
    """Dependency: this router serves only tenants scoped to ``code``.

    Already returns ``Depends(...)`` -- pass it straight into
    ``include_router(dependencies=...)``, do NOT wrap it again.
    """

    def _check(request: Request) -> None:
        if tenant_industry(request) is not code:
            raise PermissionDeniedError(
                f"This workspace is not configured for the {code.value} industry"
            )

    return Depends(_check)


def assert_industry(
    requested: str | IndustryCode | None, tenant: IndustryCode
) -> IndustryCode:
    """Resolve a client-supplied industry against the tenant's own.

    ``None`` means "the tenant's" -- the only correct default, since a client
    may never choose. Any other value must match, or it is a 403: an old client
    posting a mismatched ``target_industry`` is refused, not silently coerced.
    """
    if requested is None:
        return tenant
    try:
        value = IndustryCode(requested)
    except ValueError:
        raise ValidationError(f"Unknown industry code: {requested}") from None
    if value is not tenant:
        raise PermissionDeniedError(
            f"This workspace is not configured for the {value.value} industry"
        )
    return tenant
```

- [ ] **Step 4: Run it to verify it passes**

```bash
cd backend && uv run pytest tests/test_industry_scope.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/industry_scope.py backend/tests/test_industry_scope.py
git commit -m "feat(authz): add the industry authorization primitive"
```

---

### Task 4: Every industry router refuses other industries

**Files:**
- Modify: `backend/app/main.py:450-454`
- Test: `backend/tests/test_industry_scope.py` (append)

**Interfaces:**
- Consumes: `require_industry` from Task 3
- Produces: 403 from `/api/v1/{other_industry}/*` for every tenant not scoped to it

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/test_industry_scope.py
import uuid

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.firebase_auth import get_verifier

pytestmark = pytest.mark.asyncio


async def _token(db: AsyncSession, tenant_id: uuid.UUID, industry: str) -> str:
    user_id = uuid.uuid4()
    await db.execute(
        text(
            """
            INSERT INTO users (id, tenant_id, email, full_name, role,
                               active_industry, is_active)
            VALUES (:uid, :tid, :email, 'Scope User', 'admin', :ind, TRUE)
            """
        ),
        {
            "uid": str(user_id),
            "tid": str(tenant_id),
            "email": f"scope-{user_id.hex[:8]}@test.com",
            "ind": industry,
        },
    )
    await db.commit()
    token, _ = get_verifier().mint_dev_token(
        uid=str(user_id),
        puid=str(user_id),
        email=f"scope-{user_id.hex[:8]}@test.com",
        tid=str(tenant_id),
        role="admin",
        ind=industry,
    )
    return token


async def test_own_industry_endpoint_succeeds(
    client: AsyncClient, db_session: AsyncSession, test_tenant_id: uuid.UUID
) -> None:
    token = await _token(db_session, test_tenant_id, "fashion")
    r = await client.get(
        "/api/v1/fashion/overview", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200, r.text


async def test_other_industry_endpoint_is_forbidden(
    client: AsyncClient, db_session: AsyncSession, test_tenant_id: uuid.UUID
) -> None:
    """Direct API access to another industry fails even with a valid token."""
    token = await _token(db_session, test_tenant_id, "fashion")
    for path in ("/api/v1/pharma/overview", "/api/v1/electronics/overview",
                 "/api/v1/agrocenter/overview", "/api/v1/hardware/overview"):
        r = await client.get(path, headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 403, f"{path} returned {r.status_code}"


async def test_cross_industry_endpoint_is_gone(
    client: AsyncClient, db_session: AsyncSession, test_tenant_id: uuid.UUID
) -> None:
    """Cross-industry correlation is unavailable to ordinary customer tenants."""
    token = await _token(db_session, test_tenant_id, "fashion")
    r = await client.get(
        "/api/v1/alerts/cross-industry", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 404
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && uv run pytest tests/test_industry_scope.py -k "endpoint or cross_industry" -v
```

Expected: `test_other_industry_endpoint_is_forbidden` FAILS with `200 != 403` — this is the security hole the spec names. `test_cross_industry_endpoint_is_gone` FAILS with 200.

- [ ] **Step 3: Apply the gate and delete the cross-industry router**

In `backend/app/main.py`, replace lines 450-454 with:

```python
    # Industry scope is a *different* boundary from tenant isolation: RLS says
    # whose data, this says which modules. Applied here, not per-endpoint, so a
    # new industry endpoint inherits it by construction.
    app.include_router(
        fashion_router, prefix=api_prefix,
        dependencies=gated + [require_industry(IndustryCode.fashion)],
    )
    app.include_router(
        electronics_router, prefix=api_prefix,
        dependencies=gated + [require_industry(IndustryCode.electronics)],
    )
    app.include_router(
        pharma_router, prefix=api_prefix,
        dependencies=gated + [require_industry(IndustryCode.pharma)],
    )
    app.include_router(
        agrocenter_router, prefix=api_prefix,
        dependencies=gated + [require_industry(IndustryCode.agrocenter)],
    )
    app.include_router(
        hardware_router, prefix=api_prefix,
        dependencies=gated + [require_industry(IndustryCode.hardware)],
    )
```

Add the imports `from app.core.industry_scope import require_industry` and `from app.models.enums import IndustryCode` alongside the other router imports.

Delete the `cross_industry_router` import and its `include_router` call (lines 463-465), then:

```bash
git rm backend/app/routers/cross_industry.py frontend/src/pages/CrossIndustryCorrelation.tsx
```

- [ ] **Step 4: Run it to verify it passes**

```bash
cd backend && uv run pytest tests/test_industry_scope.py -v
```

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add -A backend/app/main.py backend/tests/test_industry_scope.py backend/app/routers/cross_industry.py frontend/src/pages/CrossIndustryCorrelation.tsx
git commit -m "feat(authz): 403 on every other industry's endpoints

Applied at include_router so a new endpoint inherits the gate rather
than relying on its author to remember. Removes cross-industry
correlation, which cannot be offered to a one-industry tenant."
```

---

### Task 5: `X-Industry-Code` can no longer switch

**Files:**
- Modify: `backend/app/middleware/tenant_context.py:104-140`
- Test: `backend/tests/test_industry_scope.py` (append)

**Interfaces:**
- Consumes: nothing new
- Produces: middleware sets `request.state.industry_code` from the token only

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/test_industry_scope.py
async def test_industry_header_cannot_switch_industry(
    client: AsyncClient, db_session: AsyncSession, test_tenant_id: uuid.UUID
) -> None:
    """An old client sending another industry is refused, not obeyed."""
    token = await _token(db_session, test_tenant_id, "fashion")
    r = await client.get(
        "/api/v1/industry/context",
        headers={"Authorization": f"Bearer {token}", "X-Industry-Code": "pharma"},
    )
    assert r.status_code == 403


async def test_industry_header_matching_the_tenant_is_accepted(
    client: AsyncClient, db_session: AsyncSession, test_tenant_id: uuid.UUID
) -> None:
    token = await _token(db_session, test_tenant_id, "fashion")
    r = await client.get(
        "/api/v1/industry/context",
        headers={"Authorization": f"Bearer {token}", "X-Industry-Code": "fashion"},
    )
    assert r.status_code == 200
    assert r.json()["code"] == "fashion"


async def test_unknown_industry_header_is_a_bad_request(
    client: AsyncClient, db_session: AsyncSession, test_tenant_id: uuid.UUID
) -> None:
    token = await _token(db_session, test_tenant_id, "fashion")
    r = await client.get(
        "/api/v1/industry/context",
        headers={"Authorization": f"Bearer {token}", "X-Industry-Code": "crypto"},
    )
    assert r.status_code == 400
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && uv run pytest tests/test_industry_scope.py -k header -v
```

Expected: `test_industry_header_cannot_switch_industry` FAILS with 200 — the middleware currently honours the switch because signup grants all five industries.

- [ ] **Step 3: Replace the switching block**

In `backend/app/middleware/tenant_context.py`, delete the `allowed_industries = identity.get("industries")` line and replace the whole `if override:` block with:

```python
        # A workspace is scoped to exactly one industry, so this header can no
        # longer select anything: it may only agree with the token. Kept as a
        # deny rather than an ignore so an old client that still sends another
        # industry fails loudly instead of silently reading the wrong module.
        override = request.headers.get("X-Industry-Code")
        if override:
            try:
                requested = IndustryCode(override).value
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={"detail": f"Unknown industry code: {override}"},
                    headers={"X-Request-ID": request_id},
                )
            if requested != industry_code:
                log.warning(
                    "auth.industry_switch.denied",
                    requested=requested,
                    tenant_industry=industry_code,
                )
                return JSONResponse(
                    status_code=403,
                    content={
                        "detail": f"This workspace is not configured for the "
                                  f"{requested} industry"
                    },
                    headers={"X-Request-ID": request_id},
                )
```

- [ ] **Step 4: Run it to verify it passes**

```bash
cd backend && uv run pytest tests/test_industry_scope.py -v
```

Expected: 11 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app/middleware/tenant_context.py backend/tests/test_industry_scope.py
git commit -m "feat(authz): X-Industry-Code may agree with the token, never override it"
```

---

## Phase C — Authentication and provisioning

### Task 6: Tokens carry one industry

**Files:**
- Modify: `backend/app/core/firebase_auth.py:254-341`
- Modify: `backend/app/scripts/seed_firebase_users.py:52-73`
- Test: `backend/tests/test_firebase_auth.py` (modify existing industries assertions)

**Interfaces:**
- Consumes: nothing
- Produces: `mint_dev_token(*, uid, puid, email, tid, role, ind) -> tuple[str, int]` and `set_user_claims(uid, *, puid, tid, role, ind) -> None` — **the `industries` parameter is removed from both.**

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/test_firebase_auth.py
def test_dev_token_carries_no_industries_claim() -> None:
    """A workspace has one industry, so a plural claim cannot exist to be trusted."""
    import base64
    import json

    from app.core.firebase_auth import get_verifier

    token, _ = get_verifier().mint_dev_token(
        uid="u", puid="u", email="a@b.c", tid="t", role="admin", ind="pharma"
    )
    payload_b64 = token.split(".")[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    payload = json.loads(base64.urlsafe_b64decode(payload_b64))
    assert payload["ind"] == "pharma"
    assert "industries" not in payload
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && uv run pytest tests/test_firebase_auth.py::test_dev_token_carries_no_industries_claim -v
```

Expected: FAIL — `TypeError` on the missing `industries` kwarg, or the key is present.

- [ ] **Step 3: Remove the plural claim**

In `backend/app/core/firebase_auth.py`:
- `mint_dev_token`: delete the `industries: list[str] | None = None` parameter and the `if industries: payload["industries"] = industries` lines.
- `set_user_claims`: delete the `industries` parameter and the `if industries: claims["industries"] = industries` lines.
- `_normalize`: delete the `industries = decoded.get("industries")` block that copies it onto the identity.
- Update the module docstring at line 58 which documents `industries`.

In `backend/app/scripts/seed_firebase_users.py`, delete the tenant preload for the industries claim (lines 52-57) and the `industries=industries` argument, and change `ind=user.active_industry.value` to read the tenant's industry.

- [ ] **Step 4: Run it to verify it passes**

```bash
cd backend && uv run pytest tests/test_firebase_auth.py -v
```

Expected: all pass. Any existing test asserting an `industries` claim must be updated to assert its absence — that is the point of the change, not a regression.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/firebase_auth.py backend/app/scripts/seed_firebase_users.py backend/tests/test_firebase_auth.py
git commit -m "feat(auth): drop the multi-industry claim from every token"
```

---

### Task 7: One tenant-creation path, industry required

**Files:**
- Create: `backend/app/services/workspace.py`
- Modify: `backend/app/schemas/auth.py:66-90`
- Modify: `backend/app/routers/auth.py:493-635` (signup), `:637-813` (google_signup)
- Test: `backend/tests/test_auth.py` (append)

**Interfaces:**
- Consumes: `Tenant.industry` from Task 2
- Produces: `create_tenant(session, *, slug: str, display_name: str, industry: IndustryCode) -> Tenant` in `app.services.workspace`; `SignUpRequest.industry: IndustryCode`; `GoogleSignUpRequest.industry: IndustryCode`

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/test_auth.py
async def test_signup_requires_an_industry(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Acme Owner",
            "email": "owner@acme-fashion.test",
            "password": "Sup3rSecret!",
            "tenant_slug": "acme-fashion",
        },
    )
    assert r.status_code == 422, "industry must be required, not defaulted"


async def test_signup_rejects_an_invalid_industry(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Acme Owner",
            "email": "owner2@acme.test",
            "password": "Sup3rSecret!",
            "tenant_slug": "acme-bogus",
            "industry": "crypto",
        },
    )
    assert r.status_code == 422


async def test_signup_creates_a_tenant_with_exactly_that_industry(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    r = await client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Acme Owner",
            "email": "owner@acme-pharma.test",
            "password": "Sup3rSecret!",
            "tenant_slug": "acme-pharma",
            "industry": "pharma",
        },
    )
    assert r.status_code == 201, r.text
    row = await db_session.execute(
        text(
            "SELECT industry::text, industries::text[] FROM tenants "
            "WHERE slug = 'acme-pharma'"
        )
    )
    industry, industries = row.one()
    assert industry == "pharma"
    assert industries == ["pharma"], "a new workspace must not get every industry"


async def test_signup_owner_inherits_the_tenant_industry(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Hardware Owner",
            "email": "owner@acme-hw.test",
            "password": "Sup3rSecret!",
            "tenant_slug": "acme-hw",
            "industry": "hardware",
        },
    )
    active = await db_session.scalar(
        text("SELECT active_industry::text FROM users WHERE email = 'owner@acme-hw.test'")
    )
    assert active == "hardware"


async def test_signup_seeds_one_industry_profile(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Agro Owner",
            "email": "owner@acme-agro.test",
            "password": "Sup3rSecret!",
            "tenant_slug": "acme-agro",
            "industry": "agrocenter",
        },
    )
    count = await db_session.scalar(
        text(
            "SELECT count(*) FROM industry_profiles p JOIN tenants t ON t.id = p.tenant_id "
            "WHERE t.slug = 'acme-agro'"
        )
    )
    assert count == 1


async def test_signup_still_refuses_to_join_an_existing_workspace(
    client: AsyncClient, test_tenant_id: uuid.UUID
) -> None:
    """Public signup must never let someone into an existing workspace."""
    r = await client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Intruder",
            "email": "intruder@test.com",
            "password": "Sup3rSecret!",
            "tenant_slug": "test-tenant",
            "industry": "fashion",
        },
    )
    assert r.status_code == 409
```

- [ ] **Step 2: Run them to verify they fail**

```bash
cd backend && uv run pytest tests/test_auth.py -k signup -v
```

Expected: the first two FAIL with 201/500 instead of 422; the industry assertions FAIL because signup hardcodes all five industries.

- [ ] **Step 3: Write the shared creation service**

```python
# backend/app/services/workspace.py
"""Workspace (tenant) creation.

One path, used by every self-service signup flow. Previously both
`/auth/signup` and `/auth/google-signup` carried their own 60-line copy of this
logic -- including the identical five-industry grant and the identical feature
flag table -- so a fix to one silently missed the other.

A workspace is created with exactly one industry. There is no path here that
grants more than one.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import IndustryCode, TenantStatus, TenantTier
from app.models.industry import IndustryProfile
from app.models.tenant import Tenant
from app.schemas.onboarding import default_onboarding_state

INDUSTRY_FEATURE_FLAGS: dict[str, dict[str, bool]] = {
    "fashion": {"markdown_optimizer": True, "assortment_planning": True},
    "electronics": {"component_risk": True, "competitor_tracking": True},
    "pharma": {"gxp_mode": True, "shortage_alerts": True, "batch_tracking": True},
    "agrocenter": {
        "seasonal_replenishment": True,
        "weather_signals": True,
        "input_coverage": True,
    },
    "hardware": {
        "supply_risk": True,
        "competitor_tracking": True,
        "safety_stock_optimizer": True,
    },
}


async def create_tenant(
    session: AsyncSession,
    *,
    slug: str,
    display_name: str,
    industry: IndustryCode,
) -> Tenant:
    """Create a workspace scoped to exactly one industry, plus its profile.

    The caller is responsible for having already rejected a duplicate slug --
    self-service signup must never join an existing workspace.
    """
    tenant = Tenant(
        id=uuid.uuid4(),
        slug=slug,
        display_name=display_name,
        tier=TenantTier.growth,
        status=TenantStatus.trial,
        industry=industry,
        max_skus=10000,
        max_users=5,
        data_retention_days=730,
        # Seed setup readiness so the SPA routes the first user into the
        # onboarding wizard. Legacy tenants (no key) stay implicitly done.
        settings={"onboarding": default_onboarding_state().model_dump(mode="json")},
    )
    session.add(tenant)
    await session.flush()

    session.add(
        IndustryProfile(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            industry=industry,
            custom_horizon_weeks=None,
            custom_signal_types=[],
            model_overrides={},
            feature_flags=INDUSTRY_FEATURE_FLAGS.get(industry.value, {}),
        )
    )
    await session.flush()
    return tenant
```

- [ ] **Step 4: Require the industry on both signup schemas**

In `backend/app/schemas/auth.py` add to `SignUpRequest` and `GoogleSignUpRequest`:

```python
    industry: IndustryCode = Field(
        description="The workspace's single industry. Chosen once, at creation; "
        "every member inherits it and it locks when setup completes."
    )
```

with `from app.models.enums import IndustryCode` at the top.

- [ ] **Step 5: Rewrite both signup handlers to use the service**

In `backend/app/routers/auth.py`, in `signup` replace the whole `tenant_row = Tenant(...)` block *and* the five-profile seeding loop with:

```python
        tenant_row = await create_tenant(
            db_session,
            slug=body.tenant_slug,
            display_name=body.tenant_slug.capitalize(),
            industry=body.industry,
        )
```

and drop `active_industry=IndustryCode.fashion` from the `User(...)` construction — the trigger sets it. Change the claim sync to `ind=tenant_row.industry.value` with no `industries=`.

Apply the identical change in `google_signup`, with `display_name=body.workspace_slug.replace("-", " ").title()`, and return `SessionInfo(..., active_industry=tenant_row.industry.value, ...)`.

Import `from app.services.workspace import create_tenant`.

- [ ] **Step 6: Run them to verify they pass**

```bash
cd backend && uv run pytest tests/test_auth.py -v
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/workspace.py backend/app/schemas/auth.py backend/app/routers/auth.py backend/tests/test_auth.py
git commit -m "feat(auth): signup requires one industry and grants only that one

Both signup paths shared a copy-pasted five-industry grant; they now
share a single create_tenant service that cannot grant more than one."
```

---

### Task 8: Sessions serve the tenant's industry, never the user's

**Files:**
- Modify: `backend/app/routers/auth.py:87-243` (session), `:243-340` (dev_login), `:340-470` (sandbox_session)
- Modify: `backend/app/config.py:114-115` (sandbox tenant slug/email)
- Test: `backend/tests/test_auth.py` (append)

**Interfaces:**
- Consumes: `create_tenant`, `Tenant.industry`
- Produces: `SessionInfo.active_industry` always equals `tenants.industry`

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/test_auth.py
async def test_stale_user_industry_cannot_override_the_tenant(
    client: AsyncClient, db_session: AsyncSession, pharma_tenant_id: uuid.UUID
) -> None:
    """Even a hand-written stale user row must not change what the session serves."""
    await _seed_user(db_session, pharma_tenant_id, "member@pharma.test", "Sup3rSecret!")
    # Force a stale value past the trigger, simulating a pre-migration row.
    await db_session.execute(
        text("ALTER TABLE users DISABLE TRIGGER trg_users_inherit_industry")
    )
    await db_session.execute(
        text("UPDATE users SET active_industry = 'fashion' WHERE email = :e"),
        {"e": "member@pharma.test"},
    )
    await db_session.execute(
        text("ALTER TABLE users ENABLE TRIGGER trg_users_inherit_industry")
    )
    await db_session.commit()

    r = await client.post(
        "/api/v1/auth/dev-login",
        json={
            "email": "member@pharma.test",
            "password": "Sup3rSecret!",
            "tenant_slug": "pharma-tenant",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["active_industry"] == "pharma", "the tenant is authoritative"


async def test_sandbox_session_is_scoped_to_the_sandbox_tenant(
    client: AsyncClient,
) -> None:
    """The public demo must not sign visitors into the development tenant."""
    r = await client.post("/api/v1/auth/sandbox-session")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["active_industry"] == "fashion"
    assert body["role"] == "viewer"
```

- [ ] **Step 2: Run them to verify they fail**

```bash
cd backend && uv run pytest tests/test_auth.py -k "stale or sandbox" -v
```

Expected: the stale test FAILS returning `fashion`; the sandbox test FAILS because the configured slug is still `sanket-dev`.

- [ ] **Step 3: Make the tenant authoritative everywhere**

In `backend/app/routers/auth.py`, in all three handlers replace every `user_row.active_industry.value` with `tenant_row.industry.value`, drop each `industries = [...]` list-comprehension and every `industries=` argument, and change the `claims_stale` comparison to `str(identity.get("ind")) != tenant_row.industry.value` with the `token_industries_set` clause deleted. Audit calls become `industry=tenant_row.industry`. Delete `active_industry=IndustryCode.fashion` from the non-production auto-provision `User(...)`.

In `backend/app/config.py` change the sandbox defaults:

```python
    sandbox_tenant_slug: str = "sandbox"
    sandbox_email: str = "sandbox@sanket.app"
```

- [ ] **Step 4: Run the auth suite**

```bash
cd backend && uv run pytest tests/test_auth.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/auth.py backend/app/config.py backend/tests/test_auth.py
git commit -m "feat(auth): every session serves the tenant's industry

Also moves the public sandbox off sanket-dev, the shared development
tenant that anonymous visitors were being signed into."
```

---

### Task 9: The industry locks

**Files:**
- Modify: `backend/app/routers/industry_router.py:166-269` (`activate_industry`), `:84-95` (`list_available_industries`)
- Modify: `backend/app/middleware/tenant_context.py:20-50` (`_PUBLIC_PATHS`)
- Test: `backend/tests/test_industry_scope.py` (append)

**Interfaces:**
- Consumes: `TenantIndustry`
- Produces: `POST /industry/activate` → 200 while unlocked, 409 once locked; public `GET /industry/catalog`; `GET /industry/available` deleted

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/test_industry_scope.py
async def test_industry_catalog_is_public(client: AsyncClient) -> None:
    """The signup form needs the canonical list before anyone has a token."""
    r = await client.get("/api/v1/industry/catalog")
    assert r.status_code == 200, r.text
    assert set(r.json()) == {
        "fashion", "electronics", "pharma", "agrocenter", "hardware"
    }


async def test_authenticated_industry_enumeration_is_gone(
    client: AsyncClient, db_session: AsyncSession, test_tenant_id: uuid.UUID
) -> None:
    token = await _token(db_session, test_tenant_id, "fashion")
    r = await client.get(
        "/api/v1/industry/available", headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 404


async def test_industry_can_be_corrected_during_onboarding(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Mistake Owner", "email": "owner@mistake.test",
            "password": "Sup3rSecret!", "tenant_slug": "mistake-co",
            "industry": "fashion",
        },
    )
    login = await client.post(
        "/api/v1/auth/dev-login",
        json={
            "email": "owner@mistake.test", "password": "Sup3rSecret!",
            "tenant_slug": "mistake-co",
        },
    )
    token = login.json()["access_token"]
    r = await client.post(
        "/api/v1/industry/activate",
        json={"code": "pharma"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    industry = await db_session.scalar(
        text("SELECT industry::text FROM tenants WHERE slug = 'mistake-co'")
    )
    assert industry == "pharma"


async def test_industry_is_locked_once_onboarding_completes(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await client.post(
        "/api/v1/auth/signup",
        json={
            "name": "Locked Owner", "email": "owner@locked.test",
            "password": "Sup3rSecret!", "tenant_slug": "locked-co",
            "industry": "fashion",
        },
    )
    await db_session.execute(
        text(
            "UPDATE tenants SET settings = jsonb_set(settings, '{onboarding,status}', "
            "'\"complete\"') WHERE slug = 'locked-co'"
        )
    )
    await db_session.commit()
    login = await client.post(
        "/api/v1/auth/dev-login",
        json={
            "email": "owner@locked.test", "password": "Sup3rSecret!",
            "tenant_slug": "locked-co",
        },
    )
    r = await client.post(
        "/api/v1/industry/activate",
        json={"code": "pharma"},
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert r.status_code == 409, "a completed workspace's industry is fixed"
```

- [ ] **Step 2: Run them to verify they fail**

```bash
cd backend && uv run pytest tests/test_industry_scope.py -k "catalog or available or corrected or locked" -v
```

Expected: catalog FAILS 404; available FAILS 200; locked FAILS 200 instead of 409.

- [ ] **Step 3: Implement the lock and the catalog**

In `backend/app/routers/industry_router.py` replace `list_available_industries` with:

```python
@router.get("/industry/catalog")
async def industry_catalog() -> dict:
    """Every industry SANKET supports — public, because the signup form needs it
    before the caller has a token, and public prospects may browse all verticals.

    Authenticated users never enumerate industries: they have exactly one.
    """
    return {
        code: {
            "display_name": ctx.display_name,
            "default_horizon_weeks": ctx.default_horizon_weeks,
            "audit_level": ctx.audit_level,
        }
        for code, ctx in INDUSTRY_REGISTRY.items()
    }
```

Add `"/api/v1/industry/catalog"` to `_PUBLIC_PATHS` in `tenant_context.py`.

Replace the body of `activate_industry` with a lock check ahead of the write, and rewrite its docstring — the old one documents switching, which no longer exists:

```python
async def _industry_is_locked(session, tenant: Tenant) -> str | None:
    """Return the reason the industry is locked, or None while it may be fixed.

    Read from the database, never from a token claim: a claim describes what was
    true when it was minted, and lock state is exactly the thing that changes.
    """
    state = load_onboarding_state(tenant.settings)
    if state.status == "complete":
        return "setup is complete"
    for table in ("products", "skus", "historical_sales", "integration_connections"):
        exists = await session.scalar(
            text(f"SELECT 1 FROM {table} WHERE tenant_id = :tid LIMIT 1"),
            {"tid": str(tenant.id)},
        )
        if exists:
            return "this workspace already holds data"
    return None
```

In the handler, after loading the tenant:

```python
        locked = await _industry_is_locked(session, tenant)
        if locked is not None:
            raise ConflictError(
                f"This workspace is set to {tenant.industry.value} and cannot be "
                f"changed because {locked}. Contact support to migrate."
            )
        tenant.industry = body.code
        await session.flush()
```

Delete the `licensed`/`IndustryNotEnabledError` check (there is no licensed list any more) and the `user.active_industry` write (the trigger owns it). After the session block, keep the dev-token re-mint without `industries=`, and add Firebase claim resync plus revocation:

```python
    if settings.firebase_enabled and firebase_uid:
        await run_in_threadpool(
            get_verifier().set_user_claims,
            firebase_uid,
            puid=str(user_id), tid=str(tenant_id), role=user_role, ind=code,
        )
        # The old ID token keeps its previous `ind` for up to an hour. Revoke so
        # the superseded industry cannot be replayed for the rest of that life.
        await run_in_threadpool(get_verifier().revoke_refresh_tokens, firebase_uid)
```

- [ ] **Step 4: Run them to verify they pass**

```bash
cd backend && uv run pytest tests/test_industry_scope.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/industry_router.py backend/app/middleware/tenant_context.py backend/tests/test_industry_scope.py
git commit -m "feat(authz): industry is correctable during setup, then locked

Lock state is read from the database, never a token claim -- a claim
describes what was true when minted, and this is the thing that changes."
```

---

### Task 10: Invite acceptance, inheriting the industry

**Files:**
- Modify: `backend/app/routers/auth.py` (append handler), `backend/app/schemas/auth.py` (append schema)
- Modify: `backend/app/middleware/tenant_context.py:20-50` (`_PUBLIC_PATHS`)
- Create: `backend/tests/test_accept_invite.py`

**Interfaces:**
- Consumes: `Invite`, `InviteStatus`, `create_tenant` (not used), `hash_password`
- Produces: `POST /api/v1/auth/accept-invite` taking `{token, name, password}` → `SessionInfo`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_accept_invite.py
from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _owner_token(client: AsyncClient, slug: str, industry: str) -> str:
    await client.post(
        "/api/v1/auth/signup",
        json={
            "name": f"{slug} Owner", "email": f"owner@{slug}.test",
            "password": "Sup3rSecret!", "tenant_slug": slug, "industry": industry,
        },
    )
    r = await client.post(
        "/api/v1/auth/dev-login",
        json={
            "email": f"owner@{slug}.test", "password": "Sup3rSecret!",
            "tenant_slug": slug,
        },
    )
    return r.json()["access_token"]


async def test_invite_offers_no_industry_choice(client: AsyncClient) -> None:
    """An inviter cannot place a teammate in a different industry."""
    from app.schemas.invite import InviteCreate

    assert "industry" not in InviteCreate.model_fields


async def test_accepted_invite_inherits_the_tenant_industry(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    token = await _owner_token(client, "invite-pharma", "pharma")
    created = await client.post(
        "/api/v1/invites",
        json={"email": "teammate@invite.test", "role": "analyst"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert created.status_code == 201, created.text
    raw = created.json()["invite_url"].split("token=")[1]

    r = await client.post(
        "/api/v1/auth/accept-invite",
        json={"token": raw, "name": "Team Mate", "password": "An0therSecret!"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["active_industry"] == "pharma", "members inherit, never choose"
    assert body["role"] == "analyst"

    active = await db_session.scalar(
        text("SELECT active_industry::text FROM users WHERE email = 'teammate@invite.test'")
    )
    assert active == "pharma"


async def test_invite_token_is_single_use(client: AsyncClient) -> None:
    token = await _owner_token(client, "invite-once", "fashion")
    created = await client.post(
        "/api/v1/invites",
        json={"email": "once@invite.test", "role": "viewer"},
        headers={"Authorization": f"Bearer {token}"},
    )
    raw = created.json()["invite_url"].split("token=")[1]
    body = {"token": raw, "name": "Once", "password": "An0therSecret!"}
    assert (await client.post("/api/v1/auth/accept-invite", json=body)).status_code == 201
    assert (await client.post("/api/v1/auth/accept-invite", json=body)).status_code == 404


async def test_unknown_invite_token_is_rejected(client: AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/accept-invite",
        json={"token": "not-a-real-token", "name": "X", "password": "An0therSecret!"},
    )
    assert r.status_code == 404
```

- [ ] **Step 2: Run them to verify they fail**

```bash
cd backend && uv run pytest tests/test_accept_invite.py -v
```

Expected: FAIL with 404 on `/api/v1/auth/accept-invite` — the endpoint does not exist. `invites.py:14` says acceptance was never built.

- [ ] **Step 3: Add the schema**

```python
# backend/app/schemas/auth.py
class AcceptInviteRequest(BaseModel):
    """Redeem a one-time invite link.

    Deliberately accepts no tenant, no role and no industry: all three come from
    the invite record, which an owner/admin created. A client that could name
    its own role or industry would be an obvious privilege-escalation path.
    """

    token: str = Field(min_length=16, max_length=256)
    name: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=8, max_length=128)
```

- [ ] **Step 4: Add the handler**

```python
# backend/app/routers/auth.py
@router.post("/accept-invite", response_model=SessionInfo, status_code=201)
async def accept_invite(
    body: AcceptInviteRequest, request: Request, settings: SettingsDep
) -> SessionInfo:
    """Redeem an invite and join its workspace.

    Public because the invitee has no bearer yet. Everything that decides
    privilege -- tenant, role, industry -- is read from the invite row, never
    from the request.
    """
    import hashlib

    token_hash = hashlib.sha256(body.token.encode("utf-8")).hexdigest()
    db = request.app.state.db
    async with db.session_no_rls() as db_session:
        invite = await db_session.scalar(
            select(Invite).where(
                Invite.token_hash == token_hash,
                Invite.status == InviteStatus.pending,
            )
        )
        if invite is None:
            raise NotFoundError("Invite")
        if invite.expires_at <= datetime.now(tz=UTC):
            raise NotFoundError("Invite")

        tenant_row = await db_session.get(Tenant, invite.tenant_id)
        if tenant_row is None or tenant_row.status == TenantStatus.suspended:
            raise NotFoundError("Invite")

        existing = await db_session.scalar(
            select(User).where(
                User.tenant_id == invite.tenant_id, User.email == invite.email
            )
        )
        if existing is not None:
            raise ConflictError("That invitation has already been used")

        seat_count = await db_session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.tenant_id == invite.tenant_id, User.is_active.is_(True))
        )
        if int(seat_count or 0) >= tenant_row.max_users:
            raise ConflictError("This workspace has no seats available")

        user_row = User(
            id=uuid.uuid4(),
            tenant_id=invite.tenant_id,
            email=invite.email,
            password_hash=hash_password(body.password, settings),
            full_name=body.name,
            role=invite.role,
            is_active=True,
        )
        db_session.add(user_row)
        invite.status = InviteStatus.accepted
        await db_session.flush()

        if settings.firebase_enabled:
            firebase_uid = await run_in_threadpool(
                get_verifier().create_or_get_user,
                email=invite.email,
                password=body.password,
                display_name=body.name,
                reset_password=True,
            )
            user_row.firebase_uid = firebase_uid
            await run_in_threadpool(
                get_verifier().set_user_claims,
                firebase_uid,
                puid=str(user_row.id),
                tid=str(tenant_row.id),
                role=invite.role.value,
                ind=tenant_row.industry.value,
            )

        await audit.record(
            db_session,
            tenant_id=tenant_row.id,
            user_id=user_row.id,
            action="user.invite_accepted",
            entity_type="user",
            entity_id=str(user_row.id),
            industry=tenant_row.industry,
            ip_address=_client_ip(request),
            user_agent=request.headers.get("User-Agent"),
            request_id=getattr(request.state, "request_id", None),
        )
        result = SessionInfo(
            user_id=user_row.id,
            tenant_id=tenant_row.id,
            role=invite.role.value,
            active_industry=tenant_row.industry.value,
            email=user_row.email,
            full_name=user_row.full_name,
            onboarding=load_onboarding_state(tenant_row.settings),
        )
        await db_session.commit()

    log.info("auth.invite_accepted", tenant_id=str(result.tenant_id))
    return result
```

Add `"/api/v1/auth/accept-invite"` to `_PUBLIC_PATHS`, and the imports `from sqlalchemy import func`, `from app.models.invite import Invite, InviteStatus`, `from app.core.exceptions import NotFoundError`, `from app.schemas.auth import AcceptInviteRequest`.

- [ ] **Step 5: Run them to verify they pass**

```bash
cd backend && uv run pytest tests/test_accept_invite.py -v
```

Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app/routers/auth.py backend/app/schemas/auth.py backend/app/middleware/tenant_context.py backend/tests/test_accept_invite.py
git commit -m "feat(auth): redeem invites; members inherit the workspace industry

The invite link has always pointed at /accept-invite and nothing ever
redeemed it. Tenant, role and industry all come from the invite row."
```

---

### Task 11: Integrations cannot target another industry

**Files:**
- Modify: `backend/app/schemas/integrations.py:13,128`
- Modify: `backend/app/routers/integrations.py:59-145`, `backend/app/routers/integrations_hub.py:239-247,405-407,490-572`
- Test: `backend/tests/test_industry_scope.py` (append)

**Interfaces:**
- Consumes: `assert_industry`, `TenantIndustry`
- Produces: `target_industry` optional in both request schemas; persisted value is always the tenant's

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/test_industry_scope.py
async def test_integration_cannot_target_another_industry(
    client: AsyncClient, db_session: AsyncSession, test_tenant_id: uuid.UUID
) -> None:
    token = await _token(db_session, test_tenant_id, "fashion")
    r = await client.post(
        "/api/v1/integrations/connect/shopify",
        json={"target_industry": "pharma", "credentials": {"shop": "x", "token": "y"}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


async def test_integration_defaults_to_the_tenant_industry(
    client: AsyncClient, db_session: AsyncSession, test_tenant_id: uuid.UUID
) -> None:
    """Omitting the field is the normal path now — the server knows the industry."""
    token = await _token(db_session, test_tenant_id, "fashion")
    r = await client.post(
        "/api/v1/integrations/connect/shopify",
        json={"credentials": {"shop": "x", "token": "y"}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code in (200, 201), r.text
```

- [ ] **Step 2: Run them to verify they fail**

```bash
cd backend && uv run pytest tests/test_industry_scope.py -k integration -v
```

Expected: the first FAILS (the connection is created against pharma); the second FAILS 422 because `target_industry` is required.

- [ ] **Step 3: Make the field optional and verified**

In `backend/app/schemas/integrations.py` change both `target_industry: IndustryCode = Field(...)` declarations to:

```python
    target_industry: IndustryCode | None = Field(
        default=None,
        description="Deprecated. The workspace's own industry is always used; "
        "supplying a different one is refused.",
    )
```

In every handler that reads it, take `industry: TenantIndustry` as a dependency and resolve with `industry = assert_industry(body.target_industry, industry)` before use, persisting that value. For the multipart upload at `integrations_hub.py:490`, change `target_industry: Annotated[str, Form()]` to `Annotated[str | None, Form()] = None` and resolve the same way, deleting the manual `IndustryCode(target_industry)` / 400 block (`assert_industry` now owns both cases).

- [ ] **Step 4: Run them to verify they pass**

```bash
cd backend && uv run pytest tests/test_industry_scope.py tests/test_integrations_hub_db.py tests/test_sql_source.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/integrations.py backend/app/routers/integrations.py backend/app/routers/integrations_hub.py backend/tests/test_industry_scope.py
git commit -m "feat(authz): integrations use the tenant industry implicitly"
```

---

### Task 12: Background work uses the tenant industry

**Files:**
- Modify: `backend/app/workers/whatsapp_digest.py:85`
- Modify: `backend/ml/scripts/train_all.py:50-57`, `backend/ml/scripts/backfill_features.py:33-43`
- Test: `backend/tests/test_whatsapp_digest.py` (modify)

**Interfaces:**
- Consumes: `tenants.industry`
- Produces: no code path reads `tenants.industries` or `users.active_industry`

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/test_whatsapp_digest.py
async def test_digest_uses_the_tenant_industry(db_session: AsyncSession) -> None:
    """A worker has no user context, so it must read the tenant, not a user row."""
    import inspect

    from app.workers import whatsapp_digest

    source = inspect.getsource(whatsapp_digest)
    assert "active_industry" not in source
    assert "tenant.industry" in source
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd backend && uv run pytest tests/test_whatsapp_digest.py -k tenant_industry -v
```

Expected: FAIL — `active_industry` still appears at line 85.

- [ ] **Step 3: Update the readers**

`whatsapp_digest.py:85`: `industry = str(tenant.industry)`.

`train_all.py:50`: change the SELECT to `SELECT id::text, slug, industry::text AS industry FROM tenants {where}` and replace the `for ind in row.industries or []:` loop with a single-industry body using `row.industry`. Apply the identical change to `backfill_features.py:33-43`.

- [ ] **Step 4: Run it to verify it passes**

```bash
cd backend && uv run pytest tests/test_whatsapp_digest.py -v
```

Expected: all pass.

- [ ] **Step 5: Run the full backend suite — this is the Phase C gate**

```bash
cd backend && uv run pytest -q
```

Expected: all pass. Fix any remaining reader of the removed attributes before moving to the frontend.

- [ ] **Step 6: Commit**

```bash
git add backend/app/workers/whatsapp_digest.py backend/ml/scripts/train_all.py backend/ml/scripts/backfill_features.py backend/tests/test_whatsapp_digest.py
git commit -m "refactor(workers): read the tenant's single industry"
```

---

## Phase D — Frontend

### Task 13: Industry is a projection of the session

**Files:**
- Modify: `frontend/src/stores/industry.ts` (rewrite), `frontend/src/stores/auth.ts:126-140,300-340`
- Modify: `frontend/src/api/client.ts:37-39`
- Create: `frontend/src/hooks/useTenantIndustry.ts`, `frontend/src/stores/industry.test.ts`

**Interfaces:**
- Consumes: `SessionInfo.active_industry`
- Produces: `useTenantIndustry(): IndustryCode | null`; `useIndustryStore` exposes `activeIndustry: IndustryCode | null` and `setSessionIndustry` only — **`setIndustry` and `DEFAULT_INDUSTRY` are removed**

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/stores/industry.test.ts
import { describe, expect, it, beforeEach } from "vitest";
import { useIndustryStore } from "@/stores/industry";

describe("industry store", () => {
  beforeEach(() => {
    localStorage.clear();
    useIndustryStore.getState().setSessionIndustry(null);
  });

  it("exposes no way for the UI to change industry", () => {
    expect("setIndustry" in useIndustryStore.getState()).toBe(false);
  });

  it("does not persist industry to localStorage", () => {
    useIndustryStore.getState().setSessionIndustry("pharma");
    expect(localStorage.getItem("sanket.industry")).toBeNull();
  });

  it("ignores stale persisted state from an earlier version", () => {
    localStorage.setItem("sanket.industry", JSON.stringify({ state: { activeIndustry: "pharma" } }));
    useIndustryStore.getState().setSessionIndustry("fashion");
    expect(useIndustryStore.getState().activeIndustry).toBe("fashion");
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd frontend && npm test -- src/stores/industry.test.ts
```

Expected: FAIL — `setIndustry` is present and the store persists.

- [ ] **Step 3: Rewrite the store**

```typescript
// frontend/src/stores/industry.ts
import { create } from "zustand";
import type { IndustryCode } from "@/types/api";

/**
 * The workspace's industry, projected from the verified session.
 *
 * This used to be writable and localStorage-persisted, which made it a second,
 * client-owned source of truth: a stale value could outlive a logout and be
 * sent back as `X-Industry-Code`. A workspace now has exactly one industry,
 * decided by the server, so the only writer is `auth.setSession`.
 */
interface IndustryState {
  activeIndustry: IndustryCode | null;
  /** Internal: called by the auth store when a session is established. */
  setSessionIndustry: (i: IndustryCode | null) => void;
}

export const useIndustryStore = create<IndustryState>()((set) => ({
  activeIndustry: null,
  setSessionIndustry: (i) => set({ activeIndustry: i }),
}));

// One-time cleanup of the persisted key written by earlier versions.
try {
  localStorage.removeItem("sanket.industry");
} catch {
  /* storage may be unavailable */
}
```

```typescript
// frontend/src/hooks/useTenantIndustry.ts
import { useAuthStore } from "@/stores/auth";
import type { IndustryCode } from "@/types/api";

/**
 * The authenticated workspace's industry.
 *
 * Derived from the verified session, not from local state, so a stale value
 * cannot outlive a logout or survive into another account's session.
 */
export const useTenantIndustry = (): IndustryCode | null =>
  useAuthStore((s) => s.industry);
```

In `frontend/src/stores/auth.ts`: rename `defaultIndustry` to `industry` throughout (including `CLEARED` and `decodeToken`), and in `setSession` call `useIndustryStore.getState().setSessionIndustry(s.active_industry)` **before** the `set({...})` so no render observes an authenticated session without its industry. In `logout`, replace `useIndustryStore.getState().reset()` with `setSessionIndustry(null)`.

In `frontend/src/api/client.ts` delete the two lines that read the store and set `X-Industry-Code`, and drop the now-unused import.

- [ ] **Step 4: Run it to verify it passes**

```bash
cd frontend && npm test -- src/stores/industry.test.ts
```

Expected: 3 passed.

- [ ] **Step 5: Fix every call site the type change surfaces**

```bash
cd frontend && npm run typecheck
```

Each error is a component reading `activeIndustry` as non-nullable. In components that render only inside `ProtectedRoute` (`AppShell`, `Sidebar`, `TopBar`, dashboards), switch to `useTenantIndustry()` and return `null` early when it is `null`. Re-run until clean.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/stores/industry.ts frontend/src/stores/auth.ts frontend/src/api/client.ts frontend/src/hooks/useTenantIndustry.ts frontend/src/stores/industry.test.ts
git commit -m "feat(frontend): industry derives from the session, not local state"
```

---

### Task 14: No authenticated industry switcher

**Files:**
- Delete: `frontend/src/components/layout/IndustrySwitcher.tsx`
- Modify: `frontend/src/components/layout/TopBar.tsx:22,193`
- Create: `frontend/src/components/layout/TopBar.test.tsx`

**Interfaces:**
- Consumes: `useTenantIndustry`
- Produces: the header shows the workspace's industry as a static label

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/layout/TopBar.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { TopBar } from "@/components/layout/TopBar";
import { useAuthStore } from "@/stores/auth";

const renderTopBar = () =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <TopBar />
      </MemoryRouter>
    </QueryClientProvider>,
  );

describe("TopBar", () => {
  it("shows the workspace industry without offering a switch", () => {
    useAuthStore.setState({
      ready: true, isAuthenticated: true, industry: "fashion",
      role: "owner", email: "a@b.c", fullName: "A", userId: "u", tenantId: "t",
    });
    renderTopBar();
    expect(screen.queryByText(/switch industry/i)).toBeNull();
    expect(screen.queryByText(/pharmaceuticals/i)).toBeNull();
    expect(screen.queryByText(/agrocenter/i)).toBeNull();
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd frontend && npm test -- src/components/layout/TopBar.test.tsx
```

Expected: FAIL — the switcher renders every industry's name in its dropdown.

- [ ] **Step 3: Delete the switcher**

```bash
git rm frontend/src/components/layout/IndustrySwitcher.tsx
```

In `TopBar.tsx` remove the import and replace `<IndustrySwitcher />` at line 193 with a static badge built from `useTenantIndustry()` and `INDUSTRY_THEME`, showing only that industry's icon and label. Icons come from `@/components/ui/icons`.

- [ ] **Step 4: Run it to verify it passes**

```bash
cd frontend && npm test -- src/components/layout/TopBar.test.tsx
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add -A frontend/src/components/layout
git commit -m "feat(frontend): remove the authenticated industry switcher"
```

---

### Task 15: Signup asks for the industry

**Files:**
- Modify: `frontend/src/pages/Login.tsx:186-330,476-560`
- Modify: `frontend/src/api/{auth,industry}.ts`, `frontend/src/types/api.ts`
- Create: `frontend/src/pages/Login.test.tsx`

**Interfaces:**
- Consumes: public `GET /industry/catalog`
- Produces: `industryApi.catalog()`; `SignUpRequest.industry` and `GoogleSignUpRequest.industry` on the wire

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/pages/Login.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { LoginPage } from "@/pages/Login";
import { authApi } from "@/api/auth";

vi.mock("@/api/industry", () => ({
  industryApi: {
    catalog: vi.fn().mockResolvedValue({
      fashion: { display_name: "Apparel & Fashion", default_horizon_weeks: 26, audit_level: "standard" },
      pharma: { display_name: "Pharmaceuticals", default_horizon_weeks: 52, audit_level: "gxp" },
    }),
  },
}));

const renderPage = () =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={["/login?mode=signup"]}>
        <LoginPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );

describe("signup", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("sends the chosen industry to the backend", async () => {
    const signUp = vi.spyOn(authApi, "signUp").mockResolvedValue({
      status: "ok", user_id: "u", tenant_id: "t",
    });
    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByLabelText(/name/i), "Acme Owner");
    await user.type(screen.getByLabelText(/workspace/i), "acme-pharma");
    await user.type(screen.getByLabelText(/email/i), "owner@acme.test");
    await user.type(screen.getByLabelText(/^password/i), "Sup3rSecret!");
    await user.type(screen.getByLabelText(/confirm/i), "Sup3rSecret!");
    await user.click(await screen.findByRole("radio", { name: /pharmaceuticals/i }));
    await user.click(screen.getByRole("button", { name: /create workspace/i }));

    expect(signUp).toHaveBeenCalledWith(
      expect.objectContaining({ industry: "pharma", tenant_slug: "acme-pharma" }),
    );
  });

  it("refuses to submit without an industry", async () => {
    const signUp = vi.spyOn(authApi, "signUp");
    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByLabelText(/name/i), "Acme Owner");
    await user.type(screen.getByLabelText(/workspace/i), "acme-none");
    await user.type(screen.getByLabelText(/email/i), "owner2@acme.test");
    await user.type(screen.getByLabelText(/^password/i), "Sup3rSecret!");
    await user.type(screen.getByLabelText(/confirm/i), "Sup3rSecret!");
    await user.click(screen.getByRole("button", { name: /create workspace/i }));

    expect(signUp).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd frontend && npm test -- src/pages/Login.test.tsx
```

Expected: FAIL — no industry radio group exists.

- [ ] **Step 3: Add the selector**

In `frontend/src/api/industry.ts` replace `available` with `catalog: () => apiClient.get<Record<string, IndustryMeta>>("/industry/catalog").then((r) => r.data)`. Add `industry: IndustryCode` to `SignUpRequest` and `GoogleSignUpRequest` in `frontend/src/types/api.ts` and `frontend/src/api/auth.ts`.

In `Login.tsx` add `const [signUpIndustry, setSignUpIndustry] = useState<IndustryCode | null>(null);`, render a radio group from the catalog query inside the sign-up form (`role="radio"`, `aria-checked`, labelled by `display_name`), block submit when it is null with the message "Choose the industry this workspace plans for", and pass `industry: signUpIndustry` to `authApi.signUp`. Add the identical selector to the Google workspace modal and pass it to `authApi.googleSignup`.

- [ ] **Step 4: Run it to verify it passes**

```bash
cd frontend && npm test -- src/pages/Login.test.tsx
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Login.tsx frontend/src/pages/Login.test.tsx frontend/src/api/industry.ts frontend/src/api/auth.ts frontend/src/types/api.ts
git commit -m "feat(frontend): choosing an industry is part of creating a workspace"
```

---

### Task 16: Onboarding confirms, and only corrects while unlocked

**Files:**
- Modify: `frontend/src/pages/onboarding/StepIndustry.tsx` (rewrite)
- Create: `frontend/src/pages/onboarding/StepIndustry.test.tsx`

**Interfaces:**
- Consumes: `useTenantIndustry`, `industryApi.activate`
- Produces: the step renders the chosen industry; the correction control appears only for owner/admin

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/pages/onboarding/StepIndustry.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StepIndustry } from "@/pages/onboarding/StepIndustry";
import { useAuthStore } from "@/stores/auth";

const renderStep = () =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      <StepIndustry thisStep="industry" nextStep="data" save={async () => {}} />
    </QueryClientProvider>,
  );

describe("StepIndustry", () => {
  it("shows the workspace industry and no other", async () => {
    useAuthStore.setState({ ready: true, isAuthenticated: true, industry: "fashion", role: "owner" });
    renderStep();
    expect(await screen.findByText(/apparel & fashion/i)).toBeInTheDocument();
    expect(screen.queryByText(/pharmaceuticals/i)).toBeNull();
  });

  it("offers no correction to a non-admin member", () => {
    useAuthStore.setState({ ready: true, isAuthenticated: true, industry: "fashion", role: "analyst" });
    renderStep();
    expect(screen.queryByRole("button", { name: /change/i })).toBeNull();
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd frontend && npm test -- src/pages/onboarding/StepIndustry.test.tsx
```

Expected: FAIL — the step currently renders a five-option picker from `industryApi.available`.

- [ ] **Step 3: Rewrite the step**

Replace the selection grid with a confirmation card built from `useTenantIndustry()` and `INDUSTRY_THEME`. When `role` is `owner` or `admin`, render a "Change industry" control that reveals the catalog options and calls `industryApi.activate`; on a 409 show the returned detail as an inline notice rather than a toast. `submit()` marks the step done without any activation call when the industry is unchanged.

- [ ] **Step 4: Run it to verify it passes**

```bash
cd frontend && npm test -- src/pages/onboarding/StepIndustry.test.tsx
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/onboarding/StepIndustry.tsx frontend/src/pages/onboarding/StepIndustry.test.tsx
git commit -m "feat(frontend): onboarding confirms the industry instead of choosing it"
```

---

### Task 17: Industry-specific routes are guarded

**Files:**
- Create: `frontend/src/components/auth/IndustryRoute.tsx`, `frontend/src/components/auth/IndustryRoute.test.tsx`
- Modify: `frontend/src/App.tsx:241` (`pharma/batches`), `frontend/src/components/layout/Sidebar.tsx:169`

**Interfaces:**
- Consumes: `useTenantIndustry`
- Produces: `<IndustryRoute industry="pharma">` renders children or an access-denied panel

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/components/auth/IndustryRoute.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { IndustryRoute } from "@/components/auth/IndustryRoute";
import { useAuthStore } from "@/stores/auth";

describe("IndustryRoute", () => {
  it("renders the page for the workspace's own industry", () => {
    useAuthStore.setState({ ready: true, isAuthenticated: true, industry: "pharma" });
    render(<IndustryRoute industry="pharma"><p>Batches</p></IndustryRoute>);
    expect(screen.getByText("Batches")).toBeInTheDocument();
  });

  it("denies a manually typed route for another industry", () => {
    useAuthStore.setState({ ready: true, isAuthenticated: true, industry: "fashion" });
    render(<IndustryRoute industry="pharma"><p>Batches</p></IndustryRoute>);
    expect(screen.queryByText("Batches")).toBeNull();
    expect(screen.getByText(/not available for this workspace/i)).toBeInTheDocument();
  });

  it("renders nothing while the session is still loading", () => {
    useAuthStore.setState({ ready: false, isAuthenticated: false, industry: null });
    const { container } = render(
      <IndustryRoute industry="pharma"><p>Batches</p></IndustryRoute>,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd frontend && npm test -- src/components/auth/IndustryRoute.test.tsx
```

Expected: FAIL — the module does not exist.

- [ ] **Step 3: Write the guard**

```tsx
// frontend/src/components/auth/IndustryRoute.tsx
import type { ReactNode } from "react";
import { useAuthStore } from "@/stores/auth";
import { useTenantIndustry } from "@/hooks/useTenantIndustry";
import type { IndustryCode } from "@/types/api";

/**
 * Gate a route on the workspace's industry.
 *
 * Presentation only — the server returns 403 for the same request. This exists
 * so a manually typed URL produces a clear explanation instead of a wall of
 * failed queries.
 *
 * Renders nothing until the session resolves, so another industry's page can
 * never flash while auth is still loading.
 */
export const IndustryRoute = ({
  industry,
  children,
}: {
  industry: IndustryCode;
  children: ReactNode;
}) => {
  const ready = useAuthStore((s) => s.ready);
  const tenantIndustry = useTenantIndustry();

  if (!ready || tenantIndustry === null) return null;
  if (tenantIndustry !== industry) {
    return (
      <div className="grid place-items-center p-16 text-center">
        <div className="max-w-md space-y-2">
          <h1 className="font-heading text-xl font-semibold text-content">
            Not available for this workspace
          </h1>
          <p className="text-sm text-content-subtle">
            This workspace plans for a different industry, so this module is not
            part of it.
          </p>
        </div>
      </div>
    );
  }
  return <>{children}</>;
};
```

In `App.tsx` wrap the `pharma/batches` element in `<IndustryRoute industry="pharma">`. In `Sidebar.tsx:169` switch to `useTenantIndustry()` and filter pharma-only nav entries on it.

- [ ] **Step 4: Run it to verify it passes**

```bash
cd frontend && npm test -- src/components/auth/IndustryRoute.test.tsx
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/auth/IndustryRoute.tsx frontend/src/components/auth/IndustryRoute.test.tsx frontend/src/App.tsx frontend/src/components/layout/Sidebar.tsx
git commit -m "feat(frontend): guard industry-specific routes"
```

---

### Task 18: Integrations form drops the industry selector; accept-invite page

**Files:**
- Modify: `frontend/src/pages/Integrations.tsx:488,563,655,691`, `frontend/src/api/integrations.ts:9,20`
- Create: `frontend/src/pages/AcceptInvite.tsx`, `frontend/src/pages/Integrations.test.tsx`
- Modify: `frontend/src/App.tsx` (add `/accept-invite` route), `frontend/src/api/auth.ts`

**Interfaces:**
- Consumes: `POST /auth/accept-invite`
- Produces: `authApi.acceptInvite({token, name, password}) -> SessionInfo`

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/pages/Integrations.test.tsx
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";

describe("integrations", () => {
  it("never offers a target-industry choice", () => {
    const source = readFileSync("src/pages/Integrations.tsx", "utf8");
    expect(source).not.toMatch(/target_industry/);
    expect(source).not.toMatch(/Target industry/i);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd frontend && npm test -- src/pages/Integrations.test.tsx
```

Expected: FAIL — `target_industry` appears at four call sites.

- [ ] **Step 3: Remove it and add the invite page**

In `Integrations.tsx` delete `target_industry` from all three request bodies and replace the `<Meta label="Industry" …>` row with the workspace's own industry from `useTenantIndustry()`. In `frontend/src/api/integrations.ts` make `target_industry` optional on the response type and delete it from the request type.

Create `frontend/src/pages/AcceptInvite.tsx`: read `token` from the query string, collect name + password, call `authApi.acceptInvite`, then `setSession` and navigate to `/workspace`. It must not render any industry control — the industry comes back on the session. Add the route to `App.tsx` outside `ProtectedRoute`, and add `acceptInvite` to `frontend/src/api/auth.ts`.

- [ ] **Step 4: Run it to verify it passes**

```bash
cd frontend && npm test -- src/pages/Integrations.test.tsx
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/Integrations.tsx frontend/src/pages/Integrations.test.tsx frontend/src/pages/AcceptInvite.tsx frontend/src/api/integrations.ts frontend/src/api/auth.ts frontend/src/App.tsx
git commit -m "feat(frontend): integrations inherit the workspace industry; add invite redemption"
```

---

### Task 19: Four public entry points, and honest positioning

**Files:**
- Modify: `frontend/src/pages/LandingPage.tsx:1937-1955,2061-2130,2200-2240,2378-2420`
- Modify: `README.md:64`, `CLAUDE.md:18`
- Create: `frontend/src/pages/LandingPage.test.tsx`

**Interfaces:**
- Consumes: nothing
- Produces: named CTAs — Try Live Sandbox, Create Workspace, Request Enterprise Demo, Sign In

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/pages/LandingPage.test.tsx
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";

describe("landing page", () => {
  const source = readFileSync("src/pages/LandingPage.tsx", "utf8");

  it("exposes all four entry points", () => {
    for (const cta of [
      "Try Live Sandbox", "Create Workspace", "Request Enterprise Demo", "Sign in",
    ]) {
      expect(source).toContain(cta);
    }
  });

  it("does not sell multi-tenancy as a differentiator", () => {
    expect(source).not.toMatch(/multi-tenant/i);
  });

  it("does not let a visitor pick a sandbox industry the session ignores", () => {
    expect(source).not.toMatch(/setIndustry/);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd frontend && npm test -- src/pages/LandingPage.test.tsx
```

Expected: FAIL — "Create Workspace" and "Request Enterprise Demo" do not appear, and `setIndustry` is called in `launchSandbox`.

- [ ] **Step 3: Rewrite the entry points**

Rename the CTAs: "Try the Sandbox" → "Try Live Sandbox", "Book a Demo" → "Request Enterprise Demo", and add a "Create Workspace" button navigating to `/login?mode=signup` in the header, the hero, the final CTA and the mobile menu. Change `launchSandbox` to take no argument and drop the `setIndustry(code)` call; replace the sandbox modal's industry grid with a single line naming it a Fashion sample workspace.

Add the positioning line "One focused planning workspace, configured for your industry from day one." to the hero, and change the Enterprise tier bullet "SSO / SAML + data isolation" to keep the isolation claim while removing tenancy-as-feature framing. **Leave the security section at lines 2378-2420 alone** — tenant isolation and RLS are accurate security architecture the spec explicitly keeps.

In `CLAUDE.md:18` change "multi-tenant, multi-industry predictive analytics" to "industry-scoped predictive analytics & supply-chain SaaS. Each workspace is scoped to one industry; tenant isolation is enforced by PostgreSQL RLS." In `README.md:64` change "FastAPI multi-tenant backend" to "FastAPI backend with tenant-isolating RLS" — the architecture diagram at line 13 stays.

- [ ] **Step 4: Run it to verify it passes**

```bash
cd frontend && npm test -- src/pages/LandingPage.test.tsx
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/LandingPage.tsx frontend/src/pages/LandingPage.test.tsx README.md CLAUDE.md
git commit -m "feat(marketing): four clear entry points; industry-scoped positioning

Tenant isolation stays documented as security architecture; what goes
is multi-tenancy sold as a customer-facing differentiator."
```

---

## Phase E — End-to-end and completion

### Task 20: The Playwright journey

**Files:**
- Create: `frontend/e2e/industry-scope.spec.ts`

**Interfaces:**
- Consumes: the whole stack
- Produces: the seven-step journey from the spec

- [ ] **Step 1: Write the spec**

```typescript
// frontend/e2e/industry-scope.spec.ts
import { test, expect } from "@playwright/test";

const slug = `e2e-fashion-${Date.now()}`;
const email = `owner@${slug}.test`;
const password = "Sup3rSecret!";

test.describe("industry-scoped workspace", () => {
  test("a Fashion workspace can reach only Fashion", async ({ page, request }) => {
    // 1. Create a Fashion workspace.
    await page.goto("/login?mode=signup");
    await page.getByLabel(/name/i).fill("E2E Owner");
    await page.getByLabel(/workspace/i).fill(slug);
    await page.getByLabel(/email/i).fill(email);
    await page.getByLabel(/^password/i).fill(password);
    await page.getByLabel(/confirm/i).fill(password);
    await page.getByRole("radio", { name: /apparel & fashion/i }).click();
    await page.getByRole("button", { name: /create workspace/i }).click();

    // 2. Complete the permitted onboarding flow.
    await expect(page).toHaveURL(/\/onboarding/);
    await expect(page.getByText(/apparel & fashion/i)).toBeVisible();

    // 3. The Fashion experience loads.
    await page.goto("/workspace");
    await expect(page.getByText(/apparel & fashion/i)).toBeVisible();

    // 4. No other industry is navigable.
    for (const other of [/pharmaceutical/i, /agrocenter/i, /consumer electronics/i]) {
      await expect(page.getByText(other)).toHaveCount(0);
    }
    await expect(page.getByRole("button", { name: /switch industry/i })).toHaveCount(0);

    // 5. A directly typed Pharma URL is denied.
    await page.goto("/workspace/pharma/batches");
    await expect(page.getByText(/not available for this workspace/i)).toBeVisible();

    // 6. A direct Pharma API call is 403.
    const token = await page.evaluate(() => localStorage.getItem("sanket.dev.token"));
    const denied = await request.get("/api/v1/pharma/overview", {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(denied.status()).toBe(403);

    // 7. An invited teammate inherits Fashion.
    const invite = await request.post("/api/v1/invites", {
      headers: { Authorization: `Bearer ${token}` },
      data: { email: `mate@${slug}.test`, role: "analyst" },
    });
    expect(invite.status()).toBe(201);
    const inviteToken = (await invite.json()).invite_url.split("token=")[1];

    const accepted = await request.post("/api/v1/auth/accept-invite", {
      data: { token: inviteToken, name: "Team Mate", password: "An0therSecret!" },
    });
    expect(accepted.status()).toBe(201);
    expect((await accepted.json()).active_industry).toBe("fashion");
  });
});
```

- [ ] **Step 2: Run it**

```bash
cd frontend && npx playwright test e2e/industry-scope.spec.ts
```

Expected: passes against a running stack. If the dev server is not up, start it first; do **not** weaken an assertion to make it pass.

- [ ] **Step 3: Commit**

```bash
git add frontend/e2e/industry-scope.spec.ts
git commit -m "test(e2e): industry-scoped workspace journey"
```

---

### Task 21: Full verification

**Files:** none

- [ ] **Step 1: Backend**

```bash
cd backend && uv run pytest
```

- [ ] **Step 2: Frontend**

```bash
cd frontend && npm run typecheck && npm run lint && npm test
```

- [ ] **Step 3: Confirm RLS is untouched**

```bash
cd backend && uv run pytest tests/test_rls_isolation.py -v
```

Expected: pass. Tenant A still cannot read or modify tenant B's data.

- [ ] **Step 4: Grep for survivors**

```bash
cd backend && grep -rn "active_industry\|industries" app/ --include=*.py | grep -v "industry_scope\|models/industry"
```

Expected: no application code reads either. Matches inside the migration are correct.

- [ ] **Step 5: Invoke `superpowers:requesting-code-review`, then `superpowers:verification-before-completion`**

Report the real output of every command above, including any failures.

---

## Self-Review

**Spec coverage:** §2 invariant → Tasks 1-2; §3 primitive → Task 3; §4 data model → Tasks 1-2; §5 auth/claims → Tasks 6-8; §5.2 lock → Task 9; §5.3 invites → Tasks 10, 18, 20; §6 backend authz → Tasks 4, 5, 11, 12; §7 sandbox → Tasks 1, 8, 19; §8 frontend → Tasks 13-18; §9 marketing → Task 19; §11 acceptance → Tasks 20-21. No gaps.

**Placeholder scan:** no TBD/TODO; every code step carries real code; no "similar to Task N".

**Type consistency:** `tenant_industry`/`TenantIndustry`/`require_industry`/`assert_industry` (Task 3) are used with those exact names in Tasks 4, 9, 11. `create_tenant` (Task 7) is used in Task 7 only. `useTenantIndustry` (Task 13) is used in Tasks 14, 16, 17, 18. `setSessionIndustry` (Task 13) is used in Task 13's auth-store edit. `auth.industry` replaces `auth.defaultIndustry` consistently from Task 13 onward.
