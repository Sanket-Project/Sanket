# Location-level forecasting, allocation and transfers — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. If those skills are not available to you, follow the steps literally: write the test, watch it fail, implement, watch it pass, commit.

**Goal:** Give a multi-branch tenant (one DC + N stores sharing a SKU catalogue) per-(SKU, location) forecasts that reconcile to the SKU forecast, plus advisory DC→store allocation and store↔store transfer decisions.

**Architecture:**
- The SKU forecast stays authoritative. A post-step splits it across locations by stock-out-corrected, recency-weighted, category-shrunk sales shares (`share_split_v1`) and stores the result in a new partitioned table.
- Pure, DB-free modules do the maths: shares, quantile split, allocation water-filling and transfer matching.
- A DB service builds `allocation` and `transfer` decisions from the location forecasts, current stock and a `locations` network table. These decisions go into the existing `recommendations` ledger.

**Tech Stack:**
- Python 3.11+, FastAPI, SQLAlchemy 2 async, Alembic, PostgreSQL 16 with FORCE RLS, pytest + testcontainers (`uv run pytest`).
- React + Vite + TypeScript + Vitest for the frontend.

**Spec:** `docs/superpowers/specs/2026-10-26-location-forecasting-allocation-transfers-design.md` — read it in full before Task 1. Section numbers (§) below refer to it.

## Global Constraints

Every task's requirements implicitly include this section.

- **Read `AGENTS.md` and `CLAUDE.md` at the repo root first.** They bind every agent: TDD, systematic debugging, verification before claiming done, RLS rules and honest failure.
- **Never bypass RLS in application code.** App code connects as `sanket_app`. Every new tenant table gets `ENABLE` + `FORCE ROW LEVEL SECURITY`, the policy `USING (bypass_rls() OR tenant_id = current_tenant_id())`, and `GRANT SELECT, INSERT, UPDATE, DELETE ... TO sanket_app`.
- **Fail honestly.** Never invent a number to fill a gap. Missing input means `None` plus a human-readable reason. Unknown money means `None`, never `0` (follow `decision_engine._money(value, known)`).
- **Advisory only.** No writes to external connectors.
- **Constants (copy exactly):**

  | Name | Value |
  |---|---|
  | Share window | 12 complete weeks |
  | Decay half-life | 4 weeks |
  | Shrinkage `k` | 4 |
  | Unassigned-share degraded threshold | 0.05 |
  | `z` for p10/p90 | 1.2816 |
  | `min_allocation_units` default | 1 |
  | `min_transfer_units` default | 2 |
  | `transfer_lead_time_days` default | 2 |
  | `transfer_cost_per_unit` default | unset (`None`) |
  | Method-C gate | location MASE ≥ 5% better, SKU MASE ≤ 1% worse |

- **Location identity** is `lower(trim(location))`, the same key `app/services/coverage.py` uses. The text values `NULL`, `''` and `'default'` are **unassigned**, never a location.
- **Migrations:** the next revision ids are `0025`, `0026`, `0027`, chained after `0024`. Tests build the schema with `alembic upgrade head` automatically (`tests/conftest.py`). Against a real DB, migrations need `MIGRATION_DATABASE_URL` set to the postgres superuser, not `sanket_app`.
- **Frontend icons** come only from `@/components/ui/icons`. Never import an icon package directly.
- **Commits:** one per task, conventional messages, each ending with the attribution line the repo uses (`Co-Authored-By: ...`) if your tool adds one. Do **not** push and do **not** open PRs unless the user asks.

**Test commands:**
- Backend: `cd backend && uv run pytest tests/<file>.py -v`. Docker must be running for testcontainers.
- ML package: `cd backend/ml && uv run pytest tests/<file>.py -v`.
- Frontend: `cd frontend && npx vitest run <path>`, plus `npm run typecheck`.

## File structure

| File | Responsibility |
|---|---|
| `backend/app/config.py` (modify) | `forecast_max_skus` setting |
| `backend/ml/sanket_ml/config.py` (modify) | `zero_shot_batch_size`, higher `zero_shot_max_series` |
| `backend/ml/sanket_ml/inference/zero_shot.py` (modify) | Batched Chronos prediction |
| `backend/alembic/versions/0025_locations.py` | `locations` table |
| `backend/alembic/versions/0026_location_forecast_results.py` | Partitioned `location_forecast_results` + partition maintenance |
| `backend/alembic/versions/0027_recommendation_locations.py` | Location columns, new kinds, new open-unique index on `recommendations` |
| `backend/app/models/location.py` | `Location`, `LocationForecastResult` ORM models |
| `backend/app/models/enums.py` (modify) | `LocationKind`; `DecisionKind.allocation`, `DecisionKind.transfer` |
| `backend/app/services/locations.py` | Code normalisation, registration from data, network readiness |
| `backend/app/services/location_shares.py` | **Pure:** shares + quantile split |
| `backend/app/services/location_forecast.py` | DB: split a run into location rows; location bands loader |
| `backend/app/services/allocation.py` | **Pure:** DC→store allocation |
| `backend/app/services/transfers.py` | **Pure:** store↔store transfer matching |
| `backend/app/services/network_decisions.py` | DB: allocation + transfer `Decision`s for a run |
| `backend/app/services/decision_engine.py` (modify) | `Decision` location fields; policy keys |
| `backend/app/services/decision_builder.py` (modify) | Policy keys, network decisions, persistence of location fields |
| `backend/app/services/coverage.py` (modify) | Location cover from location forecast |
| `backend/app/services/forecast_accuracy.py` (modify) | Location MASE |
| `backend/app/services/hybrid_forecast.py` (modify) | SKU cap; location split hook |
| `backend/app/routers/locations.py` + `backend/app/main.py` (modify) | `GET/PATCH /locations` |
| `backend/app/routers/decisions.py` (modify) | Serialise location fields |
| `frontend/src/api/locations.ts` | API client |
| `frontend/src/components/settings/NetworkCard.tsx` + `frontend/src/pages/Settings.tsx` (modify) | Network setup |
| `frontend/src/pages/Inventory.tsx`, `frontend/src/pages/Decisions.tsx` (modify) | Location filter, route grouping |
| `backend/benchmarks/bench_location_pipeline.py` | 25k × 6 performance benchmark |

---

## Phase 0 — scale

### Task 1: Configurable SKU cap for forecast runs and decisions

**Files:**
- Modify: `backend/app/config.py` (inside `class Settings`, next to `ml_api_timeout_s` ~line 304)
- Modify: `backend/app/services/hybrid_forecast.py:175` (`sku_q = sku_q.limit(50)`)
- Modify: `backend/app/services/decision_builder.py:59` (`MAX_SKUS = 500`) and its use `ids = list(bands)[:MAX_SKUS]`
- Test: `backend/tests/test_forecast_sku_cap.py`

**Interfaces:**
- Produces: `Settings.forecast_max_skus: int` (default `30000`).

- [x] **Step 1: Write the failing test**

```python
"""A forecast run is not silently truncated to 50 SKUs (spec §2, Phase 0)."""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import text

from app.schemas.trends import HybridForecastRequest
from app.services import hybrid_forecast


async def _skus(db, tenant, n):
    pid = uuid.uuid4()
    await db.execute(
        text("INSERT INTO products (id, tenant_id, industry, name, category, status) "
             "VALUES (:p, :t, 'fashion', 'Kurti', 'Kurtis', 'active')"),
        {"p": str(pid), "t": str(tenant)},
    )
    ids = []
    for i in range(n):
        sid = uuid.uuid4()
        ids.append(sid)
        await db.execute(
            text("INSERT INTO skus (id, tenant_id, product_id, industry, sku_code) "
                 "VALUES (:s, :t, :p, 'fashion', :c)"),
            {"s": str(sid), "t": str(tenant), "p": str(pid), "c": f"SKU-{i:03d}"},
        )
    return ids


async def test_run_keeps_more_than_fifty_skus(db_session, app_role_db, make_tenant, monkeypatch):
    tenant = await make_tenant()
    ids = await _skus(db_session, tenant, 60)
    await db_session.commit()

    async def fake_baseline(tenant_id, industry, horizon_weeks, http_client=None):
        start = date(2026, 10, 26)
        return {"source": "zero_shot", "rows": [
            {"sku_id": str(s), "forecast_date": (start + timedelta(weeks=w)).isoformat(),
             "p10": 1.0, "p50": 2.0, "p90": 3.0}
            for s in ids for w in range(4)
        ]}

    monkeypatch.setattr(hybrid_forecast, "_fetch_ml_baseline", fake_baseline)
    result = await hybrid_forecast.compute_hybrid_forecast(
        db=app_role_db, http_client=None, realtime=None, run_id=uuid.uuid4(),
        tenant_id=tenant, industry_code="fashion",
        body=HybridForecastRequest(horizon_weeks=4, include_alerts=False),
    )
    assert len(result.out.series) == 60
```

- [x] **Step 2: Run it and confirm it fails**

Run: `cd backend && uv run pytest tests/test_forecast_sku_cap.py -v`
Expected: FAIL with `assert 50 == 60`.

If it fails for a different reason, read the traceback. For example, signal fusion may need a fixture the test lacks. Fix the *test setup* only, not production code, until the failure is the 50-vs-60 assertion.

- [x] **Step 3: Implement**

In `app/config.py` `class Settings`:

```python
    #: Upper bound on SKUs one forecast run / decision refresh evaluates. Large
    #: enough for a 25k-SKU multi-branch tenant; a guard, not a product limit.
    forecast_max_skus: int = 30000
```

In `hybrid_forecast.py`, replace `sku_q = sku_q.limit(50)` with:

```python
        sku_q = sku_q.limit(get_settings().forecast_max_skus)
```

In `decision_builder.py`:
- Delete `MAX_SKUS = 500`.
- Add `from app.config import get_settings` if it isn't already imported.
- Replace `ids = list(bands)[:MAX_SKUS]` with `ids = list(bands)[: get_settings().forecast_max_skus]`.
- Run `grep -rn "MAX_SKUS" backend/app backend/tests` and update any other reference the same way.

- [x] **Step 4: Run the tests and confirm they pass**

Run: `cd backend && uv run pytest tests/test_forecast_sku_cap.py tests/test_decision_engine.py tests/test_decision_readiness.py -v`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add backend/app/config.py backend/app/services/hybrid_forecast.py backend/app/services/decision_builder.py backend/tests/test_forecast_sku_cap.py
git commit -m "feat(forecast): configurable SKU cap instead of a hard 50"
```

### Task 2: Batched zero-shot inference past the 500-series cap

**Files:**
- Modify: `backend/ml/sanket_ml/config.py:97` (`zero_shot_max_series: int = 500`)
- Modify: `backend/ml/sanket_ml/inference/zero_shot.py:299-317` (`_chronos_predict`)
- Test: `backend/ml/tests/test_zero_shot_batching.py`

**Interfaces:**
- Produces: `MLSettings.zero_shot_batch_size: int = 256`; `MLSettings.zero_shot_max_series: int = 30000`.

- [x] **Step 1: Write the failing test**

```python
"""Chronos is called in bounded batches, and results keep series order."""
from __future__ import annotations

import numpy as np
import torch

from sanket_ml.config import MLSettings
from sanket_ml.inference import zero_shot


class _FakePipeline:
    def __init__(self):
        self.batch_sizes: list[int] = []

    def predict(self, ctx, prediction_length, num_samples):
        self.batch_sizes.append(len(ctx))
        # Each series forecasts its own last value, so order is checkable.
        last = torch.tensor([float(c[-1]) for c in ctx])
        return last.view(-1, 1, 1).repeat(1, num_samples, prediction_length)


def test_chronos_predict_batches_and_preserves_order(monkeypatch):
    fake = _FakePipeline()
    monkeypatch.setattr(zero_shot, "get_chronos_pipeline", lambda settings=None: fake)
    settings = MLSettings(zero_shot_batch_size=4)
    fc = zero_shot.ZeroShotForecaster(settings)
    arrays = {f"s{i}": np.array([0.0, float(i)], dtype=np.float32) for i in range(10)}

    p10, p50, p90 = fc._chronos_predict(arrays, horizon=3, num_samples=5)

    assert fake.batch_sizes == [4, 4, 2]
    assert p50.shape == (10, 3)
    assert [float(p50[i, 0]) for i in range(10)] == [float(i) for i in range(10)]


def test_default_series_cap_fits_a_multi_branch_tenant():
    assert MLSettings().zero_shot_max_series >= 30000
```

If `ZeroShotForecaster.__init__` needs more than `settings` (for example a loader that opens a DB), construct it with `object.__new__(zero_shot.ZeroShotForecaster)` and set `fc.settings = settings` instead. The test exercises `_chronos_predict` only.

- [x] **Step 2: Run it and confirm it fails**

Run: `cd backend/ml && uv run pytest tests/test_zero_shot_batching.py -v`
Expected: FAIL. Either `MLSettings` has no field `zero_shot_batch_size`, or `batch_sizes == [10]`.

- [x] **Step 3: Implement**

In `config.py`, next to `zero_shot_max_series`:

```python
    zero_shot_max_series: int = 30000
    #: Series per Chronos predict call — bounds memory, not the series count.
    zero_shot_batch_size: int = 256
```

Replace the body of `_chronos_predict` with:

```python
        pipeline = get_chronos_pipeline(self.settings)
        ctx_tensors = [torch.tensor(v, dtype=torch.float32) for v in context_arrays.values()]
        size = max(1, int(self.settings.zero_shot_batch_size))
        parts: list[np.ndarray] = []
        for start in range(0, len(ctx_tensors), size):
            forecast = pipeline.predict(
                ctx_tensors[start : start + size],
                prediction_length=horizon,
                num_samples=num_samples,
            )
            parts.append(
                forecast.cpu().numpy() if isinstance(forecast, torch.Tensor) else np.asarray(forecast)
            )
        # arr shape (N, num_samples, horizon)
        arr = np.concatenate(parts, axis=0)
        p10 = np.quantile(arr, 0.1, axis=1)
        p50 = np.quantile(arr, 0.5, axis=1)
        p90 = np.quantile(arr, 0.9, axis=1)
        return p10, p50, p90
```

- [x] **Step 4: Run the tests and confirm they pass**

Run: `cd backend/ml && uv run pytest tests/test_zero_shot_batching.py tests/test_zero_shot_eligibility.py tests/test_zero_shot_censoring.py -v`
Expected: PASS.

- [x] **Step 5: Commit**

```bash
git add backend/ml/sanket_ml/config.py backend/ml/sanket_ml/inference/zero_shot.py backend/ml/tests/test_zero_shot_batching.py
git commit -m "feat(ml): batch Chronos zero-shot calls; raise series cap for multi-branch tenants"
```

---

## Phase 1 — locations

### Task 3: `locations` table, model and RLS

**Files:**
- Create: `backend/alembic/versions/0025_locations.py`
- Create: `backend/app/models/location.py`
- Modify: `backend/app/models/enums.py` (add `LocationKind`)
- Modify: `backend/app/models/__init__.py` (export the new models the same way the existing ones are exported)
- Test: `backend/tests/test_locations_schema.py`

**Interfaces:**
- Produces:
  - `LocationKind(StrEnum)` with values `warehouse`, `store`, `unconfirmed`.
  - ORM `Location` with fields `id, tenant_id, code, name, kind, parent_location_id, lead_time_days_from_parent, is_active, attributes, created_at, updated_at`.

- [ ] **Step 1: Write the failing test**

```python
"""locations: tenant-isolated, unique per (tenant, code), kind constrained (spec §3.1)."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError


async def _insert(db, tenant, code, kind="unconfirmed"):
    await db.execute(
        text("INSERT INTO locations (tenant_id, code, name, kind) VALUES (:t, :c, :c, :k)"),
        {"t": str(tenant), "c": code, "k": kind},
    )


async def test_code_unique_per_tenant(db_session, make_tenant):
    t = await make_tenant()
    await _insert(db_session, t, "alwal")
    with pytest.raises(IntegrityError):
        await _insert(db_session, t, "alwal")


async def test_kind_is_constrained(db_session, make_tenant):
    t = await make_tenant()
    with pytest.raises(IntegrityError):
        await _insert(db_session, t, "x", kind="depot")


async def test_locations_are_tenant_isolated(db_session, app_role_db, make_tenant):
    a, b = await make_tenant(), await make_tenant()
    await _insert(db_session, a, "alwal")
    await _insert(db_session, b, "boduppal")
    await db_session.commit()
    async with app_role_db.session(str(a)) as s:
        codes = (await s.execute(text("SELECT code FROM locations"))).scalars().all()
    assert codes == ["alwal"]
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `cd backend && uv run pytest tests/test_locations_schema.py -v`
Expected: FAIL with `relation "locations" does not exist`.

- [ ] **Step 3: Implement the migration**

`0025_locations.py`:

```python
"""Add locations — the store / warehouse network of a tenant (location spec §3).

Sales and inventory keep their free-text ``location``; rows resolve to a
location by ``code = lower(trim(location))``. Kind is text + CHECK (as in
recommendations) so adding a kind is a one-line migration.

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "locations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False, server_default="unconfirmed"),
        sa.Column("parent_location_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lead_time_days_from_parent", sa.SmallInteger(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("attributes", postgresql.JSONB(), nullable=False,
                  server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_location_id"], ["locations.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_locations_tenant_code"),
        sa.CheckConstraint("kind IN ('warehouse', 'store', 'unconfirmed')",
                           name="ck_locations_kind"),
        sa.CheckConstraint("code = lower(btrim(code)) AND code NOT IN ('', 'default')",
                           name="ck_locations_code_normalised"),
        sa.CheckConstraint("lead_time_days_from_parent IS NULL OR lead_time_days_from_parent >= 0",
                           name="ck_locations_lead_time"),
    )
    op.execute(
        "CREATE TRIGGER trg_locations_updated_at BEFORE UPDATE ON locations "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at()"
    )
    op.execute("ALTER TABLE locations ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE locations FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY locations_isolation ON locations "
        "USING (bypass_rls() OR tenant_id = current_tenant_id())"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON locations TO sanket_app")


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS locations_isolation ON locations")
    op.execute("DROP TRIGGER IF EXISTS trg_locations_updated_at ON locations")
    op.drop_table("locations")
```

- [ ] **Step 4: Implement the enum and model**

In `enums.py`:

```python
class LocationKind(enum.StrEnum):
    warehouse = "warehouse"
    store = "store"
    unconfirmed = "unconfirmed"
```

`app/models/location.py`. Task 7 adds the second class to this file.

```python
"""Store / warehouse network and per-location forecasts (location spec §3–§4)."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, SmallInteger, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKey
from app.models.enums import LocationKind


class Location(UUIDPrimaryKey, TimestampMixin, Base):
    """One store or warehouse. ``code`` is ``lower(trim(raw))`` of the text that
    sales and inventory rows carry in their ``location`` column."""

    __tablename__ = "locations"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_locations_tenant_code"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[LocationKind] = mapped_column(
        SAEnum(LocationKind, name="location_kind", create_constraint=False, native_enum=False),
        nullable=False,
        default=LocationKind.unconfirmed,
    )
    parent_location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id", ondelete="SET NULL")
    )
    lead_time_days_from_parent: Mapped[int | None] = mapped_column(SmallInteger)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    attributes: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
```

Check that `TimestampMixin` maps `created_at` and `updated_at`. It does for `InventoryLevel`, which uses it with the same migration columns.

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `cd backend && uv run pytest tests/test_locations_schema.py tests/test_rls_isolation.py -v`
Expected: PASS. `test_force_rls_enabled_on_all_tenant_tables` also covers the new table.

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/0025_locations.py backend/app/models/location.py backend/app/models/enums.py backend/app/models/__init__.py backend/tests/test_locations_schema.py
git commit -m "feat(locations): add tenant-isolated locations table"
```

### Task 4: Location registration and network readiness

**Files:**
- Create: `backend/app/services/locations.py`
- Test: `backend/tests/test_locations_service.py`

**Interfaces:**
- Consumes: `Location`, `LocationKind` (Task 3).
- Produces:
  - `normalize_code(raw: str | None) -> str | None`
  - `async sync_locations(session, tenant_id: uuid.UUID) -> int` (returns rows created)
  - `async load_locations(session, tenant_id) -> list[Location]`
  - `network_readiness(locations: list[Location]) -> NetworkReadiness`
  - `@dataclass(frozen=True) NetworkReadiness(allocation_ready: bool, transfers_ready: bool, missing: list[str])`

- [ ] **Step 1: Write the failing test**

```python
"""Locations are registered from data as unconfirmed; readiness lists what is missing (spec §3.2–§3.3)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import text

from app.models.enums import LocationKind
from app.models.location import Location
from app.services.locations import load_locations, network_readiness, normalize_code, sync_locations


def test_normalize_code():
    assert normalize_code("  Alwal ") == "alwal"
    assert normalize_code("DEFAULT") is None
    assert normalize_code("") is None
    assert normalize_code(None) is None


async def _sku(db, tenant):
    pid, sid = uuid.uuid4(), uuid.uuid4()
    await db.execute(text("INSERT INTO products (id, tenant_id, industry, name, category, status) "
                          "VALUES (:p, :t, 'fashion', 'K', 'Kurtis', 'active')"),
                     {"p": str(pid), "t": str(tenant)})
    await db.execute(text("INSERT INTO skus (id, tenant_id, product_id, industry, sku_code) "
                          "VALUES (:s, :t, :p, 'fashion', 'K-M')"),
                     {"s": str(sid), "t": str(tenant), "p": str(pid)})
    return sid


async def test_sync_registers_sales_and_stock_locations_once(db_session, app_role_db, make_tenant):
    t = await make_tenant()
    sku = await _sku(db_session, t)
    for loc in ("Alwal", " alwal", None, "default"):
        await db_session.execute(
            text("INSERT INTO historical_sales (tenant_id, sku_id, industry, sale_time, channel, "
                 "units_sold, location) VALUES (:t, :s, 'fashion', :w, 'store', 1, :l)"),
            {"t": str(t), "s": str(sku), "l": loc, "w": datetime(2026, 10, 5, tzinfo=UTC)},
        )
    await db_session.execute(
        text("INSERT INTO inventory_levels (tenant_id, sku_id, industry, location, on_hand_units) "
             "VALUES (:t, :s, 'fashion', 'Central DC', 10)"),
        {"t": str(t), "s": str(sku)},
    )
    await db_session.commit()

    async with app_role_db.session(str(t)) as s:
        created = await sync_locations(s, t)
        again = await sync_locations(s, t)
        locs = await load_locations(s, t)

    assert created == 2 and again == 0
    assert sorted(l.code for l in locs) == ["alwal", "central dc"]
    assert all(l.kind == LocationKind.unconfirmed for l in locs)


def _loc(code, kind, parent=None, lead=None):
    return Location(id=uuid.uuid4(), tenant_id=uuid.uuid4(), code=code, name=code,
                    kind=kind, parent_location_id=parent, lead_time_days_from_parent=lead,
                    is_active=True, attributes={})


def test_readiness_requires_dc_parent_and_lead_time():
    dc = _loc("dc", LocationKind.warehouse)
    a = _loc("a", LocationKind.store, parent=dc.id, lead=3)
    b = _loc("b", LocationKind.store)
    r = network_readiness([dc, a, b])
    assert r.allocation_ready is False
    assert r.transfers_ready is True
    assert "Store 'b' has no supplying warehouse" in r.missing
    assert "Store 'b' has no lead time from its warehouse" in r.missing


def test_readiness_unconfirmed_blocks_everything():
    r = network_readiness([_loc("x", LocationKind.unconfirmed)])
    assert (r.allocation_ready, r.transfers_ready) == (False, False)
    assert "Location 'x' kind is not confirmed" in r.missing
    assert "No warehouse is defined" in r.missing
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `cd backend && uv run pytest tests/test_locations_service.py -v`
Expected: FAIL with `ModuleNotFoundError: app.services.locations`.

- [ ] **Step 3: Implement `app/services/locations.py`**

```python
"""Location identity, registration from imported data, and network readiness.

Imports never create locations themselves: any code seen on sales (last 365
days) or stock is registered here as ``unconfirmed``. Nothing is inferred from a
name — "Central DC" is not assumed to be a warehouse.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import LocationKind
from app.models.location import Location

UNASSIGNED_CODES = frozenset({"", "default"})


def normalize_code(raw: str | None) -> str | None:
    """``lower(trim(raw))``, or None when the value means "no location"."""
    if raw is None:
        return None
    code = raw.strip(" ").lower()
    return None if code in UNASSIGNED_CODES else code


_SYNC_SQL = text(
    """
    INSERT INTO locations (tenant_id, code, name, kind)
    SELECT :t, code, min(raw), 'unconfirmed'
      FROM (
        SELECT lower(btrim(location)) AS code, btrim(location) AS raw
          FROM inventory_levels WHERE tenant_id = :t AND location IS NOT NULL
        UNION ALL
        SELECT lower(btrim(location)), btrim(location)
          FROM historical_sales
         WHERE tenant_id = :t AND location IS NOT NULL
           AND sale_time >= now() - interval '365 days'
      ) seen
     WHERE code NOT IN ('', 'default')
     GROUP BY code
    ON CONFLICT (tenant_id, code) DO NOTHING
    """
)


async def sync_locations(session: AsyncSession, tenant_id: uuid.UUID) -> int:
    result = await session.execute(_SYNC_SQL, {"t": str(tenant_id)})
    return int(result.rowcount or 0)


async def load_locations(session: AsyncSession, tenant_id: uuid.UUID) -> list[Location]:
    rows = await session.execute(
        select(Location).where(Location.tenant_id == tenant_id).order_by(Location.code)
    )
    return list(rows.scalars().all())


@dataclass(frozen=True)
class NetworkReadiness:
    allocation_ready: bool
    transfers_ready: bool
    missing: list[str] = field(default_factory=list)


def network_readiness(locations: list[Location]) -> NetworkReadiness:
    active = [l for l in locations if l.is_active]
    missing: list[str] = []
    for l in active:
        if l.kind == LocationKind.unconfirmed:
            missing.append(f"Location '{l.code}' kind is not confirmed")
    warehouses = {l.id for l in active if l.kind == LocationKind.warehouse}
    stores = [l for l in active if l.kind == LocationKind.store]
    if not warehouses:
        missing.append("No warehouse is defined")
    for s in stores:
        if s.parent_location_id is None or s.parent_location_id not in warehouses:
            missing.append(f"Store '{s.code}' has no supplying warehouse")
        if s.lead_time_days_from_parent is None:
            missing.append(f"Store '{s.code}' has no lead time from its warehouse")
    unconfirmed = any(l.kind == LocationKind.unconfirmed for l in active)
    allocation_ready = not missing and bool(stores)
    transfers_ready = not unconfirmed and len(stores) >= 2
    return NetworkReadiness(allocation_ready, transfers_ready, missing)
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `cd backend && uv run pytest tests/test_locations_service.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/locations.py backend/tests/test_locations_service.py
git commit -m "feat(locations): register locations from data and report network readiness"
```

### Task 5: `GET /locations` and `PATCH /locations/{id}`

**Files:**
- Create: `backend/app/routers/locations.py`
- Modify: `backend/app/main.py` (import the router; add `app.include_router(locations_router, prefix=api_prefix, dependencies=gated)` next to `inventory_router`, ~line 487)
- Test: `backend/tests/test_locations_api.py`

**Interfaces:**
- Consumes: `sync_locations`, `load_locations`, `network_readiness` (Task 4); `require_admin` from `app.core.rbac`; `TenantId` from `app.routers.industry_router`.
- Produces: `GET /api/v1/locations` returning
  `{"locations": [LocationOut], "network": {"allocation_ready", "transfers_ready", "missing"}}`, and
  `PATCH /api/v1/locations/{id}` accepting `LocationPatch` (all fields optional: `name, kind, parent_location_id, lead_time_days_from_parent, is_active`).

Before writing the test, read `tests/test_decision_expiry.py` or another API test to see how an authenticated `client` request is made: header names, how a user and tenant are created, and the api prefix. Copy that exact helper pattern.

- [ ] **Step 1: Write the failing test.** Using that helper pattern:
  - **(a)** `GET /locations` on a tenant with sales at "Alwal" returns one `unconfirmed` location and `network.allocation_ready == False`.
  - **(b)** As admin, `PATCH` a DC to `kind="warehouse"` and a store to `kind="store", parent_location_id=<dc>, lead_time_days_from_parent=3`. A following `GET` reports `allocation_ready == True`.
  - **(c)** `PATCH` setting a store's parent to another *store* returns 422 with detail `"Parent must be a warehouse of this workspace"`.
  - **(d)** A non-admin (analyst) `PATCH` returns 403.

- [ ] **Step 2: Run it and confirm it fails** (404 on `/locations`).

- [ ] **Step 3: Implement the router**

```python
"""Store / warehouse network: list (registering any newly seen codes) and edit."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.rbac import require_admin
from app.models.enums import LocationKind
from app.models.location import Location
from app.routers.industry_router import TenantId
from app.services.locations import load_locations, network_readiness, sync_locations

router = APIRouter(prefix="/locations", tags=["locations"])


class LocationPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    kind: LocationKind | None = None
    parent_location_id: uuid.UUID | None = None
    lead_time_days_from_parent: int | None = Field(default=None, ge=0, le=365)
    is_active: bool | None = None


def _out(l: Location) -> dict[str, Any]:
    return {
        "id": str(l.id), "code": l.code, "name": l.name, "kind": str(l.kind),
        "parent_location_id": str(l.parent_location_id) if l.parent_location_id else None,
        "lead_time_days_from_parent": l.lead_time_days_from_parent,
        "is_active": l.is_active,
    }


def _network(locs: list[Location]) -> dict[str, Any]:
    r = network_readiness(locs)
    return {"allocation_ready": r.allocation_ready, "transfers_ready": r.transfers_ready,
            "missing": r.missing}


@router.get("")
async def list_locations(request: Request, tenant_id: TenantId) -> dict[str, Any]:
    db = request.app.state.db
    async with db.session(str(tenant_id)) as session:
        await sync_locations(session, tenant_id)
        locs = await load_locations(session, tenant_id)
    return {"locations": [_out(l) for l in locs], "network": _network(locs)}


@router.patch("/{location_id}")
async def update_location(
    request: Request,
    tenant_id: TenantId,
    location_id: uuid.UUID,
    body: LocationPatch,
    _rbac: Annotated[None, require_admin],
) -> dict[str, Any]:
    db = request.app.state.db
    async with db.session(str(tenant_id)) as session:
        locs = {l.id: l for l in await load_locations(session, tenant_id)}
        loc = locs.get(location_id)
        if loc is None:
            raise HTTPException(status_code=404, detail="Location not found")
        changes = body.model_dump(exclude_unset=True)
        if "parent_location_id" in changes and changes["parent_location_id"] is not None:
            parent = locs.get(changes["parent_location_id"])
            if parent is None or parent.kind != LocationKind.warehouse or parent.id == loc.id:
                raise HTTPException(status_code=422,
                                    detail="Parent must be a warehouse of this workspace")
        for key, value in changes.items():
            setattr(loc, key, value)
        if loc.kind == LocationKind.warehouse:
            loc.parent_location_id = None
            loc.lead_time_days_from_parent = None
        await session.flush()
        out = _out(loc)
        network = _network(list(locs.values()))
    return {"location": out, "network": network}
```

Note: `exclude_unset` lets a client clear `parent_location_id` by sending `null` explicitly.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `cd backend && uv run pytest tests/test_locations_api.py tests/test_rbac.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/locations.py backend/app/main.py backend/tests/test_locations_api.py
git commit -m "feat(locations): list and edit the store/warehouse network"
```

---

## Phase 2 — location forecasts

### Task 6: Pure share and quantile maths

**Files:**
- Create: `backend/app/services/location_shares.py`
- Test: `backend/tests/test_location_shares.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True, slots=True) WeekObs(week: date, location: str | None, units: float, in_stock: bool | None)` — `location=None` means unassigned.
  - `@dataclass(frozen=True, slots=True) ShareResult(shares: dict[str, float], basis: dict[str, str], unassigned: float, evidence_weeks: float)`
  - `rates(obs, weeks: list[date]) -> tuple[dict[str, float], float, float]` returning `(rate_by_location, unassigned_rate, evidence_weeks)`
  - `blend_shares(sku: ShareResult | None, category: ShareResult | None, k: float = SHRINK_K) -> ShareResult`
  - `shares_from_obs(obs, weeks: list[date]) -> ShareResult`
  - `split_week(p10: float, p50: float, p90: float, share: float) -> tuple[float, float, float]`
  - constants `WINDOW_WEEKS = 12`, `HALF_LIFE_WEEKS = 4.0`, `SHRINK_K = 4.0`, `Z90 = 1.2816`

- [ ] **Step 1: Write the failing tests**

```python
"""share_split_v1 maths (spec §4.1–§4.2). Pure: no database."""
from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

from app.services.location_shares import (
    HALF_LIFE_WEEKS, WeekObs, blend_shares, shares_from_obs, split_week,
)

WEEKS = [date(2026, 8, 3) + timedelta(weeks=i) for i in range(12)]  # oldest → newest


def _flat(loc, per_week, weeks=WEEKS, in_stock=None):
    return [WeekObs(w, loc, per_week, in_stock) for w in weeks]


def test_steady_two_stores_split_by_volume():
    r = shares_from_obs(_flat("a", 30) + _flat("b", 10), WEEKS)
    assert r.shares == pytest.approx({"a": 0.75, "b": 0.25})
    assert r.unassigned == 0


def test_recent_weeks_weigh_more():
    obs = _flat("a", 10, WEEKS[:6]) + _flat("b", 10, WEEKS[6:])
    r = shares_from_obs(obs, WEEKS)
    assert r.shares["b"] > r.shares["a"]


def test_out_of_stock_weeks_do_not_shrink_a_share():
    # b sells 10/week but was out of stock in the 6 newest weeks (selling 0).
    obs = _flat("a", 10) + _flat("b", 10, WEEKS[:6]) + _flat("b", 0, WEEKS[6:], in_stock=False)
    r = shares_from_obs(obs, WEEKS)
    assert r.shares == pytest.approx({"a": 0.5, "b": 0.5})


def test_missing_weeks_are_observed_zero():
    r = shares_from_obs(_flat("a", 10) + _flat("b", 10, WEEKS[-1:]), WEEKS)
    assert r.shares["b"] < 0.2


def test_unassigned_is_held_back():
    r = shares_from_obs(_flat("a", 9) + _flat(None, 1), WEEKS)
    assert r.unassigned == pytest.approx(0.1)
    assert sum(r.shares.values()) == pytest.approx(0.9)


def test_blend_no_history_uses_category_prior():
    cat = shares_from_obs(_flat("a", 1) + _flat("b", 3), WEEKS)
    r = blend_shares(None, cat)
    assert r.shares == pytest.approx({"a": 0.25, "b": 0.75})
    assert set(r.basis.values()) == {"category_prior"}


def test_blend_long_history_tracks_sku():
    sku = shares_from_obs(_flat("a", 100) + _flat("b", 100), WEEKS)
    cat = shares_from_obs(_flat("a", 1) + _flat("b", 9), WEEKS)
    r = blend_shares(sku, cat)
    lam = sku.evidence_weeks / (sku.evidence_weeks + 4)
    assert r.shares["a"] == pytest.approx(lam * 0.5 + (1 - lam) * 0.1)
    assert sum(r.shares.values()) == pytest.approx(1.0)


def test_split_preserves_p50_and_floors_p10():
    lp10, lp50, lp90 = split_week(2.0, 10.0, 18.0, 0.3)
    assert lp50 == pytest.approx(3.0)
    assert lp10 >= 0
    assert lp90 > lp50


def test_split_full_share_reproduces_symmetric_band():
    assert split_week(5.0, 10.0, 15.0, 1.0) == pytest.approx((5.0, 10.0, 15.0))


def test_split_small_share_is_relatively_wider():
    _, p50_s, p90_s = split_week(8.0, 10.0, 12.0, 0.1)
    assert (p90_s - p50_s) / p50_s > (12.0 - 10.0) / 10.0


@pytest.mark.parametrize("shares", [[0.5, 0.3, 0.2], [0.9, 0.05, 0.05], [1 / 3] * 3])
def test_location_p50_sums_to_sku_p50(shares):
    assert sum(split_week(4, 10, 16, s)[1] for s in shares) == pytest.approx(10.0)


def test_half_life_constant():
    assert HALF_LIFE_WEEKS == 4.0
```

- [ ] **Step 2: Run them and confirm they fail** (`ModuleNotFoundError`).

Run: `cd backend && uv run pytest tests/test_location_shares.py -v`

- [ ] **Step 3: Implement `app/services/location_shares.py`**

```python
"""share_split_v1: split a SKU forecast across locations (location spec §4.1–§4.2).

Pure functions only — the database service in ``location_forecast`` feeds them.

* A location's **rate** is its recency-weighted units per in-stock week; weeks
  it was out of stock are dropped from both sums, so lost sales never shrink
  its share. A week with no sales row is an observed zero.
* Unassigned sales (no location) have their own rate over every week and are
  held back: location shares sum to ``1 − unassigned``.
* Sparse SKUs are shrunk toward their category's shares with weight
  ``n / (n + k)``, where ``n`` is the weighted number of weeks with SKU sales.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

WINDOW_WEEKS = 12
HALF_LIFE_WEEKS = 4.0
SHRINK_K = 4.0
Z90 = 1.2816
_SKU_HISTORY_MIN_WEIGHT = 0.9


@dataclass(frozen=True, slots=True)
class WeekObs:
    week: date
    location: str | None
    units: float
    in_stock: bool | None = None


@dataclass(frozen=True, slots=True)
class ShareResult:
    shares: dict[str, float]
    basis: dict[str, str] = field(default_factory=dict)
    unassigned: float = 0.0
    evidence_weeks: float = 0.0


def _weights(weeks: list[date]) -> dict[date, float]:
    newest = max(weeks)
    return {w: 0.5 ** (((newest - w).days // 7) / HALF_LIFE_WEEKS) for w in weeks}


def rates(obs: list[WeekObs], weeks: list[date]) -> tuple[dict[str, float], float, float]:
    """(rate per location, unassigned rate, evidence weeks) over ``weeks``."""
    if not weeks:
        return {}, 0.0, 0.0
    w = _weights(weeks)
    units: dict[str | None, dict[date, float]] = defaultdict(lambda: defaultdict(float))
    oos: dict[str, set[date]] = defaultdict(set)
    sold_weeks: set[date] = set()
    for o in obs:
        if o.week not in w:
            continue
        units[o.location][o.week] += float(o.units)
        if o.location is not None and o.in_stock is False:
            oos[o.location].add(o.week)
        if o.units > 0:
            sold_weeks.add(o.week)

    loc_rates: dict[str, float] = {}
    for loc, by_week in units.items():
        if loc is None:
            continue
        in_stock_weeks = [wk for wk in weeks if wk not in oos[loc]]
        denom = sum(w[wk] for wk in in_stock_weeks)
        if denom <= 0:
            continue
        loc_rates[loc] = sum(w[wk] * by_week.get(wk, 0.0) for wk in in_stock_weeks) / denom
    total_w = sum(w.values())
    unassigned_rate = sum(w[wk] * u for wk, u in units.get(None, {}).items()) / total_w
    evidence = sum(w[wk] for wk in sold_weeks)
    return loc_rates, unassigned_rate, evidence


def shares_from_obs(obs: list[WeekObs], weeks: list[date]) -> ShareResult:
    loc_rates, un_rate, evidence = rates(obs, weeks)
    total = sum(loc_rates.values()) + un_rate
    if total <= 0:
        return ShareResult(shares={}, unassigned=0.0, evidence_weeks=0.0)
    return ShareResult(
        shares={l: r / total for l, r in loc_rates.items() if r > 0},
        basis={l: "sku_history" for l, r in loc_rates.items() if r > 0},
        unassigned=un_rate / total,
        evidence_weeks=evidence,
    )


def blend_shares(
    sku: ShareResult | None, category: ShareResult | None, k: float = SHRINK_K
) -> ShareResult:
    """Shrink SKU shares toward category shares; renormalise to ``1 − unassigned``."""
    n = sku.evidence_weeks if sku and sku.shares else 0.0
    if n <= 0:
        if not category or not category.shares:
            return ShareResult(shares={})
        return ShareResult(
            shares=dict(category.shares),
            basis={l: "category_prior" for l in category.shares},
            unassigned=category.unassigned,
            evidence_weeks=0.0,
        )
    lam = n / (n + k)
    cat = category.shares if category else {}
    locs = set(sku.shares) | set(cat)
    raw = {l: lam * sku.shares.get(l, 0.0) + (1 - lam) * cat.get(l, 0.0) for l in locs}
    raw = {l: v for l, v in raw.items() if v > 0}
    target = 1.0 - sku.unassigned
    scale = target / sum(raw.values()) if raw else 0.0
    if lam >= _SKU_HISTORY_MIN_WEIGHT:
        label = "sku_history"
    elif cat:
        label = "blended"
    else:
        label = "sku_history"
    return ShareResult(
        shares={l: v * scale for l, v in raw.items()},
        basis={l: label for l in raw},
        unassigned=sku.unassigned,
        evidence_weeks=n,
    )


def split_week(p10: float, p50: float, p90: float, share: float) -> tuple[float, float, float]:
    """Location quantiles for one week (multinomial thinning, spec §4.2)."""
    s = min(1.0, max(0.0, float(share)))
    sigma = max(0.0, float(p90) - float(p10)) / (2 * Z90)
    var = s * s * sigma * sigma + s * (1 - s) * max(0.0, float(p50))
    sd = math.sqrt(var)
    lp50 = s * float(p50)
    return max(0.0, lp50 - Z90 * sd), lp50, lp50 + Z90 * sd
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `cd backend && uv run pytest tests/test_location_shares.py -v`
Expected: PASS. If `test_blend_long_history_tracks_sku` is off by the renormalisation, check that `sku.unassigned == 0` in that fixture. It is, so `scale == 1`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/location_shares.py backend/tests/test_location_shares.py
git commit -m "feat(forecast): share_split_v1 maths for per-location forecasts"
```

### Task 7: `location_forecast_results` table

**Files:**
- Create: `backend/alembic/versions/0026_location_forecast_results.py`
- Modify: `backend/app/models/location.py` (add `LocationForecastResult`)
- Test: `backend/tests/test_location_forecast_schema.py`

**Interfaces:**
- Produces: ORM `LocationForecastResult` with fields `id, tenant_id, run_id, sku_id, location_id, forecast_date, p10, p50, p90, share, share_basis, method, created_at`, primary key `(id, forecast_date)`.

- [ ] **Step 1: Write the failing test**

```python
"""location_forecast_results: partitioned, RLS-isolated, maintained (spec §4.3)."""
from __future__ import annotations

import uuid

from sqlalchemy import text


async def test_partitioned_and_maintained(db_session):
    kind = await db_session.scalar(text(
        "SELECT c.relkind FROM pg_class c WHERE c.relname = 'location_forecast_results'"))
    assert kind == "p"
    parents = (await db_session.execute(
        text("SELECT parent FROM sanket_maintain_partitions()"))).scalars().all()
    assert {"historical_sales", "forecast_results", "trend_signals",
            "location_forecast_results"} <= set(parents)


async def test_rls_isolated(db_session, app_role_db, make_tenant):
    a, b = await make_tenant(), await make_tenant()
    for t in (a, b):
        run = uuid.uuid4()
        await db_session.execute(text(
            "INSERT INTO forecast_runs (id, tenant_id, industry, model_stack, horizon_weeks, "
            "granularity, status) VALUES (:r, :t, 'fashion', ARRAY['x'], 4, 'weekly', 'completed')"),
            {"r": str(run), "t": str(t)})
        await db_session.execute(text(
            "INSERT INTO location_forecast_results (tenant_id, run_id, sku_id, location_id, "
            "forecast_date, p10, p50, p90, share, share_basis, method) VALUES "
            "(:t, :r, gen_random_uuid(), gen_random_uuid(), current_date, 1, 2, 3, 0.5, "
            "'sku_history', 'share_split_v1')"), {"t": str(t), "r": str(run)})
    await db_session.commit()
    async with app_role_db.session(str(a)) as s:
        n = await s.scalar(text("SELECT count(*) FROM location_forecast_results"))
    assert n == 1
```

- [ ] **Step 2: Run it and confirm it fails.**

- [ ] **Step 3: Implement the migration**

```python
"""Add location_forecast_results — per-(SKU, location) forecasts (location spec §4.3).

Kept apart from forecast_results on purpose: every existing reader aggregates
forecast_results by sku_id, and location rows there would be double counted.
Quarterly RANGE partitions on forecast_date, maintained by
sanket_maintain_partitions() exactly like forecast_results.

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-26
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _maintain_fn(include_location: bool) -> str:
    location = (
        """
    parent := 'location_forecast_results';
    created := sanket_ensure_quarterly_partitions('location_forecast_results'::regclass, 1, 4);
    RETURN NEXT;
"""
        if include_location
        else ""
    )
    return f"""
CREATE OR REPLACE FUNCTION sanket_maintain_partitions()
RETURNS TABLE (parent text, created int)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    parent := 'historical_sales';
    created := sanket_ensure_quarterly_partitions('historical_sales'::regclass, 1, 4);
    RETURN NEXT;

    parent := 'forecast_results';
    created := sanket_ensure_quarterly_partitions('forecast_results'::regclass, 1, 4);
    RETURN NEXT;

    parent := 'trend_signals';
    created := sanket_ensure_monthly_partitions('trend_signals'::regclass, 2, 3);
    RETURN NEXT;
{location}END;
$$;
"""


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE location_forecast_results (
            id             UUID          NOT NULL DEFAULT gen_random_uuid(),
            tenant_id      UUID          NOT NULL,
            run_id         UUID          NOT NULL REFERENCES forecast_runs (id) ON DELETE CASCADE,
            sku_id         UUID          NOT NULL,
            location_id    UUID          NOT NULL,
            forecast_date  DATE          NOT NULL,
            p10            NUMERIC(18,4) NOT NULL,
            p50            NUMERIC(18,4) NOT NULL,
            p90            NUMERIC(18,4) NOT NULL,
            share          NUMERIC(9,6)  NOT NULL,
            share_basis    TEXT          NOT NULL,
            method         TEXT          NOT NULL,
            created_at     TIMESTAMPTZ   NOT NULL DEFAULT now(),
            PRIMARY KEY (id, forecast_date),
            CONSTRAINT ck_lfr_basis CHECK (share_basis IN ('sku_history', 'blended', 'category_prior')),
            CONSTRAINT ck_lfr_method CHECK (method IN ('share_split_v1', 'middle_out_mint'))
        ) PARTITION BY RANGE (forecast_date)
        """
    )
    op.execute("CREATE INDEX idx_lfr_run_sku_loc ON location_forecast_results "
               "(run_id, sku_id, location_id, forecast_date)")
    op.execute("CREATE INDEX idx_lfr_tenant_loc ON location_forecast_results "
               "(tenant_id, location_id, forecast_date)")
    op.execute("ALTER TABLE location_forecast_results ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE location_forecast_results FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY location_forecast_results_isolation ON location_forecast_results "
        "USING (bypass_rls() OR tenant_id = current_tenant_id())"
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON location_forecast_results TO sanket_app")
    op.execute(_maintain_fn(include_location=True))
    op.execute("SELECT sanket_maintain_partitions()")


def downgrade() -> None:
    op.execute(_maintain_fn(include_location=False))
    op.execute("DROP TABLE IF EXISTS location_forecast_results CASCADE")
```

Before relying on this:
- Open `0024_trend_signal_partitions.py` and confirm `_maintain_fn(include_trend_signals=True)` produces exactly the three-table body copied above. If it differs, copy its body verbatim and only append the location block.
- Partition children inherit RLS from a partitioned parent only for queries through the parent. `test_force_rls_enabled_on_all_tenant_tables` filters `relkind = 'r'`. If it flags the new child partitions, follow whatever `forecast_results` partitions do (check `sql/003_rls_policies.sql` and migration 0013) and apply the same.

- [ ] **Step 4: Add the model** to `app/models/location.py`. Extend the imports with `from datetime import date, datetime`, `from decimal import Decimal`, `from sqlalchemy import Date, DateTime, Numeric, func`.

```python
class LocationForecastResult(Base):
    """Partitioned by forecast_date (RANGE); no FK on sku/location, like ForecastResult."""

    __tablename__ = "location_forecast_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("forecast_runs.id", ondelete="CASCADE"), nullable=False
    )
    sku_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    forecast_date: Mapped[date] = mapped_column(Date, nullable=False)
    p10: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    p50: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    p90: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    share: Mapped[Decimal] = mapped_column(Numeric(9, 6), nullable=False)
    share_basis: Mapped[str] = mapped_column(Text, nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False, default="share_split_v1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __mapper_args__ = {"primary_key": [id, forecast_date]}
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `cd backend && uv run pytest tests/test_location_forecast_schema.py tests/test_partitions.py tests/test_rls_isolation.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/0026_location_forecast_results.py backend/app/models/location.py backend/tests/test_location_forecast_schema.py
git commit -m "feat(forecast): partitioned location_forecast_results table"
```

### Task 8: Split a forecast run into location rows

**Files:**
- Create: `backend/app/services/location_forecast.py`
- Modify: `backend/app/services/hybrid_forecast.py` (`_persist_accuracy_snapshot`, after the `ForecastResult` loop and before `await session.commit()`)
- Test: `backend/tests/test_location_forecast_split.py`

**Interfaces:**
- Consumes: Task 4 (`sync_locations`, `load_locations`), Task 6 (all of `location_shares`), Task 7 model; `app.core.calendar.current_week_start`, `week_bucket`, `week_start_instant`.
- Produces:
  - `@dataclass SplitSummary(series: int, excluded: list[dict[str, str]], unassigned_share: float, degraded: bool)`
  - `async split_run_by_location(session, *, tenant_id, industry: str, run_id, now) -> SplitSummary` — idempotent: deletes the run's existing location rows first.
  - `async ensure_location_split(session, *, tenant_id, industry, run, now) -> SplitSummary | None` — returns `None` without writing when rows already exist for the run.
  - `async location_bands(session, tenant_id, run_id, now) -> dict[tuple[uuid.UUID, uuid.UUID], DemandBand]` — keyed `(sku_id, location_id)`, weeks from the current week forward.
  - Run `metrics` gain keys `location_series`, `location_excluded` (count), `unassigned_share`, `location_degraded`.

- [ ] **Step 1: Write the failing test.** Reuse the helpers from `tests/test_inventory_coverage.py`: copy `_sku`, `_weekly_sales` and `_forecast` into the new test file. Do not import them across test modules. Use `NOW = datetime(2026, 10, 26, 9, 0, tzinfo=UTC)` and weekly sales on the 12 Mondays before 26 Oct 2026.

```python
async def test_split_two_stores_reconciles_to_sku(db_session, app_role_db, make_tenant):
    tenant = await make_tenant()
    sku = await _sku(db_session, tenant)
    await _weekly_sales(db_session, tenant, sku, 30, weeks=WINDOW, location="Boduppal")
    await _weekly_sales(db_session, tenant, sku, 10, weeks=WINDOW, location="Alwal")
    run = await _forecast(db_session, tenant, sku, completed=NOW, weekly_p50=40)
    await db_session.commit()

    async with app_role_db.session(str(tenant)) as s:
        summary = await split_run_by_location(s, tenant_id=tenant, industry="fashion",
                                              run_id=run, now=NOW)
        rows = (await s.execute(text(
            "SELECT l.code, f.forecast_date, f.p50, f.share_basis FROM location_forecast_results f "
            "JOIN locations l ON l.id = f.location_id WHERE f.run_id = :r"), {"r": str(run)})).all()

    assert summary.series == 2 and summary.degraded is False
    by_week = defaultdict(float)
    for code, d, p50, _ in rows:
        by_week[d] += float(p50)
    assert all(v == pytest.approx(40.0, abs=1e-3) for v in by_week.values())
    bod = [float(p50) for code, _, p50, _ in rows if code == "boduppal"]
    assert bod[0] == pytest.approx(30.0, abs=1e-3)


async def test_unassigned_over_five_percent_is_degraded(db_session, app_role_db, make_tenant):
    tenant = await make_tenant()
    sku = await _sku(db_session, tenant)
    await _weekly_sales(db_session, tenant, sku, 9, weeks=WINDOW, location="Alwal")
    await _weekly_sales(db_session, tenant, sku, 1, weeks=WINDOW, location=None)
    run = await _forecast(db_session, tenant, sku, completed=NOW, weekly_p50=10)
    await db_session.commit()
    async with app_role_db.session(str(tenant)) as s:
        summary = await split_run_by_location(s, tenant_id=tenant, industry="fashion",
                                              run_id=run, now=NOW)
    assert summary.degraded is True
    assert summary.unassigned_share == pytest.approx(0.1, abs=1e-6)


async def test_split_is_idempotent(db_session, app_role_db, make_tenant):
    tenant = await make_tenant()
    sku = await _sku(db_session, tenant)
    await _weekly_sales(db_session, tenant, sku, 5, weeks=WINDOW, location="Alwal")
    run = await _forecast(db_session, tenant, sku, completed=NOW, weekly_p50=5)
    await db_session.commit()
    count_sql = text("SELECT count(*) FROM location_forecast_results WHERE run_id = :r")
    async with app_role_db.session(str(tenant)) as s:
        await split_run_by_location(s, tenant_id=tenant, industry="fashion", run_id=run, now=NOW)
        first = await s.scalar(count_sql, {"r": str(run)})
        await split_run_by_location(s, tenant_id=tenant, industry="fashion", run_id=run, now=NOW)
        second = await s.scalar(count_sql, {"r": str(run)})
        run_row = await s.get(ForecastRun, run)
        again = await ensure_location_split(s, tenant_id=tenant, industry="fashion",
                                            run=run_row, now=NOW)
    assert first == second == 8
    assert again is None
```

Imports for this file: `from collections import defaultdict`, `import pytest`, `from sqlalchemy import text`, `from app.models.forecast import ForecastRun`, `from app.services.location_forecast import ensure_location_split, split_run_by_location`. Define `WINDOW = [date(2026, 10, 19) - timedelta(weeks=i) for i in range(12)]`. The `_forecast` helper copied from `test_inventory_coverage.py` writes 8 weekly rows, hence `== 8`.

- [ ] **Step 2: Run them and confirm they fail** (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `app/services/location_forecast.py`**

```python
"""Split a completed SKU forecast run across locations (location spec §4).

The SKU forecast stays authoritative; this writes share_split_v1 rows to
location_forecast_results and records coverage of the split on the run.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal as D

from sqlalchemy import delete, func, insert, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.calendar import current_week_start, week_bucket, week_start_instant
from app.models.enums import IndustryCode
from app.models.forecast import ForecastResult, ForecastRun
from app.models.location import LocationForecastResult
from app.models.product import Product, Sku
from app.models.sales import HistoricalSale
from app.services.decision_engine import DemandBand
from app.services.location_shares import (
    WINDOW_WEEKS, ShareResult, WeekObs, blend_shares, shares_from_obs, split_week,
)
from app.services.locations import load_locations, sync_locations

METHOD = "share_split_v1"
DEGRADED_UNASSIGNED_SHARE = 0.05


@dataclass
class SplitSummary:
    series: int
    excluded: list[dict[str, str]] = field(default_factory=list)
    unassigned_share: float = 0.0
    degraded: bool = False


async def split_run_by_location(
    session: AsyncSession, *, tenant_id: uuid.UUID, industry: str, run_id: uuid.UUID, now: datetime
) -> SplitSummary:
    ind = IndustryCode(industry)
    this_week = current_week_start(now)
    weeks = [this_week - timedelta(weeks=WINDOW_WEEKS - i) for i in range(WINDOW_WEEKS)]

    await sync_locations(session, tenant_id)
    loc_ids = {l.code: l.id for l in await load_locations(session, tenant_id) if l.is_active}

    fc = (await session.execute(
        select(ForecastResult.sku_id, ForecastResult.forecast_date,
               func.avg(ForecastResult.p10), func.avg(ForecastResult.p50),
               func.avg(ForecastResult.p90))
        .where(ForecastResult.tenant_id == tenant_id, ForecastResult.run_id == run_id)
        .group_by(ForecastResult.sku_id, ForecastResult.forecast_date)
    )).all()
    weekly: dict[uuid.UUID, list[tuple[date, float, float, float]]] = defaultdict(list)
    for sku_id, d, p10, p50, p90 in fc:
        weekly[sku_id].append((d, float(p10), float(p50), float(p90)))

    category = dict((await session.execute(
        select(Sku.id, Product.category).join(Product, Product.id == Sku.product_id)
        .where(Sku.tenant_id == tenant_id, Sku.id.in_(list(weekly)))
    )).all())

    bucket = week_bucket(HistoricalSale.sale_time).label("week")
    loc_key = func.lower(func.btrim(HistoricalSale.location)).label("loc")
    sales = (await session.execute(
        select(HistoricalSale.sku_id, bucket, loc_key,
               func.sum(HistoricalSale.units_sold).label("units"),
               func.bool_or(HistoricalSale.in_stock.is_(False)).label("oos"))
        .where(HistoricalSale.tenant_id == tenant_id, HistoricalSale.industry == ind,
               HistoricalSale.sale_time >= week_start_instant(weeks[0]),
               HistoricalSale.sale_time < week_start_instant(this_week))
        .group_by(HistoricalSale.sku_id, bucket, loc_key)
    )).all()

    sku_obs: dict[uuid.UUID, list[WeekObs]] = defaultdict(list)
    cat_obs: dict[str, list[WeekObs]] = defaultdict(list)
    total_units = unassigned_units = 0.0
    for r in sales:
        code = r.loc if r.loc and r.loc not in ("", "default") else None
        units = float(r.units or 0)
        wk = r.week.date() if isinstance(r.week, datetime) else r.week
        total_units += units
        if code is None:
            unassigned_units += units
        sku_obs[r.sku_id].append(WeekObs(wk, code, units, False if r.oos else None))
        cat = category.get(r.sku_id)
        if cat is not None:
            cat_obs[cat].append(WeekObs(wk, code, units, None))

    cat_shares: dict[str, ShareResult] = {c: shares_from_obs(o, weeks) for c, o in cat_obs.items()}

    await session.execute(delete(LocationForecastResult).where(
        LocationForecastResult.tenant_id == tenant_id, LocationForecastResult.run_id == run_id))

    rows: list[dict] = []
    series = 0
    excluded: list[dict[str, str]] = []
    for sku_id, band in weekly.items():
        own = shares_from_obs(sku_obs.get(sku_id, []), weeks)
        blended = blend_shares(own if own.shares else None, cat_shares.get(category.get(sku_id)))
        if not blended.shares:
            excluded.append({"sku_id": str(sku_id),
                             "reason": "No sales history for this SKU or its category"})
            continue
        for code, share in blended.shares.items():
            loc_id = loc_ids.get(code)
            if loc_id is None:
                continue
            series += 1
            for d, p10, p50, p90 in band:
                lp10, lp50, lp90 = split_week(p10, p50, p90, share)
                rows.append({
                    "id": uuid.uuid4(), "tenant_id": tenant_id, "run_id": run_id,
                    "sku_id": sku_id, "location_id": loc_id, "forecast_date": d,
                    "p10": D(str(round(lp10, 4))), "p50": D(str(round(lp50, 4))),
                    "p90": D(str(round(lp90, 4))), "share": D(str(round(share, 6))),
                    "share_basis": blended.basis[code], "method": METHOD,
                })
    for start in range(0, len(rows), 5000):
        await session.execute(insert(LocationForecastResult), rows[start : start + 5000])

    unassigned_share = unassigned_units / total_units if total_units > 0 else 0.0
    summary = SplitSummary(series=series, excluded=excluded,
                           unassigned_share=round(unassigned_share, 6),
                           degraded=unassigned_share > DEGRADED_UNASSIGNED_SHARE)
    await session.execute(
        text("UPDATE forecast_runs SET metrics = metrics || CAST(:m AS jsonb) WHERE id = :r"),
        {"r": str(run_id), "m": __import__("json").dumps({
            "location_series": summary.series, "location_excluded": len(excluded),
            "unassigned_share": summary.unassigned_share,
            "location_degraded": summary.degraded})},
    )
    return summary


async def ensure_location_split(
    session: AsyncSession, *, tenant_id: uuid.UUID, industry: str, run: ForecastRun, now: datetime
) -> SplitSummary | None:
    exists = await session.scalar(
        select(LocationForecastResult.id).where(
            LocationForecastResult.tenant_id == tenant_id,
            LocationForecastResult.run_id == run.id).limit(1))
    if exists is not None:
        return None
    return await split_run_by_location(session, tenant_id=tenant_id, industry=industry,
                                       run_id=run.id, now=now)


async def location_bands(
    session: AsyncSession, tenant_id: uuid.UUID, run_id: uuid.UUID, now: datetime
) -> dict[tuple[uuid.UUID, uuid.UUID], DemandBand]:
    rows = (await session.execute(
        select(LocationForecastResult.sku_id, LocationForecastResult.location_id,
               LocationForecastResult.p10, LocationForecastResult.p50, LocationForecastResult.p90)
        .where(LocationForecastResult.tenant_id == tenant_id,
               LocationForecastResult.run_id == run_id,
               LocationForecastResult.forecast_date >= current_week_start(now))
        .order_by(LocationForecastResult.sku_id, LocationForecastResult.location_id,
                  LocationForecastResult.forecast_date)
    )).all()
    acc: dict[tuple[uuid.UUID, uuid.UUID], tuple[list, list, list]] = {}
    for sku_id, loc_id, p10, p50, p90 in rows:
        b = acc.setdefault((sku_id, loc_id), ([], [], []))
        b[0].append(float(p10)); b[1].append(float(p50)); b[2].append(float(p90))
    return {k: DemandBand(p10=v[0], p50=v[1], p90=v[2]) for k, v in acc.items()}
```

Replace `__import__("json")` with a normal `import json` at the top; the inline form only keeps the excerpt short. Check `week_bucket` returns a timestamp: `coverage.py` calls `r.week.date()`, so handle both shapes as shown.

- [ ] **Step 4: Hook it into the snapshot.** In `hybrid_forecast._persist_accuracy_snapshot`, after the `for s in out.series:` loop and before `await session.commit()`:

```python
            await session.flush()
            try:
                async with session.begin_nested():
                    from app.services.location_forecast import split_run_by_location

                    await split_run_by_location(
                        session, tenant_id=tenant_id, industry=industry_code,
                        run_id=run_row_id, now=datetime.now(UTC),
                    )
            except Exception as exc:  # pragma: no cover - never lose the SKU snapshot
                log.warning("hybrid.run.location_split_failed", error=str(exc))
```

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `cd backend && uv run pytest tests/test_location_forecast_split.py tests/test_location_shares.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/location_forecast.py backend/app/services/hybrid_forecast.py backend/tests/test_location_forecast_split.py
git commit -m "feat(forecast): split completed runs into per-location forecasts"
```

### Task 9: Coverage uses the location forecast

**Files:**
- Modify: `backend/app/services/coverage.py` (the per-location loop starting ~line 212, `for lvl in sorted(levels, ...)`)
- Test: `backend/tests/test_inventory_coverage.py` (add a test)

**Interfaces:**
- Consumes: the `location_forecast_results` + `locations` tables.
- Produces: each location entry gains `"demand_basis": "forecast" | "trailing_actuals" | None`.

- [ ] **Step 1: Write the failing test.** Add it to `test_inventory_coverage.py`, using the existing helpers there:
  - Two stores, each selling 5/week in trailing actuals.
  - A fresh run whose location rows give Boduppal p50 = 20/week. Insert a `locations` row and `location_forecast_results` rows directly with SQL.
  - Assert Boduppal's location entry has `demand_basis == "forecast"` and `cover_days` computed from 20/week.
  - Assert Alwal, with no location rows, has `demand_basis == "trailing_actuals"`.

- [ ] **Step 2: Run it and confirm it fails** (`KeyError: 'demand_basis'`).

- [ ] **Step 3: Implement.** Inside `coverage()`, in the `if is_run_fresh(run, now):` branch, also load:

```python
        loc_rows = (
            await session.execute(
                text(
                    "SELECT f.sku_id, l.code, avg(f.p50) AS p50 FROM location_forecast_results f "
                    "JOIN locations l ON l.id = f.location_id "
                    "WHERE f.tenant_id = :t AND f.run_id = :r AND f.forecast_date >= :w "
                    "AND f.forecast_date < :w4 GROUP BY f.sku_id, l.code"
                ),
                {"t": str(tenant_id), "r": str(run.id), "w": this_week,
                 "w4": this_week + timedelta(weeks=FORECAST_WEEKS)},
            )
        ).all()
        loc_forecast_weekly = {(r.sku_id, r.code): float(r.p50 or 0) for r in loc_rows}
```

Initialise `loc_forecast_weekly: dict = {}` before the `if`, and add `text` to the sqlalchemy import. In the per-location loop, look up `key = (sku_id, lvl.location.strip().lower())`:
- If the key is in `loc_forecast_weekly`, use that weekly value instead of the trailing mean, set `demand_basis = "forecast"`, and say so in the reason text ("Mean P50 of the next 4 location forecast weeks.").
- Otherwise keep the existing trailing-actuals logic and set `demand_basis = "trailing_actuals"`, or `None` when it has no basis.

Add `"demand_basis"` to the location dict.

- [ ] **Step 4: Run the whole coverage file and confirm it passes**

Run: `cd backend && uv run pytest tests/test_inventory_coverage.py -v`
Expected: all PASS. The existing assertions must still hold.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/coverage.py backend/tests/test_inventory_coverage.py
git commit -m "feat(inventory): location cover from the location forecast when fresh"
```

### Task 10: Location forecast accuracy (MASE)

**Files:**
- Modify: `backend/app/services/forecast_accuracy.py` (add a function; do not change `compute_accuracy`'s existing output keys)
- Modify: the router that serves `GET /forecast/accuracy` (`grep -rn "compute_accuracy" backend/app/routers`) — add `"locations": await compute_location_accuracy(...)` to its response
- Test: `backend/tests/test_location_accuracy.py`

**Interfaces:**
- Produces:
  - `mase(actual: list[float], forecast: list[float], history: list[float], season: int) -> float | None` — the scale is the mean absolute seasonal difference of `history` (lag `season`, falling back to lag 1 when `len(history) <= season`); returns `None` when the scale is 0 or there is no data.
  - `async compute_location_accuracy(session, *, tenant_id, industry, run_id) -> dict` returning
    `{"method": "share_split_v1", "weighted_mase": float | None, "locations": [{"location": code, "mase": float | None, "units": float, "weeks": int}]}`.

- [ ] **Step 1: Write the failing tests**

```python
from app.services.forecast_accuracy import mase


def test_mase_perfect_forecast_is_zero():
    assert mase([5, 6], [5, 6], history=[1, 2, 3, 4, 5], season=1) == 0.0


def test_mase_equals_naive_is_one():
    hist = [1, 2, 3, 4, 5]
    assert mase([7], [6], history=hist, season=1) == 1.0


def test_mase_flat_history_is_undefined():
    assert mase([1], [2], history=[3, 3, 3], season=1) is None
```

Also add one DB test: the 12-week + 2-week-ahead setup from Task 8, plus actual sales for the 2 forecast weeks at each location. Assert `compute_location_accuracy` returns two locations with non-`None` MASE and `weighted_mase` equal to the unit-weighted mean of the two.

- [ ] **Step 2: Run them and confirm they fail.**

- [ ] **Step 3: Implement**

```python
def mase(actual: list[float], forecast: list[float], history: list[float], season: int) -> float | None:
    """Mean absolute scaled error against an in-sample seasonal-naive scale."""
    if not actual or len(actual) != len(forecast):
        return None
    lag = season if len(history) > season else 1
    diffs = [abs(history[i] - history[i - lag]) for i in range(lag, len(history))]
    scale = sum(diffs) / len(diffs) if diffs else 0.0
    if scale <= 0:
        return None
    mae = sum(abs(a - f) for a, f in zip(actual, forecast, strict=True)) / len(actual)
    return round(mae / scale, 4)
```

`compute_location_accuracy`:
- Load location forecast p50 per (location, week) for `run_id`, summed over SKUs, for weeks that have actuals (weeks before `current_week_start()`).
- Load actuals per (location code, week) from `historical_sales` for those weeks.
- Load history per location for the 104 weeks before the first forecast week.
- Call `mase(..., season=52)`.
- `weighted_mase` = Σ(mase × units) / Σ units over locations where mase is not `None`.
- Return locations sorted by code.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `cd backend && uv run pytest tests/test_location_accuracy.py tests/test_forecast_accuracy.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/forecast_accuracy.py backend/app/routers backend/tests/test_location_accuracy.py
git commit -m "feat(accuracy): per-location MASE for share_split_v1 forecasts"
```

---

## Phase 3 — allocation

### Task 11: Pure DC→store allocation

**Files:**
- Create: `backend/app/services/allocation.py`
- Test: `backend/tests/test_allocation.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True, slots=True) StoreNeed(location: str, position: float, target: float, daily_rate: float)` with property `need = max(0, target − position)`
  - `allocate(stores: list[StoreNeed], supply: float, moq: int = 1, min_units: int = 1) -> dict[str, int]` — units per store; stores with 0 are omitted
  - `cover_level(stores, supply) -> float` — the water-filling level T in days

- [ ] **Step 1: Write the failing tests**

```python
"""DC→store allocation (spec §5.2). Pure."""
from __future__ import annotations

import pytest
from hypothesis import given, strategies as st

from app.services.allocation import StoreNeed, allocate


def test_surplus_ships_exact_needs():
    stores = [StoreNeed("a", 10, 30, 2.0), StoreNeed("b", 0, 12, 1.0)]
    assert allocate(stores, supply=100) == {"a": 20, "b": 12}


def test_shortage_equalises_cover():
    stores = [StoreNeed("a", 0, 100, 2.0), StoreNeed("b", 0, 100, 1.0)]
    out = allocate(stores, supply=30)
    assert out == {"a": 20, "b": 10}          # both reach 10 days of cover


def test_shortage_tops_up_the_lowest_first():
    stores = [StoreNeed("a", 20, 100, 1.0), StoreNeed("b", 0, 100, 1.0)]
    assert allocate(stores, supply=10) == {"b": 10}


def test_zero_rate_store_gets_nothing_in_shortage():
    stores = [StoreNeed("a", 0, 50, 1.0), StoreNeed("b", 0, 50, 0.0)]
    assert allocate(stores, supply=10) == {"a": 10}


def test_rounds_to_pack_without_exceeding_supply():
    stores = [StoreNeed("a", 0, 7, 1.0), StoreNeed("b", 0, 7, 1.0)]
    out = allocate(stores, supply=10, moq=4)
    assert sum(out.values()) <= 10
    assert all(v % 4 == 0 for v in out.values())


def test_min_units_drops_tiny_lines():
    stores = [StoreNeed("a", 0, 1, 1.0), StoreNeed("b", 0, 20, 1.0)]
    assert allocate(stores, supply=100, min_units=2) == {"b": 20}


def test_no_supply_no_allocation():
    assert allocate([StoreNeed("a", 0, 10, 1.0)], supply=0) == {}


@given(
    st.lists(st.tuples(st.floats(0, 200), st.floats(0, 400), st.floats(0, 20)), min_size=1, max_size=8),
    st.floats(0, 1000), st.integers(1, 12),
)
def test_never_exceeds_supply_or_need(raw, supply, moq):
    stores = [StoreNeed(f"s{i}", p, t, r) for i, (p, t, r) in enumerate(raw)]
    out = allocate(stores, supply=supply, moq=moq)
    assert sum(out.values()) <= int(supply)
    need = {s.location: s.need for s in stores}
    for loc, units in out.items():
        assert units % moq == 0
        assert units <= need[loc] + moq    # rounding to a pack may pass need by < 1 pack
```

If `hypothesis` is not in the backend dev dependencies (`grep hypothesis backend/pyproject.toml`), add it with `cd backend && uv add --dev hypothesis` and commit `pyproject.toml` and `uv.lock` with this task.

- [ ] **Step 2: Run them and confirm they fail.**

- [ ] **Step 3: Implement `app/services/allocation.py`**

```python
"""DC→store allocation (location spec §5.2). Pure.

Every store is lifted toward its target. When the DC cannot cover every need,
stock is rationed by equal days of cover (water-filling) so no store runs out
first; quantities are packs (``moq``) and never exceed supply.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StoreNeed:
    location: str
    position: float
    target: float
    daily_rate: float

    @property
    def need(self) -> float:
        return max(0.0, self.target - self.position)


def _fill(s: StoreNeed, level: float) -> float:
    return min(s.need, max(0.0, level * s.daily_rate - s.position))


def cover_level(stores: list[StoreNeed], supply: float) -> float:
    live = [s for s in stores if s.daily_rate > 0 and s.need > 0]
    if not live:
        return 0.0
    lo, hi = 0.0, max((s.position + s.need) / s.daily_rate for s in live)
    for _ in range(100):
        mid = (lo + hi) / 2
        if sum(_fill(s, mid) for s in live) > supply:
            hi = mid
        else:
            lo = mid
    return lo


def _round(raw: dict[str, float], cap: int, moq: int) -> dict[str, int]:
    base = {k: int(math.floor(v / moq)) * moq for k, v in raw.items()}
    left = (cap - sum(base.values())) // moq
    for k in sorted(raw, key=lambda k: raw[k] - base[k], reverse=True):
        if left <= 0:
            break
        if raw[k] - base[k] > 0:
            base[k] += moq
            left -= 1
    return base


def allocate(
    stores: list[StoreNeed], supply: float, moq: int = 1, min_units: int = 1
) -> dict[str, int]:
    moq = max(1, int(moq))
    cap = max(0, int(math.floor(supply)))
    if cap == 0:
        return {}
    needs = {s.location: s.need for s in stores if s.need > 0}
    rounded_up = {k: int(math.ceil(v / moq)) * moq for k, v in needs.items()}
    if sum(rounded_up.values()) <= cap:
        out = rounded_up
    else:
        level = cover_level(stores, cap)
        raw = {s.location: _fill(s, level) for s in stores if s.daily_rate > 0 and s.need > 0}
        out = _round(raw, cap, moq)
    return {k: v for k, v in out.items() if v > 0 and v >= min_units}
```

Check `test_shortage_equalises_cover` by hand: with supply 30 the level is T = 10, so a = 20 and b = 10, which are already whole. Check `test_surplus_ships_exact_needs`: the needs are 20 and 12, summing to 32 ≤ 100.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `cd backend && uv run pytest tests/test_allocation.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/allocation.py backend/tests/test_allocation.py backend/pyproject.toml backend/uv.lock
git commit -m "feat(planning): DC-to-store allocation with equal-cover rationing"
```

### Task 12: Ledger support for location decisions

**Files:**
- Create: `backend/alembic/versions/0027_recommendation_locations.py`
- Modify: `backend/app/models/enums.py` (`DecisionKind`), `backend/app/models/recommendation.py`, `backend/app/services/decision_engine.py` (`Decision`), `backend/app/services/decision_builder.py` (`persist_decisions`, `serialize`, `load_policy`), `backend/app/services/decision_engine.py` (`PolicyConfig`), `backend/app/routers/decisions.py` (`_serialize`)
- Test: `backend/tests/test_location_decisions_ledger.py`

**Interfaces:**
- Produces:
  - `DecisionKind.allocation = "allocation"` and `DecisionKind.transfer = "transfer"`.
  - `Recommendation.location_id` and `Recommendation.source_location_id`, both `uuid | None`.
  - `Decision.location_id: str | None = None` and `Decision.source_location_id: str | None = None`; the last two fields, also present in `as_dict()`.
  - `PolicyConfig` gains `min_allocation_units: int = 1`, `min_transfer_units: int = 2`, `transfer_lead_time_days: int = 2`, `transfer_cost_per_unit: float | None = None`, all read by `load_policy`.
  - Serialised decisions gain `location_id`, `source_location_id`, `location_code` and `source_location_code`.

- [ ] **Step 1: Write the failing tests.** All four are required.
  - **(a)** `persist_decisions` with two `allocation` decisions for the same SKU and different `location_id` both persist as `open`. This proves the unique index includes the location.
  - **(b)** Two `purchase_order` decisions for the same SKU still violate the open-unique index (`IntegrityError`), so the old guarantee is kept.
  - **(c)** `load_policy({"decisions": {"min_transfer_units": 5, "transfer_cost_per_unit": 12.5}})` returns those values; `load_policy(None).transfer_cost_per_unit is None`.
  - **(d)** The ROI service ignores allocation and transfer rows. Persist one accepted `allocation` and call the ROI summary function used by `GET /roi` (find it with `grep -n "_is_po" backend/app/services/roi.py`). Assert that the working-capital figures are unchanged from an empty ledger.

- [ ] **Step 2: Run them and confirm they fail.**

- [ ] **Step 3: Write the migration**

```python
"""Location-aware decisions: allocation / transfer kinds, origin + destination.

The open-queue uniqueness moves from (tenant, sku, kind) to (tenant, sku, kind,
destination, origin): one SKU legitimately has one allocation per store.

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ZERO = "'00000000-0000-0000-0000-000000000000'::uuid"


def upgrade() -> None:
    op.add_column("recommendations", sa.Column("location_id", postgresql.UUID(as_uuid=True)))
    op.add_column("recommendations",
                  sa.Column("source_location_id", postgresql.UUID(as_uuid=True)))
    op.create_foreign_key("fk_recommendations_location", "recommendations", "locations",
                          ["location_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_recommendations_source_location", "recommendations", "locations",
                          ["source_location_id"], ["id"], ondelete="SET NULL")
    op.drop_constraint("ck_recommendations_kind", "recommendations", type_="check")
    op.create_check_constraint(
        "ck_recommendations_kind", "recommendations",
        "kind IN ('purchase_order', 'excess_stock', 'safety_stock_update', 'allocation', 'transfer')",
    )
    op.execute("DROP INDEX IF EXISTS uq_recommendations_open_per_sku_kind")
    op.execute(
        "CREATE UNIQUE INDEX uq_recommendations_open_per_sku_kind_loc ON recommendations "
        f"(tenant_id, sku_id, kind, COALESCE(location_id, {_ZERO}), "
        f"COALESCE(source_location_id, {_ZERO})) WHERE status = 'open'"
    )
    op.create_index("ix_recommendations_tenant_kind_source", "recommendations",
                    ["tenant_id", "kind", "source_location_id"])


def downgrade() -> None:
    op.drop_index("ix_recommendations_tenant_kind_source", table_name="recommendations")
    op.execute("DROP INDEX IF EXISTS uq_recommendations_open_per_sku_kind_loc")
    op.execute("DELETE FROM recommendations WHERE kind IN ('allocation', 'transfer')")
    op.execute(
        "CREATE UNIQUE INDEX uq_recommendations_open_per_sku_kind "
        "ON recommendations (tenant_id, sku_id, kind) WHERE status = 'open'"
    )
    op.drop_constraint("ck_recommendations_kind", "recommendations", type_="check")
    op.create_check_constraint(
        "ck_recommendations_kind", "recommendations",
        "kind IN ('purchase_order', 'excess_stock', 'safety_stock_update')",
    )
    op.drop_constraint("fk_recommendations_source_location", "recommendations", type_="foreignkey")
    op.drop_constraint("fk_recommendations_location", "recommendations", type_="foreignkey")
    op.drop_column("recommendations", "source_location_id")
    op.drop_column("recommendations", "location_id")
```

- [ ] **Step 4: Update the code**
  - `enums.py` `DecisionKind`: add `allocation = "allocation"` and `transfer = "transfer"`.
  - `recommendation.py`: add `location_id` and `source_location_id` as `Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("locations.id", ondelete="SET NULL"))`.
  - `decision_engine.Decision`: append `location_id: str | None = None` and `source_location_id: str | None = None` after `inputs`, and add both keys to `as_dict()`.
  - `decision_engine.PolicyConfig`: append the four fields with the defaults above.
  - `decision_builder.load_policy`: read the four keys. Use `int(...)` for the units and lead time, and for `transfer_cost_per_unit` use `None if raw.get(...) is None else float(raw[...])`.
  - `decision_builder.persist_decisions`: pass `location_id=uuid.UUID(d.location_id) if d.location_id else None` and `source_location_id` the same way.
  - `decision_builder.serialize` and `routers/decisions._serialize`: add `location_id` and `source_location_id` (as strings or `None`). In `routers/decisions.list_decisions`, load `{id: code}` for the referenced location ids and add `location_code` and `source_location_code`.
  - `roi.py`: `_is_po` already restricts to `purchase_order`. Change nothing there; the test from step 1 (d) proves it.

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `cd backend && uv run pytest tests/test_location_decisions_ledger.py tests/test_decision_engine.py tests/test_decision_expiry.py tests/test_roi_tiers.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/0027_recommendation_locations.py backend/app/models backend/app/services/decision_engine.py backend/app/services/decision_builder.py backend/app/routers/decisions.py backend/tests/test_location_decisions_ledger.py
git commit -m "feat(decisions): location-aware ledger with allocation and transfer kinds"
```

### Task 13: Build allocation decisions in the refresh

**Files:**
- Create: `backend/app/services/network_decisions.py`
- Modify: `backend/app/services/decision_builder.py` (`build_decisions`: collect confidence per SKU; call the network builder after the per-SKU loop; `refresh` calls `ensure_location_split` before `build_decisions`)
- Test: `backend/tests/test_network_decisions_allocation.py`

**Interfaces:**
- Consumes: Task 4 (`load_locations`, `network_readiness`), Task 8 (`location_bands`, `ensure_location_split`), Task 11 (`StoreNeed`, `allocate`), Task 12 (`Decision` fields, `PolicyConfig` fields); `decision_engine._window_sum`, `_pooled_sigma`, `_z_for`, `_money`; `planning_inputs.stock_is_stale`.
- Produces:
  - `@dataclass NetworkBuild(decisions: list[Decision], skipped: list[dict[str, str]], notes: list[str])`
  - `async build_network_decisions(session, *, tenant_id, industry: str, run: ForecastRun, skus: dict[uuid.UUID, Sku], levels: dict[uuid.UUID, list[InventoryLevel]], confidence: dict[uuid.UUID, tuple[int, str]], policy: PolicyConfig, now: datetime, include_transfers: bool = True) -> NetworkBuild` — this task builds allocations only; Task 15 adds transfers.
  - `BuildResult` gains `notes: list[str] = field(default_factory=list)`, which carries readiness messages to the API.

- [ ] **Step 1: Write the failing tests.** Build the synthetic fixture: 1 DC + 6 stores, all `source='synthetic_test'`, never in the demo seed.
  - Insert `locations` rows directly: DC with `kind='warehouse'`; stores with `kind='store'`, parent = DC, lead time 3 days.
  - Insert 1 SKU (`moq = 1`, `unit_cost = 400`, `unit_price = 960`).
  - Insert fresh inventory: DC 100 available; stores 0, 0, 5, 5, 20, 40.
  - Insert a fresh `forecast_runs` row and `location_forecast_results` with weekly p50 per store 14, 14, 7, 7, 7, 7 and p10/p90 at ±30%.
  - Policy: `review_period_days = 7`, service level 0.97.

  Tests:
  1. **Surplus:** with DC 1000, each store gets `ceil(target − position)`, where target = Σ p50 over 10 days + z·σ. Compute the expected values in the test with the same `_window_sum` / `_pooled_sigma` helpers, imported from `decision_engine`.
  2. **Shortage:** with DC 100, Σ allocation ≤ 100 and the projected days of cover `(position + alloc) / daily_rate` across stores that received stock differ by at most 1 day + 1 unit / rate.
  3. **Not ready:** with no warehouse confirmed (the DC row `kind='unconfirmed'`), there are no allocation decisions, and `notes` contains `"No warehouse is defined"`.
  4. **Stale:** with a store's stock 30 days old, that store is in `skipped` with a stale reason and receives nothing.
  5. **Ledger:** after `refresh(...)`, `recommendations` holds `kind='allocation'` rows with `source_location_id` = DC and `location_id` = the store.

- [ ] **Step 2: Run them and confirm they fail.**

- [ ] **Step 3: Implement `network_decisions.py`.** The allocation part, per SKU:

```python
"""Allocation (DC→store) and transfer (store↔store) decisions (location spec §5–§6).

Inputs are the run's location forecasts, current stock per location and the
confirmed network. Nothing is assumed: an unready network, a stale stock row or
a location without a forecast produces a note or a skipped entry, not a number.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import DecisionKind, LocationKind
from app.models.forecast import ForecastRun
from app.models.inventory import InventoryLevel
from app.models.product import Sku
from app.services.allocation import StoreNeed, allocate
from app.services.decision_engine import (
    Decision, DemandBand, PolicyConfig, Reason, _money, _pooled_sigma, _window_sum, _z_for,
)
from app.services.location_forecast import location_bands
from app.services.locations import load_locations, network_readiness
from app.services.planning_inputs import stock_is_stale


@dataclass
class NetworkBuild:
    decisions: list[Decision] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _position(rows: list[InventoryLevel]) -> float:
    return sum(float(r.available_units) + max(0.0, float(r.inbound_units or 0)) for r in rows)


def _target(band: DemandBand, days: float, z: float) -> float:
    return _window_sum(band.p50, days) + z * _pooled_sigma(band, days)


async def build_network_decisions(
    session: AsyncSession, *, tenant_id: uuid.UUID, industry: str, run: ForecastRun,
    skus: dict[uuid.UUID, Sku], levels: dict[uuid.UUID, list[InventoryLevel]],
    confidence: dict[uuid.UUID, tuple[int, str]], policy: PolicyConfig, now: datetime,
    include_transfers: bool = True,
) -> NetworkBuild:
    out = NetworkBuild()
    locs = [l for l in await load_locations(session, tenant_id) if l.is_active]
    if not locs:
        return out
    ready = network_readiness(locs)
    if not ready.allocation_ready:
        out.notes = list(ready.missing)  # once per refresh, not per SKU
    by_code = {l.code: l for l in locs}
    bands = await location_bands(session, tenant_id, run.id, now)
    z = _z_for(policy.service_level)

    for sku_id, sku in skus.items():
        rows_by_code: dict[str, list[InventoryLevel]] = {}
        for lvl in levels.get(sku_id, []):
            code = (lvl.location or "").strip().lower()
            if code in by_code:
                rows_by_code.setdefault(code, []).append(lvl)
        conf, band_label = confidence.get(sku_id, (0, "insufficient"))

        if ready.allocation_ready:
            for dc in (l for l in locs if l.kind == LocationKind.warehouse):
                dc_rows = rows_by_code.get(dc.code, [])
                if not dc_rows or any(stock_is_stale(r.as_of, now) for r in dc_rows):
                    out.skipped.append({"sku_code": sku.sku_code,
                                        "reason": f"Stock at {dc.name} is missing or stale"})
                    continue
                dc_band = bands.get((sku_id, dc.id))
                dc_own = _window_sum(dc_band.p50, policy.review_period_days) if dc_band else 0.0
                supply = max(0.0, sum(float(r.available_units) for r in dc_rows) - dc_own)

                needs: list[StoreNeed] = []
                meta: dict[str, tuple] = {}
                for st in (l for l in locs if l.kind == LocationKind.store
                           and l.parent_location_id == dc.id):
                    rows = rows_by_code.get(st.code, [])
                    band = bands.get((sku_id, st.id))
                    if band is None:
                        out.skipped.append({"sku_code": sku.sku_code,
                                            "reason": f"No location forecast for {st.name}"})
                        continue
                    if not rows or any(stock_is_stale(r.as_of, now) for r in rows):
                        out.skipped.append({"sku_code": sku.sku_code,
                                            "reason": f"Stock at {st.name} is missing or stale"})
                        continue
                    days = float((st.lead_time_days_from_parent or 0) + policy.review_period_days)
                    pos = _position(rows)
                    tgt = _target(band, days, z)
                    rate = _window_sum(band.p50, days) / days if days > 0 else 0.0
                    needs.append(StoreNeed(st.code, pos, tgt, rate))
                    meta[st.code] = (st, days, pos, tgt, rate)

                alloc = allocate(needs, supply, moq=int(sku.moq or 1),
                                 min_units=policy.min_allocation_units)
                level = None
                for code, units in alloc.items():
                    st, days, pos, tgt, rate = meta[code]
                    cover_after = (pos + units) / rate if rate > 0 else None
                    out.decisions.append(Decision(
                        kind=DecisionKind.allocation, sku_id=str(sku_id), sku_code=sku.sku_code,
                        headline=f"Send {units} × {sku.sku_code} from {dc.name} to {st.name}",
                        recommended_units=units,
                        baseline_units=0,  # replaced by the "replace last period's sales" baseline below
                        urgency="high" if rate > 0 and pos / rate < days else "normal",
                        confidence=conf, confidence_band=band_label,
                        reasons=[Reason("store_target",
                                        f"{st.name} needs {tgt:.0f} units for the next {days:.0f} "
                                        f"days and holds {pos:.0f}.", tgt - pos)],
                        economics={"currency": sku.currency or "INR",
                                   "stock_value_moved": _money(units * float(sku.unit_cost or 0),
                                                               sku.unit_cost is not None)},
                        inputs={"window_days": days, "position": pos, "target": tgt,
                                "daily_rate": rate, "dc_supply": supply,
                                "cover_after_days": cover_after, "share_method": "share_split_v1",
                                "unit_cost": float(sku.unit_cost) if sku.unit_cost is not None else None,
                                "unit_price": float(sku.unit_price) if sku.unit_price is not None else None},
                        location_id=str(st.id), source_location_id=str(dc.id),
                    ))
    return out
```

- **Baseline (spec §5.3):** after the allocations for one DC are built, compute each store's units sold in the last `policy.review_period_days`. Query `historical_sales` once per refresh, grouped by `(sku_id, lower(btrim(location)))`. If their sum exceeds `supply`, scale them down proportionally and floor. Set `baseline_units` on each decision with `dataclasses.replace`. Put this in a helper `_baseline_units(...)` in the same file, and test it in test 1.
- **Urgency:** `Urgency` is a type in `decision_engine`. Use its values (`"critical" | "high" | "normal" | "low"`) exactly as `decision_engine._urgency` returns them; read that function first.

- [ ] **Step 4: Wire it into `decision_builder`**
  - In `build_decisions`, inside the per-SKU loop, store `conf_by_sku[sku_id] = (confidence.score, confidence.band)`. Check the attribute names on `ConfidenceScore` in `app/services/forecast_confidence.py` first.
  - After the loop, call `net = await build_network_decisions(session, tenant_id=tenant_id, industry=industry, run=run, skus=skus, levels=by_sku, confidence=conf_by_sku, policy=policy, now=now)`.
  - Then `decisions.extend(net.decisions)` and `skipped.extend(net.skipped)`, and set `notes=net.notes` on the `BuildResult`.
  - Note that SKUs skipped for stale *pooled* stock are still passed to the network builder, which skips per location itself.
  - In `refresh`, before `build_decisions`, add:

    ```python
    run = await latest_completed_run(session, tenant_id, IndustryCode(industry))
    if run is not None and is_run_fresh(run, now):
        await ensure_location_split(session, tenant_id=tenant_id, industry=industry, run=run, now=now)
    ```
  - In `routers/decisions.refresh_decisions`, include `notes` in the response next to `skipped`.

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `cd backend && uv run pytest tests/test_network_decisions_allocation.py tests/test_decision_readiness.py tests/test_decision_expiry.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/network_decisions.py backend/app/services/decision_builder.py backend/app/routers/decisions.py backend/tests/test_network_decisions_allocation.py
git commit -m "feat(decisions): DC-to-store allocation recommendations"
```

---

## Phase 4 — transfers

### Task 14: Pure transfer matching

**Files:**
- Create: `backend/app/services/transfers.py`
- Test: `backend/tests/test_transfers.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True, slots=True) TransferSite(location: str, position: float, window_p50: float, window_p90: float, daily_rate: float, lead_from_parent: int | None, fresh: bool, allocated: int = 0)`
  - `@dataclass(frozen=True, slots=True) Transfer(source: str, destination: str, units: int, deficit: float, excess: float)`
  - `match_transfers(sites: list[TransferSite], *, transfer_lead_days: int, moq: int = 1, min_units: int = 2) -> list[Transfer]`

- [ ] **Step 1: Write the failing tests**

```python
"""Store↔store transfers (spec §6). Pure."""
from __future__ import annotations

from hypothesis import given, strategies as st

from app.services.transfers import TransferSite, match_transfers


def site(loc, pos, p50, p90, rate, lead=5, fresh=True, allocated=0):
    return TransferSite(loc, pos, p50, p90, rate, lead, fresh, allocated)


def test_moves_excess_to_a_store_running_out():
    sites = [site("r", 2, 20, 30, 2.0), site("d", 60, 10, 15, 1.0)]
    [t] = match_transfers(sites, transfer_lead_days=2)
    assert (t.source, t.destination, t.units) == ("d", "r", 18)


def test_donor_keeps_its_p90():
    sites = [site("r", 0, 100, 120, 10.0), site("d", 40, 10, 30, 1.0)]
    [t] = match_transfers(sites, transfer_lead_days=2)
    assert t.units == 10                       # 40 − 30


def test_no_transfer_when_dc_delivery_is_as_fast():
    sites = [site("r", 2, 20, 30, 2.0, lead=2), site("d", 60, 10, 15, 1.0)]
    assert match_transfers(sites, transfer_lead_days=2) == []


def test_no_transfer_when_receiver_cover_outlasts_dc_lead_time():
    sites = [site("r", 15, 20, 30, 2.0, lead=5), site("d", 60, 10, 15, 1.0)]   # 7.5 days ≥ 5
    assert match_transfers(sites, transfer_lead_days=2) == []


def test_stale_and_allocated_donors_excluded():
    sites = [site("r", 0, 20, 30, 2.0), site("d1", 60, 10, 15, 1.0, fresh=False),
             site("d2", 60, 10, 15, 1.0, allocated=5)]
    assert match_transfers(sites, transfer_lead_days=2) == []


def test_min_units():
    sites = [site("r", 19, 20, 30, 2.0, lead=20), site("d", 60, 10, 15, 1.0)]
    assert match_transfers(sites, transfer_lead_days=2, min_units=2) == []


def test_most_urgent_receiver_served_first():
    sites = [site("r1", 5, 20, 30, 1.0), site("r2", 0, 20, 30, 1.0), site("d", 35, 10, 15, 1.0)]
    out = match_transfers(sites, transfer_lead_days=2)
    assert out[0].destination == "r2" and out[0].units == 20


@given(st.lists(st.tuples(st.floats(0, 100), st.floats(0, 60), st.floats(0, 40),
                          st.floats(0.1, 10), st.integers(0, 10)), min_size=2, max_size=7))
def test_invariants(raw):
    sites = [TransferSite(f"s{i}", p, a, a + b, r, l, True) for i, (p, a, b, r, l) in enumerate(raw)]
    out = match_transfers(sites, transfer_lead_days=1)
    given_by = {}
    for t in out:
        given_by[t.source] = given_by.get(t.source, 0) + t.units
    by_loc = {s.location: s for s in sites}
    for src, units in given_by.items():
        assert by_loc[src].position - units >= by_loc[src].window_p90 - 1e-9
    assert not ({t.source for t in out} & {t.destination for t in out})
```

- [ ] **Step 2: Run them and confirm they fail.**

- [ ] **Step 3: Implement `app/services/transfers.py`**

```python
"""Store↔store transfers (location spec §6). Pure.

Only when the DC cannot fix a shortage in time: the receiver runs out before its
next DC delivery and a faster store-to-store move exists. Donors keep their own
p90 demand for the window, are fresh, and receive nothing this cycle.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TransferSite:
    location: str
    position: float
    window_p50: float
    window_p90: float
    daily_rate: float
    lead_from_parent: int | None
    fresh: bool
    allocated: int = 0


@dataclass(frozen=True, slots=True)
class Transfer:
    source: str
    destination: str
    units: int
    deficit: float
    excess: float


def match_transfers(
    sites: list[TransferSite], *, transfer_lead_days: int, moq: int = 1, min_units: int = 2
) -> list[Transfer]:
    moq = max(1, int(moq))
    receivers: list[tuple[float, TransferSite, float]] = []
    for s in sites:
        if not s.fresh or s.lead_from_parent is None or s.daily_rate <= 0:
            continue
        deficit = s.window_p50 - (s.position + s.allocated)
        cover = (s.position + s.allocated) / s.daily_rate
        if deficit > 0 and cover < s.lead_from_parent and transfer_lead_days < s.lead_from_parent:
            receivers.append((cover, s, deficit))
    receiver_ids = {s.location for _, s, _ in receivers}
    excess = {
        s.location: s.position - s.window_p90
        for s in sites
        if s.fresh and s.allocated == 0 and s.location not in receiver_ids
        and s.position - s.window_p90 > 0
    }

    out: list[Transfer] = []
    for _, r, deficit in sorted(receivers, key=lambda x: x[0]):
        for donor in sorted(excess, key=lambda k: excess[k], reverse=True):
            if deficit <= 0:
                break
            qty = int(math.floor(min(deficit, excess[donor]) / moq)) * moq
            if qty < max(1, min_units):
                continue
            out.append(Transfer(donor, r.location, qty, deficit, excess[donor]))
            excess[donor] -= qty
            deficit -= qty
    return out
```

Check `test_moves_excess_to_a_store_running_out` by hand: deficit = 20 − 2 = 18; cover = 1 day < 5; excess = 60 − 15 = 45; qty = 18. ✓

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `cd backend && uv run pytest tests/test_transfers.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/transfers.py backend/tests/test_transfers.py
git commit -m "feat(planning): store-to-store transfer matching"
```

### Task 15: Transfer decisions and coverage hint

**Files:**
- Modify: `backend/app/services/network_decisions.py` (transfers after the allocation block)
- Modify: `backend/app/services/coverage.py` (`EXCESS_ACTION` hint per location)
- Test: `backend/tests/test_network_decisions_transfers.py`

**Interfaces:**
- Consumes: Task 14 (`TransferSite`, `match_transfers`); `PolicyConfig.transfer_lead_time_days`, `min_transfer_units` and `transfer_cost_per_unit` (Task 12).
- Produces: `Decision(kind=DecisionKind.transfer, source_location_id=<donor>, location_id=<receiver>)`. Coverage location entries gain `"open_transfer": {"units": int, "destination": code} | None`.

- [ ] **Step 1: Write the failing tests.** Use the Task 13 fixture with DC available = 0, store A at 0 units and p50 14/week, store F at 80 units and p50 7/week, and lead time 5 days.
  1. **Transfer suggested:** there is one `transfer` F → A with units = `floor(min(deficit_A, excess_F))`.
  2. **Unknown cost:** with `transfer_cost_per_unit` unset, the transfer is still suggested, `economics["net_value"] is None`, and one reason reads `"Transfer cost not known"`.
  3. **Unprofitable:** with cost 1000 per unit (more than the margin of 560), no transfer is suggested.
  4. **Not ready:** with fewer than 2 confirmed stores, there are no transfers.
  5. **Coverage hint:** after `refresh`, the coverage entry for F has `open_transfer == {"units": n, "destination": "a"}`.

- [ ] **Step 2: Run them and confirm they fail.**

- [ ] **Step 3: Implement.** In `build_network_decisions`, per SKU, after allocation and when `include_transfers and ready.transfers_ready`:
  - Build a `TransferSite` for every active store with a location band. Use:
    - `window = lead_time_days_from_parent + review_period_days` (if the lead time is `None`, use `review_period_days` and pass `lead_from_parent=None`, which makes the store a donor only);
    - `window_p50 = _window_sum(band.p50, window)`, `window_p90 = _window_sum(band.p90, window)`;
    - `daily_rate = window_p50 / window`, `fresh = not stale`;
    - `allocated` = units allocated to that store this cycle (0 if none).
  - Call `match_transfers(sites, transfer_lead_days=policy.transfer_lead_time_days, moq=int(sku.moq or 1), min_units=policy.min_transfer_units)`.
  - For each transfer:
    - `margin_known = sku.unit_cost is not None and sku.unit_price is not None`
    - `cost = policy.transfer_cost_per_unit`
    - `net = units * (price - unit_cost) - units * cost` if `margin_known and cost is not None` else `None`
    - If `net is not None and net <= 0`: skip, and append to `skipped` the reason `f"Transfer of {sku.sku_code} to {dest} not worth its cost"`.
    - Otherwise append a `Decision` with:
      - `kind=DecisionKind.transfer`, headline `f"Move {units} × {code} from {src} to {dest}"`, `recommended_units=units`, `baseline_units=0` (the baseline is "no transfer");
      - urgency `"high"`;
      - reasons: `Reason("receiver_runs_out", f"{dest} runs out in {cover:.1f} days; the next warehouse delivery takes {lead} days.", deficit)`, plus `Reason("transfer_cost_unknown", "Transfer cost not known", None)` when `cost is None`;
      - `economics={"currency": ..., "net_value": net}`;
      - `inputs` with deficit, excess, the windows and the policy values;
      - `location_id = receiver id`, `source_location_id = donor id`.
  - In `coverage.py`: when building location entries, query open `transfer` recommendations for the tenant with `source_location_id` set. Join `locations` for codes and attach `open_transfer` to the donor's entry, otherwise `None`. `EXCESS_ACTION` stays as the generic text; `open_transfer` is the backed suggestion.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `cd backend && uv run pytest tests/test_network_decisions_transfers.py tests/test_network_decisions_allocation.py tests/test_inventory_coverage.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/network_decisions.py backend/app/services/coverage.py backend/tests/test_network_decisions_transfers.py
git commit -m "feat(decisions): store-to-store transfer recommendations"
```

---

## Frontend

Before Task 16, read `frontend/src/api/decisions.ts`, `frontend/src/pages/Settings.tsx`, `frontend/src/components/settings/FocusProfileCard.tsx` and `frontend/src/pages/Decisions.test.tsx`. Copy their exact patterns for the API client, React Query keys (`frontend/src/api/planningKeys.ts`), card layout and test setup (mocking `api/client`).

### Task 16: Network setup in Settings

**Files:**
- Create: `frontend/src/api/locations.ts`
- Create: `frontend/src/components/settings/NetworkCard.tsx`
- Create: `frontend/src/components/settings/NetworkCard.test.tsx`
- Modify: `frontend/src/pages/Settings.tsx` (render `<NetworkCard />` below the existing cards)

**Interfaces:**
- Consumes: `GET /locations` and `PATCH /locations/{id}` (Task 5).
- Produces:
  - `locationsApi.list(): Promise<LocationsResponse>`
  - `locationsApi.update(id: string, patch: LocationPatch): Promise<{location: Location; network: Network}>`
  - Types `Location`, `Network`, `LocationPatch`, `LocationsResponse` mirroring the backend JSON exactly (snake_case keys).

- [ ] **Step 1: Write the failing component test.** Mock `locationsApi`, then assert that:
  - **(a)** the table lists each location with a kind select, a parent select (warehouses only) and a lead-time input;
  - **(b)** every `network.missing` message is rendered as a checklist item;
  - **(c)** changing a kind calls `locationsApi.update(id, {kind: "warehouse"})` and refetches;
  - **(d)** with `network.allocation_ready`, the card shows "Allocation ready".

- [ ] **Step 2: Run it and confirm it fails.**

Run: `cd frontend && npx vitest run src/components/settings/NetworkCard.test.tsx`

- [ ] **Step 3: Implement `locations.ts`**

```ts
import { apiClient } from "./client";

export type LocationKind = "warehouse" | "store" | "unconfirmed";

export interface Location {
  id: string;
  code: string;
  name: string;
  kind: LocationKind;
  parent_location_id: string | null;
  lead_time_days_from_parent: number | null;
  is_active: boolean;
}

export interface Network {
  allocation_ready: boolean;
  transfers_ready: boolean;
  missing: string[];
}

export interface LocationsResponse {
  locations: Location[];
  network: Network;
}

export type LocationPatch = Partial<
  Pick<Location, "name" | "kind" | "parent_location_id" | "lead_time_days_from_parent" | "is_active">
>;

export const locationsApi = {
  list: () => apiClient.get<LocationsResponse>("/locations").then((r) => r.data),
  update: (id: string, patch: LocationPatch) =>
    apiClient
      .patch<{ location: Location; network: Network }>(`/locations/${id}`, patch)
      .then((r) => r.data),
};
```

Check the real export name and response shape in `frontend/src/api/client.ts` (for example `apiClient` vs `api`, and whether it returns `r.data`), and match it.

Then implement `NetworkCard.tsx`:
- Use React Query with `queryKey: ["locations"]` (or the `planningKeys` convention if one fits) and a `useMutation` that invalidates `["locations"]` and the decisions keys.
- Lay it out as a table with these columns: name, kind (select), supplied by (select of warehouses; disabled unless the kind is `store`), lead time in days (number input, saved on blur), active (checkbox).
- Above the table, show the readiness checklist built from `network.missing`, or "Allocation ready" / "Transfers ready" badges.
- Show empty state copy: "No locations yet. Import sales or stock with a location (store/branch) column."
- Use icons only from `@/components/ui/icons`.

- [ ] **Step 4: Run the test and typecheck, and confirm they pass**

Run: `cd frontend && npx vitest run src/components/settings/NetworkCard.test.tsx && npm run typecheck`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/locations.ts frontend/src/components/settings/NetworkCard.tsx frontend/src/components/settings/NetworkCard.test.tsx frontend/src/pages/Settings.tsx
git commit -m "feat(settings): store/warehouse network setup"
```

### Task 17: Location filter on Inventory; route grouping on Decisions

**Files:**
- Modify: `frontend/src/api/inventory.ts` (types: location entry gains `demand_basis` and `open_transfer`)
- Modify: `frontend/src/api/decisions.ts` (types: `kind` union gains `"allocation" | "transfer"`; add `location_id`, `source_location_id`, `location_code`, `source_location_code`; refresh response gains `notes: string[]`)
- Modify: `frontend/src/pages/Inventory.tsx`, `frontend/src/pages/Decisions.tsx`
- Test: `frontend/src/pages/Inventory.test.tsx`, `frontend/src/pages/Decisions.test.tsx` (add cases)

- [ ] **Step 1: Write the failing tests**
  - **Inventory:**
    - A location `<select>` built from the location codes in the coverage response filters the location rows.
    - A location row with `demand_basis: "forecast"` shows the badge "From location forecast".
    - A location row with `open_transfer` shows "Transfer {units} to {destination} suggested".
  - **Decisions:**
    - Allocation and transfer items are grouped under a route header `"{source_location_code} → {location_code} · {n} lines · {units} units"`.
    - `purchase_order` items render exactly as before. The existing tests must still pass unchanged.
    - When the refresh response has `notes`, they are shown in an info panel titled "Network setup needed" that links to Settings.

- [ ] **Step 2: Run them and confirm they fail.**

Run: `cd frontend && npx vitest run src/pages/Inventory.test.tsx src/pages/Decisions.test.tsx`

- [ ] **Step 3: Implement.** Add the minimal UI to make the tests pass. Group items with a pure helper, `groupByRoute(items)` in `Decisions.tsx` (or `frontend/src/pages/decisionsRoutes.ts` if `Decisions.tsx` is already large). It returns `{key, source, destination, items, units}[]`, ordered by the most urgent item in each group. Accept and dismiss buttons reuse the existing per-item handlers.

- [ ] **Step 4: Run the full frontend checks and confirm they pass**

Run: `cd frontend && npx vitest run && npm run typecheck && npm run lint`
Expected: PASS. Any failure that also fails on `main` before your change must be reported, not hidden. See the memory note about the billing specs that were already red on main.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/inventory.ts frontend/src/api/decisions.ts frontend/src/pages
git commit -m "feat(ui): location filter on inventory and route-grouped transfer/allocation decisions"
```

### Task 17b: Location forecasts on the Forecasts page (spec §7)

**Files:**
- Modify: `backend/app/routers/locations.py` (add an endpoint)
- Modify: `frontend/src/api/locations.ts`, `frontend/src/pages/Forecasts.tsx`
- Test: `backend/tests/test_locations_api.py` (add a case), `frontend/src/pages/Forecasts.test.tsx` (add a case)

**Interfaces:**
- Consumes: `latest_completed_run` (decision_builder), `is_run_fresh` (planning_inputs), `location_bands` (Task 8).
- Produces:
  - `GET /api/v1/locations/forecast?sku_id=<uuid>`, returning `{"run_id": str | null, "degraded": bool, "unassigned_share": float | null, "locations": [{"location_id", "code", "name", "p10": [..], "p50": [..], "p90": [..]}], "reason": str | null}`.
  - `locationsApi.forecast(skuId: string)`.

- [ ] **Step 1: Write the failing backend test.**
  - With the fixture from Task 8 split, the endpoint returns two locations whose `p50[0]` values sum to the SKU p50.
  - With no fresh run, it returns `locations == []` and the reason `"No forecast from the last 14 days"`. Use the actual `FORECAST_MAX_AGE_DAYS` value in the message.

- [ ] **Step 2: Run it and confirm it fails.** Then implement:

```python
@router.get("/forecast")
async def location_forecast(request: Request, tenant_id: TenantId, ctx: ActiveIndustry,
                            sku_id: uuid.UUID) -> dict[str, Any]:
    from datetime import UTC, datetime

    from app.services.decision_builder import latest_completed_run
    from app.services.location_forecast import location_bands
    from app.services.planning_inputs import FORECAST_MAX_AGE_DAYS, is_run_fresh

    now = datetime.now(UTC)
    db = request.app.state.db
    async with db.session(str(tenant_id)) as session:
        run = await latest_completed_run(session, tenant_id, IndustryCode(ctx.code))
        if run is None or not is_run_fresh(run, now):
            return {"run_id": None, "degraded": False, "unassigned_share": None, "locations": [],
                    "reason": f"No forecast from the last {FORECAST_MAX_AGE_DAYS} days"}
        bands = await location_bands(session, tenant_id, run.id, now)
        locs = {l.id: l for l in await load_locations(session, tenant_id)}
    metrics = run.metrics or {}
    rows = [
        {"location_id": str(loc_id), "code": locs[loc_id].code, "name": locs[loc_id].name,
         "p10": b.p10, "p50": b.p50, "p90": b.p90}
        for (sid, loc_id), b in bands.items() if sid == sku_id and loc_id in locs
    ]
    return {"run_id": str(run.id), "degraded": bool(metrics.get("location_degraded")),
            "unassigned_share": metrics.get("unassigned_share"),
            "locations": sorted(rows, key=lambda r: r["code"]),
            "reason": None if rows else "No location forecast for this SKU"}
```

Import `ActiveIndustry` from `app.routers.industry_router` and `IndustryCode` from `app.models.enums`. Declare this route **before** `@router.patch("/{location_id}")`. It uses GET, so it can't collide with the PATCH, but keep it above anyway for readability.

- [ ] **Step 3: Frontend.** Add `forecast: (skuId) => apiClient.get(`/locations/forecast`, { params: { sku_id: skuId } }).then((r) => r.data)` to `locationsApi`. On `Forecasts.tsx`, when a SKU is selected, render a "By location" table with one row per location and the weekly p50 values (p10–p90 on hover/title). Show the `degraded` badge text "Location split incomplete: {pct}% of sales have no location", or show `reason` when `locations` is empty. Write the Vitest case first, watch it fail, then implement.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `cd backend && uv run pytest tests/test_locations_api.py -v` and `cd frontend && npx vitest run src/pages/Forecasts.test.tsx && npm run typecheck`.

- [ ] **Step 5: Commit**

```bash
git add backend/app/routers/locations.py backend/tests/test_locations_api.py frontend/src/api/locations.ts frontend/src/pages/Forecasts.tsx frontend/src/pages/Forecasts.test.tsx
git commit -m "feat(forecasts): per-location forecast view"
```

---

## Verification

### Task 18: Scale benchmark, Swecha holdout check, full suite

**Files:**
- Create: `backend/benchmarks/bench_location_pipeline.py`
- Modify: `backend/benchmarks/README.md` (one section: how to run it and the measured numbers)

- [ ] **Step 1: Write the benchmark.** Follow the structure of `backend/benchmarks/bench_sales_summary.py`, including how it connects and seeds; read it first.
  - Seed a synthetic tenant: 25,000 SKUs across 50 categories; 1 DC + 6 stores; 12 weeks of sales per (SKU, store) drawn from Poisson with per-store means 0.2–8; a completed run with 8 weeks of SKU forecasts; fresh inventory.
  - Time three steps: `split_run_by_location`, `build_network_decisions` (allocation + transfers) and `persist_decisions`.
  - Print rows/second and wall time for each step.
  - Seeding must use `source='synthetic_bench'` and a tenant slug starting `bench-`, and the benchmark must delete its tenant afterwards.

- [ ] **Step 2: Run it** against the local dev DB (see `backend/benchmarks/README.md` for the connection). Record the numbers in the README. If any step takes over 120 s, write that down as a finding in the README and in your final report. Do not tune silently.

- [ ] **Step 3: Swecha holdout check (manual, recorded).**
  1. Load `data/demo-swecha/01..03` training files and `05-inventory.csv` into a clean tenant through the normal upload API. See `docs/audit/2026-10-25-fashion-readiness/clean-run/` for the clean-import procedure used last time.
  2. Run a forecast.
  3. Load `04-heldout-8-weeks.csv`.
  4. Call `GET /forecast/accuracy`.

  Record per-location MASE (Boduppal, Alwal) and the weighted MASE in `docs/audit/2026-10-26-location-forecasting/holdout.md`, with the exact commands used. Before any live test, check port ownership (`netstat -ano | findstr :8000` and `:8001`); duplicate bare-metal and Docker stacks are known to collide.

- [ ] **Step 4: Full suites**

Run:

```bash
cd backend && uv run pytest -q
cd backend/ml && uv run pytest -q
cd frontend && npx vitest run && npm run typecheck && npm run lint
```

Expected: everything passes, except failures that are proven to exist on `main` before this work. List those by test id with the output.

- [ ] **Step 5: Commit**

```bash
git add backend/benchmarks docs/audit/2026-10-26-location-forecasting
git commit -m "test(bench): location pipeline at 25k SKUs x 6 stores; Swecha holdout record"
```

---

## Not in this plan (by spec decision)

Method C (`middle_out_mint`) and multi-echelon safety stock are gated on backtests (§4.5, §5.1). Branch-scoped access (Phase 5) gets its own spec. ERP write-back, a lanes table, multi-level networks, pharma batch-aware transfers, end-of-season consolidation, "like store" cloning and style-level size-run integrity are out of scope (§11).
