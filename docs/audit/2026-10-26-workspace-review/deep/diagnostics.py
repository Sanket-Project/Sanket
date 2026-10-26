"""Isolated audit probes. No database or network access; no app mutation."""
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

from app.models.enums import DecisionStatus
from app.routers import decisions
from app.services.decision_engine import DemandBand, SkuEconomics
from app.services.scenario import Scenario, apply_levers


async def probe_expiry():
    rec = SimpleNamespace(
        status=DecisionStatus.open,
        expires_at=datetime.now(UTC) - timedelta(days=30),
        recommended_units=10,
    )
    session = SimpleNamespace(flush=AsyncMock())

    @asynccontextmanager
    async def session_scope(*args):
        yield session

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        db=SimpleNamespace(session=session_scope))))
    with patch.object(decisions, "_load", AsyncMock(return_value=rec)), patch.object(
        decisions, "serialize", lambda item: {"status": str(item.status)}
    ):
        await decisions.accept_decision(
            uuid.uuid4(), decisions.AcceptBody(), request,
            SimpleNamespace(code="fashion"), uuid.uuid4(), uuid.uuid4(),
        )
    return {"expired_days_ago": 30, "accepted": rec.status == DecisionStatus.accepted}


async def main():
    sku = SkuEconomics(sku_id="audit", sku_code="AUDIT", on_hand_units=0,
                       unit_cost=0, unit_price=100)
    band = DemandBand(p10=[8] * 12, p50=list(range(1, 13)), p90=[15] * 12)
    demand, sigma, lead, cost, price = apply_levers(band, sku, Scenario(), 26)
    print(json.dumps({
        "expired_acceptance": await probe_expiry(),
        "simulation_extension": {"input_weeks": 12, "output_weeks": len(demand),
                                 "weeks_13_to_26": demand[12:]},
        "missing_cost_effect": {"unit_cost": cost, "unit_price": price,
                                "gross_margin_per_unit": price - cost},
    }, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
