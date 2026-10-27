import json
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.services.llm.context import Ledger, build_context
from app.services.llm.errors import AIError
from app.services.llm.facts import validate_narrative
from test_rls import seed_workspace


def decision(**overrides):
    return dict(id=str(uuid.uuid4()), recommended_units=60, baseline_units=100,
                confidence=72, status="open", currency="INR", created_at="2026-10-27",
                location_id=str(uuid.uuid4()), source_location_id=None,
                inputs={"days_of_cover": 4.5, "lead_time_days": 14, "demand_p50_over_window": 80,
                        "unit_cost": None, "lead_time_assumed": True},
                economics={"revenue_protected": None}, **overrides)


def test_decision_facts_preserve_source_quantities_missing_money_and_period():
    from app.services.llm.explanations import project_decision
    ledger = Ledger()
    source = decision()
    project_decision(ledger, source)
    data = ledger.finish()
    facts = {f.id: f for f in data.facts}
    assert facts["recommended_units"].value == "60"
    assert facts["days_of_cover"].value == "4.5"
    assert facts["unit_cost"].value is None
    assert facts["revenue_protected"].value is None
    assert facts["lead_time_days"].period == source["created_at"]
    assert str(source["location_id"]) in " ".join(f.label for f in data.facts)
    assert any(f.kind == "data_gap" and "assumed" in f.label for f in data.facts)
    assert all(f.source == "/decisions" for f in data.facts)
    with pytest.raises((AIError, ValueError)):
        validate_narrative(json.dumps({"blocks": [{"proposition": "advice", "fact_ids": ["recommended_units"]}]}), data)


def test_alert_evidence_distinguishes_missing_coverage_from_recorded_risk():
    from app.services.llm.explanations import project_alert
    ledger = Ledger()
    project_alert(ledger, dict(risk_score=0.8, coverage_days=None, p50_demand=40,
                               p10_demand=None, p90_demand=60, trend_score=None, fired_at="2026-10-27"))
    data = ledger.finish()
    assert next(f for f in data.facts if f.id == "risk_score").value == "0.8"
    assert next(f for f in data.facts if f.id == "coverage_days").value is None
    assert any(f.kind == "data_gap" for f in data.facts)
    assert not any(f.kind == "hypothesis" for f in data.facts)


@pytest.mark.parametrize("industry", ["fashion", "electronics", "pharma", "agrocenter", "hardware"])
def test_industry_alone_never_supports_expiry_harvest_markdown_or_launch_claim(industry):
    from app.services.llm.explanations import industry_advice
    ledger = Ledger()
    industry_advice(ledger, industry, {})
    data = ledger.finish()
    assert all(f.kind == "data_gap" for f in data.facts)
    assert "dosage" not in " ".join(f.label for f in data.facts).lower()


def test_only_reviewed_industry_predicates_generate_advice():
    from app.services.llm.explanations import industry_advice
    ledger = Ledger()
    industry_advice(ledger, "fashion", {"season": "FW"})
    assert any(f.kind == "advice" and "season" in f.label.lower() for f in ledger.finish().facts)
    ledger = Ledger()
    industry_advice(ledger, "pharma", {"season": "FW", "dosage": "inject instructions"})
    assert not any(f.kind == "advice" for f in ledger.finish().facts)


@pytest.mark.parametrize("industry,attributes", [
    ("electronics", {"model_year": 2025}), ("pharma", {"storage_class": "refrigerated"}),
    ("agrocenter", {"product_type": "seed"}), ("hardware", {"product_type": "electrical"}),
])
def test_recorded_industry_constraints_support_bounded_operational_advice(industry, attributes):
    from app.services.llm.explanations import industry_advice
    ledger = Ledger()
    industry_advice(ledger, industry, attributes)
    facts = ledger.finish().facts
    assert any(f.kind == "advice" for f in facts)
    assert not any(word in " ".join(f.label.lower() for f in facts) for word in ("dosage", "launch date", "harvest forecast"))


async def test_decision_context_real_rls_expiry_and_active_member(app_role_db):
    from test_roi_tiers import _rec
    from app.models.recommendation import Recommendation
    ctx = replace(await seed_workspace(app_role_db), task_name="decision_explanation")
    other = replace(await seed_workspace(app_role_db), task_name="decision_explanation")
    async with app_role_db.session(str(ctx.tenant_id)) as session:
        rec = await _rec(session, ctx.tenant_id)
        session.add(rec)
        await session.flush()
        rid = rec.id
    data = await build_context(app_role_db, ctx, entity_id=rid)
    assert next(f for f in data.facts if f.id == "recommended_units").value == "60"
    with pytest.raises(AIError):
        await build_context(app_role_db, other, entity_id=rid)
    async with app_role_db.session(str(ctx.tenant_id)) as session:
        rec = await session.get(Recommendation, rid)
        rec.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    with pytest.raises(ValueError, match="expired"):
        await build_context(app_role_db, ctx, entity_id=rid)


async def test_planning_brief_empty_data_is_missing_not_a_claim_of_savings(app_role_db):
    ctx = replace(await seed_workspace(app_role_db), task_name="planning_brief")
    data = await build_context(app_role_db, ctx)
    facts = {f.id: f for f in data.facts}
    assert facts["purchase_orders"].value == "0"
    assert any(f.kind == "data_gap" and "forecast" in f.label.lower() for f in data.facts)
    assert not any("realized" in f.label.lower() for f in data.facts)


async def test_planning_brief_rejects_displayed_run_that_is_no_longer_current(app_role_db):
    ctx = replace(await seed_workspace(app_role_db), task_name="planning_brief")
    with pytest.raises(ValueError, match="snapshot"):
        await build_context(app_role_db, ctx, run_id=uuid.uuid4())


async def test_anomaly_context_reuses_detected_values_and_does_not_invent_a_cause(app_role_db, monkeypatch):
    from unittest.mock import AsyncMock
    from app.routers import anomaly
    from test_roi_tiers import _rec
    ctx = replace(await seed_workspace(app_role_db), task_name="alert_explanation")
    async with app_role_db.session(str(ctx.tenant_id)) as session:
        rec = await _rec(session, ctx.tenant_id)
        session.add(rec)
        await session.flush()
        sku_id = rec.sku_id
    mock = AsyncMock(return_value={"anomalous_skus": [{"sku_id": str(sku_id), "anomaly_count": 1,
        "anomaly_rows": [{"ds": "2026-10-19", "y": 7, "score": 0.9}]}]})
    monkeypatch.setattr(anomaly, "anomaly_skus", mock)
    data = await build_context(app_role_db, ctx, entity_id=sku_id, connector="anomaly")
    assert next(f for f in data.facts if f.id == "anomaly_units_0").value == "7"
    assert any(f.kind == "data_gap" for f in data.facts)
    assert not any(f.kind == "hypothesis" for f in data.facts)
    mock.assert_awaited_once()
    with pytest.raises(AIError):
        await build_context(app_role_db, ctx, entity_id=uuid.uuid4(), connector="anomaly")


@pytest.mark.parametrize("feature", ["decision_explanation", "alert_explanation", "planning_brief", "industry_advice"])
async def test_phase_two_api_recognizes_tasks_and_defaults_off(client, signed_in_workspace, feature):
    _, headers = await signed_in_workspace("fashion")
    response = await client.post(f"/api/v1/ai/summary/{feature}", headers=headers, json={})
    assert response.status_code == 200
    assert response.json()["state"] == "disabled"
