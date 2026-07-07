"""Train models for every active tenant in PostgreSQL.

Usage:
    python -m scripts.train_all                # all active tenants
    python -m scripts.train_all <tenant_id>    # specific tenant
"""

from __future__ import annotations

import sys
import uuid

import structlog
from sqlalchemy import create_engine, text

from sanket_ml.config import get_ml_settings
from sanket_ml.industry import (
    ElectronicsOrchestrator,
    FashionOrchestrator,
    PharmaOrchestrator,
)

log = structlog.get_logger(__name__)


_ORCHESTRATORS = {
    "fashion": (FashionOrchestrator, {"horizon_weeks": 26}),
    "electronics": (ElectronicsOrchestrator, {"horizon_weeks": 12}),
    "pharma": (PharmaOrchestrator, {"horizon_weeks": 52}),
}


def main(target_tenant: str | None = None) -> int:
    settings = get_ml_settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True)

    where = "WHERE status = 'active'"
    params: dict = {}
    if target_tenant:
        where += " AND id = :tid"
        params["tid"] = target_tenant

    with engine.begin() as conn:
        # Enumerating tenants is a cross-tenant operation, so bypass RLS for this
        # read. Without this the app DB role (sanket_app, NOBYPASSRLS) sees zero
        # rows and training silently no-ops with n_tenants=0. Per-tenant data is
        # still loaded RLS-scoped by the loader (it sets app.current_tenant_id).
        conn.execute(text("SELECT set_config('app.bypass_rls', 'true', true)"))
        rows = conn.execute(
            text(f"SELECT id::text, slug, industries::text[] AS industries FROM tenants {where}"), params
        ).fetchall()

    log.info("train_all.start", n_tenants=len(rows))
    failures = 0
    for row in rows:
        tid = uuid.UUID(row.id)
        for ind in row.industries or []:
            spec = _ORCHESTRATORS.get(ind)
            if spec is None:
                log.warning("train_all.unknown_industry", tenant=str(tid), industry=ind)
                continue
            OrchCls, kwargs = spec
            try:
                log.info("train_all.tenant.start", tenant=str(tid), industry=ind)
                result = OrchCls().run(tid, **kwargs)
                log.info(
                    "train_all.tenant.done",
                    tenant=str(tid),
                    industry=ind,
                    run=result.train_result.run_name,
                )
            except Exception as exc:
                failures += 1
                log.error(
                    "train_all.tenant.failed",
                    tenant=str(tid),
                    industry=ind,
                    error=str(exc),
                )
    log.info("train_all.complete", failures=failures)
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else None))
