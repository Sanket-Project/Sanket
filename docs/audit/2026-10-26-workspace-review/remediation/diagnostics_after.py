"""The deep audit's three isolated probes, re-run after remediation.

Same mechanisms as ../deep/diagnostics.py (no database, no network, no app
mutation); each probe runs independently and records what now happens.
"""
import asyncio
import json
import sys
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "backend"))

from fastapi import HTTPException

from app.models.enums import DecisionStatus
from app.routers import decisions
from app.services.decision_engine import DemandBand, SkuEconomics
from app.services.scenario import Scenario, SimConfig, apply_levers, compare


async def probe_expiry():
    rec = SimpleNamespace(status=DecisionStatus.open, expires_at=datetime.now(UTC) - timedelta(days=30),
                          recommended_units=10)
    session = SimpleNamespace(flush=AsyncMock())

    @asynccontextmanager
    async def session_scope(*args):
        yield session

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(db=SimpleNamespace(session=session_scope))))
    try:
        with patch.object(decisions, "_load", AsyncMock(return_value=rec)), patch.object(
            decisions, "serialize", lambda item: {"status": str(item.status)}
        ):
            await decisions.accept_decision(uuid.uuid4(), decisions.AcceptBody(), request,
                                            SimpleNamespace(code="fashion"), uuid.uuid4(), uuid.uuid4())
        rejected = None
    except HTTPException as exc:
        rejected = {"status_code": exc.status_code, "detail": exc.detail}
    return {"expired_days_ago": 30, "accepted": rec.status == DecisionStatus.accepted, "rejected": rejected}


def probe_extension():
    sku = SkuEconomics(sku_id="audit", sku_code="AUDIT", on_hand_units=0, unit_cost=0, unit_price=100)
    band = DemandBand(p10=[8] * 12, p50=list(range(1, 13)), p90=[15] * 12)
    try:
        apply_levers(band, sku, Scenario(), 26)
        padded = True
        error = None
    except ValueError as exc:
        padded, error = False, str(exc)
    out = compare(skus=[sku], bands={"audit": band}, scenario=Scenario(), config=SimConfig(horizon_weeks=26))
    return {"input_weeks": 12, "requested_weeks": 26, "apply_levers_pads": padded, "apply_levers_error": error,
            "simulated_weeks": len(out["by_sku"][0]["weekly"]["demand"]),
            "horizon_capped_reason": out["config"]["horizon_capped_reason"]}


def probe_missing_cost():
    sku = SkuEconomics(sku_id="audit", sku_code="AUDIT", on_hand_units=0, unit_cost=0, unit_price=100,
                       cost_known=False)
    band = DemandBand(p10=[8] * 12, p50=[10] * 12, p90=[15] * 12)
    out = compare(skus=[sku], bands={"audit": band}, scenario=Scenario(), config=SimConfig(horizon_weeks=12))
    return {"unit_cost": "unknown", "unit_price": 100.0,
            "baseline_gross_margin": out["baseline"]["gross_margin"],
            "baseline_purchase_spend": out["baseline"]["purchase_spend"],
            "baseline_revenue": out["baseline"]["revenue"],
            "valuation_coverage": out["valuation_coverage"]}


async def main():
    print(json.dumps({"expired_acceptance": await probe_expiry(), "simulation_extension": probe_extension(),
                      "missing_cost_effect": probe_missing_cost()}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
