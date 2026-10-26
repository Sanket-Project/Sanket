"""Provision an isolated, synthetic database for the workspace-review remediation journeys.

Creates (or recreates) ONLY the database named ``sanket_review_fixture`` on the
local Docker Postgres, builds it with the real migration chain, and seeds two
clearly synthetic fashion workspaces (A and B) for:

* same-industry account switching (F1)        * expired recommendation (F2)
* missing unit cost / assumed lead time (F3, F14)
* stale stock and zero-sales weeks (F5, F6)   * excess cover (initial report)

The postgres superuser is used for fixture setup only (like backend/tests/conftest.py);
the app under test connects as ``sanket_app`` and is subject to RLS. Credentials
for the synthetic users are written to fixture.json beside this script.

Run from backend/:  .venv/Scripts/python.exe ../docs/audit/2026-10-26-workspace-review/remediation/provision_fixture.py
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import asyncpg

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parents[3] / "backend"
sys.path.insert(0, str(BACKEND))

DB = "sanket_review_fixture"
SUPER = "postgresql://postgres:postgres@localhost:5432"
APP_URL = f"postgresql+asyncpg://sanket_app:changeme@localhost:5432/{DB}"


def week_start(day: datetime) -> datetime:
    day = day.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return day - timedelta(days=day.weekday())


async def recreate_database() -> None:
    conn = await asyncpg.connect(f"{SUPER}/postgres")
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{DB}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{DB}"')
    finally:
        await conn.close()


def migrate() -> None:
    env = dict(os.environ)
    env["DATABASE_URL"] = APP_URL
    env["MIGRATION_DATABASE_URL"] = f"postgresql+asyncpg://postgres:postgres@localhost:5432/{DB}"
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env, check=True)


async def seed() -> dict:
    from app.config import get_settings
    from app.core.security import hash_password

    now = datetime.now(UTC)
    this_week = week_start(now)
    conn = await asyncpg.connect(f"{SUPER}/{DB}")
    fixture: dict = {"synthetic": True, "database": DB, "generated_at": now.isoformat(), "workspaces": {}}

    async def tenant(label: str) -> tuple[uuid.UUID, dict]:
        tid = uuid.uuid4()
        slug = f"synthetic-review-{label.lower()}"
        await conn.execute(
            "INSERT INTO tenants (id, slug, display_name, tier, status, industry) "
            "VALUES ($1, $2, $3, 'growth', 'active', 'fashion')",
            tid, slug, f"Synthetic review {label}",
        )
        await conn.execute(
            "INSERT INTO subscriptions (id, tenant_id, plan_id, status, current_period_start, "
            "current_period_end, cancel_at_period_end, metadata) VALUES ($1, $2, 'enterprise_monthly', "
            "'active', now() - interval '1 day', now() + interval '30 days', FALSE, "
            "'{\"review_fixture\": true}'::jsonb)",
            uuid.uuid4(), tid,
        )
        password = f"Synthetic-{secrets.token_urlsafe(9)}"
        email = f"synthetic-review-planner-{label.lower()}@example.com"
        await conn.execute(
            "INSERT INTO users (id, tenant_id, email, password_hash, full_name, role, active_industry, "
            "is_active) VALUES ($1, $2, $3, $4, $5, 'admin', 'fashion', TRUE)",
            uuid.uuid4(), tid, email, hash_password(password, get_settings()), f"Planner {label}",
        )
        # No settings["onboarding"] key: load_onboarding_state treats the
        # workspace as set up, so it opens on the planning screens.
        info = {"tenant_id": str(tid), "slug": slug, "email": email, "password": password, "skus": {}}
        fixture["workspaces"][label] = info
        return tid, info

    async def sku(tid, info, code, *, cost, price, lead):
        pid, sid = uuid.uuid4(), uuid.uuid4()
        await conn.execute(
            "INSERT INTO products (id, tenant_id, industry, name, category, status) "
            "VALUES ($1, $2, 'fashion', $3, 'Synthetic', 'active')",
            pid, tid, f"Synthetic {code}",
        )
        await conn.execute(
            "INSERT INTO skus (id, tenant_id, product_id, industry, sku_code, unit_cost, unit_price, "
            "lead_time_days, moq) VALUES ($1, $2, $3, 'fashion', $4, $5, $6, $7, 1)",
            sid, tid, pid, code, cost, price, lead,
        )
        info["skus"][code] = str(sid)
        return sid

    async def stock(tid, sid, units, age_days, location="Synthetic WH"):
        await conn.execute(
            "INSERT INTO inventory_levels (tenant_id, sku_id, industry, location, on_hand_units, "
            "reserved_units, inbound_units, source, as_of) VALUES ($1, $2, 'fashion', $3, $4, 0, 0, "
            "'synthetic_test', $5)",
            tid, sid, location, units, now - timedelta(days=age_days),
        )

    async def weekly_sales(tid, sid, per_week: list[int]):
        # per_week[i] is units for the week (len - i) weeks before this one.
        for i, units in enumerate(per_week):
            week = this_week - timedelta(weeks=len(per_week) - i)
            if units:
                await conn.execute(
                    "INSERT INTO historical_sales (tenant_id, sku_id, industry, sale_time, channel, "
                    "units_sold) VALUES ($1, $2, 'fashion', $3, 'store', $4)",
                    tid, sid, week + timedelta(days=2, hours=12), units,
                )

    async def forecast(tid, skus: dict[uuid.UUID, float]):
        run = uuid.uuid4()
        await conn.execute(
            "INSERT INTO forecast_runs (id, tenant_id, industry, model_stack, horizon_weeks, granularity, "
            "status, completed_at, metrics) VALUES ($1, $2, 'fashion', ARRAY['synthetic_fixture'], 12, "
            "'weekly', 'completed', $3, $4::jsonb)",
            run, tid, now - timedelta(hours=6), json.dumps({"mode": "synthetic_fixture", "calendar": "W-MON-UTC"}),
        )
        for sid, p50 in skus.items():
            for w in range(12):
                await conn.execute(
                    "INSERT INTO forecast_results (tenant_id, run_id, sku_id, forecast_date, p10, p50, p90, "
                    "model_name) VALUES ($1, $2, $3, $4, $5, $6, $7, 'synthetic_fixture')",
                    tid, run, sid, (this_week + timedelta(weeks=w)).date(), p50 * 0.7, p50, p50 * 1.4,
                )
        return run

    async def recommendation(tid, sid, run, headline, *, expires_in_days, units):
        rid = uuid.uuid4()
        await conn.execute(
            "INSERT INTO recommendations (id, tenant_id, industry, sku_id, run_id, kind, status, urgency, "
            "headline, recommended_units, baseline_units, confidence, confidence_band, inputs, economics, "
            "expires_at) VALUES ($1, $2, 'fashion', $3, $4, 'purchase_order', 'open', 'high', $5, $6, $6, "
            "72, 'moderate', $7::jsonb, $8::jsonb, $9)",
            rid, tid, sid, run, headline, units,
            json.dumps({"lead_time_days": 14, "review_period_days": 28, "protection_days": 42,
                        "service_level": 0.97, "days_of_cover": 9.0, "unit_cost": None,
                        "unit_price": 1200.0, "lead_time_assumed": True}),
            json.dumps({"currency": "INR", "capital_committed": None, "revenue_protected": 24000.0}),
            now + timedelta(days=expires_in_days),
        )
        return str(rid)

    async with conn.transaction():
        a, a_info = await tenant("A")
        kurti = await sku(a, a_info, "SYN-A-KURTI", cost=None, price=1200, lead=None)
        jeans = await sku(a, a_info, "SYN-A-JEANS", cost=650, price=1500, lead=21)
        scarf = await sku(a, a_info, "SYN-A-SCARF", cost=None, price=400, lead=14)
        shawl = await sku(a, a_info, "SYN-A-SHAWL", cost=900, price=2200, lead=14)
        await stock(a, kurti, 30, 1)
        await stock(a, jeans, 120, 1)
        await stock(a, scarf, 60, 40)  # stale
        await stock(a, shawl, 1000, 1)  # ~466 days of cover at 15/week → excess
        await weekly_sales(a, kurti, [0, 0, 6, 0, 9, 0, 7, 8, 0, 10])  # zero weeks, first sale 8 weeks ago
        await weekly_sales(a, jeans, [20, 22, 18, 25, 21, 19, 23, 24, 20, 22, 21, 25])
        await weekly_sales(a, scarf, [5, 4, 6, 5, 4, 5, 6, 5])
        await weekly_sales(a, shawl, [15, 14, 16, 15, 15, 14, 16, 15])
        run_a = await forecast(a, {kurti: 8.0, jeans: 22.0, scarf: 5.0, shawl: 15.0})
        a_info["recommendations"] = {
            "expired": await recommendation(a, kurti, run_a, "A-only: expired order for 20 units",
                                            expires_in_days=-2, units=20),
            "live": await recommendation(a, jeans, run_a, "A-only: raise a purchase order for 40 units",
                                         expires_in_days=10, units=40),
        }

        b, b_info = await tenant("B")
        saree = await sku(b, b_info, "SYN-B-SAREE", cost=800, price=1900, lead=14)
        await stock(b, saree, 25, 1)
        await weekly_sales(b, saree, [9, 11, 10, 12, 10, 9, 11, 10])
        run_b = await forecast(b, {saree: 10.0})
        b_info["recommendations"] = {
            "live": await recommendation(b, saree, run_b, "B-only: raise a purchase order for 15 units",
                                         expires_in_days=10, units=15),
        }

    await conn.close()
    return fixture


async def main() -> None:
    await recreate_database()
    migrate()
    fixture = await seed()
    (HERE / "fixture.json").write_text(json.dumps(fixture, indent=2), encoding="utf-8")
    print(f"Provisioned {DB}: workspaces {', '.join(fixture['workspaces'])}")


if __name__ == "__main__":
    asyncio.run(main())
