"""Precompute and cache feature matrices for every tenant/industry.

Usage: python -m scripts.backfill_features [tenant_id]
"""

from __future__ import annotations

import sys
import uuid

import structlog
from sqlalchemy import create_engine, text

from sanket_ml.config import get_ml_settings
from sanket_ml.data.features import build_feature_matrix
from sanket_ml.data.loader import ExternalSignalLoader, HistoricalSalesLoader

log = structlog.get_logger(__name__)


def main(target_tenant: str | None = None) -> int:
    settings = get_ml_settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True)

    where = "WHERE status = 'active'"
    params: dict = {}
    if target_tenant:
        where += " AND id = :tid"
        params["tid"] = target_tenant

    with engine.begin() as conn:
        tenants = conn.execute(
            text(f"SELECT id::text, industries::text[] AS industries FROM tenants {where}"), params
        ).fetchall()

    sales_loader = HistoricalSalesLoader(settings)
    signal_loader = ExternalSignalLoader(settings)
    out_root = settings.artifact_root / "features"
    out_root.mkdir(parents=True, exist_ok=True)

    for row in tenants:
        tid = uuid.UUID(row.id)
        for ind in row.industries or []:
            try:
                panel = sales_loader.load(tid, ind, freq="W")
                if panel.n_series == 0:
                    log.warning("backfill.empty", tenant=str(tid), industry=ind)
                    continue
                signals = signal_loader.load(
                    tid, ind, start=panel.start.date(), end=panel.end.date()
                )
                feats = build_feature_matrix(panel.data, signals, industry=ind)
                out = out_root / f"{tid}__{ind}.parquet"
                feats.to_parquet(out, engine="pyarrow", index=False)
                log.info(
                    "backfill.done",
                    tenant=str(tid),
                    industry=ind,
                    n_rows=len(feats),
                    path=str(out),
                )
            except Exception as exc:
                log.error("backfill.failed", tenant=str(tid), industry=ind, error=str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else None))
