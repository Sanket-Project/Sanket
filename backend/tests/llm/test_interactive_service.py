import uuid
import asyncio
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.models.enums import IndustryCode
from app.services.llm.contracts import AIResult
from app.services.llm.policy import AIContext, Policy


def context(task="data_qa_plan"):
    return AIContext(uuid.uuid4(), uuid.uuid4(), IndustryCode.fashion, task)


def request():
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(db=object())))


def allow(monkeypatch):
    from app.services.llm import interactive_service as service
    policy = AsyncMock(return_value=Policy(True, True, "headers_only", aggregate_context=True))
    monkeypatch.setattr(service.PolicyStore, "load", policy)
    return service, policy


async def test_interpretation_returns_only_reviewed_assumptions_without_simulation(monkeypatch):
    service, policy = allow(monkeypatch)
    from app.services.llm.interactive import ScenarioSelection
    ai = SimpleNamespace(run=AsyncMock(return_value=AIResult(state="success", value=ScenarioSelection(candidate_ids=["a0"]))))
    result = await service.interpret(request(), ai, context("scenario_interpretation"), "Demand increases by 20%")
    assert result["assumptions"] == {"demand_shock_pct": 20.0}
    assert result["requires_confirmation"] is True
    assert result["evidence"][0]["span"] == "Demand increases by 20%"
    assert policy.await_count >= 2


async def test_disabled_interpretation_does_not_call_model_or_load_business_data(monkeypatch):
    service, policy = allow(monkeypatch)
    policy.return_value = Policy(False, False, "disabled")
    ai = SimpleNamespace(run=AsyncMock())
    result = await service.interpret(request(), ai, context("scenario_interpretation"), "Demand increases by 20%")
    assert result["state"] == "disabled"
    ai.run.assert_not_called()


async def test_qa_uses_only_bounded_authorized_adapters_and_fact_rendered_answer(monkeypatch):
    service, policy = allow(monkeypatch)
    from app.services.llm.interactive import ToolPlan, ToolStep
    from app.services.llm.facts import NarrativeOutput, NarrativeBlock
    ai = SimpleNamespace(run=AsyncMock(side_effect=[
        AIResult(state="success", value=ToolPlan(steps=[ToolStep(operation="inventory")])),
        AIResult(state="success", value=NarrativeOutput(blocks=[NarrativeBlock(proposition="fact", fact_ids=["inventory_available_units"])])),
    ]))
    adapter = AsyncMock(return_value={"total_skus": 2, "totals": {"available_units": 17, "inbound_units": 0}})
    monkeypatch.setattr(service, "read_operation", adapter)
    answer = await service.answer(request(), ai, context(), "How much inventory is available?")
    assert answer["state"] == "success"
    assert "17" in answer["blocks"][0]["text"]
    assert answer["blocks"][0]["sources"][0]["href"] == "/inventory"
    assert adapter.await_count == 1
    assert policy.await_count >= 4
    assert ai.run.await_args_list[-1].args[0].task_name == "data_qa_answer"
    assert ai.run.await_args_list[-1].args[1].input.question == "How much inventory is available?"


async def test_qa_never_claims_missing_forecast_is_zero(monkeypatch):
    service, _ = allow(monkeypatch)
    from app.services.llm.interactive import ToolPlan, ToolStep
    ai = SimpleNamespace(run=AsyncMock(return_value=AIResult(state="success", value=ToolPlan(steps=[ToolStep(operation="saved_forecast")]))))
    monkeypatch.setattr(service, "read_operation", AsyncMock(return_value={"forecast": None, "stale": True}))
    answer = await service.answer(request(), ai, context(), "What does my forecast show?")
    assert answer["state"] == "no_data"
    assert "don't have data" in answer["message"]
    assert ai.run.await_count == 1


async def test_revoked_membership_between_steps_stops_execution(monkeypatch):
    service, policy = allow(monkeypatch)
    from app.services.llm.errors import AIError
    from app.services.llm.interactive import ToolPlan, ToolStep
    ai = SimpleNamespace(run=AsyncMock(return_value=AIResult(state="success", value=ToolPlan(steps=[ToolStep(operation="inventory")]))))
    policy.side_effect = [Policy(True, True, "headers_only", aggregate_context=True), AIError("invalid_context")]
    adapter = AsyncMock()
    monkeypatch.setattr(service, "read_operation", adapter)
    with pytest.raises(AIError):
        await service.answer(request(), ai, context(), "Inventory please")
    adapter.assert_not_called()


async def test_scenario_explanation_uses_engine_facts_without_changing_results(monkeypatch):
    service, _ = allow(monkeypatch)
    from app.services.llm.facts import NarrativeOutput, NarrativeBlock
    ai = SimpleNamespace(run=AsyncMock(return_value=AIResult(state="success", value=NarrativeOutput(blocks=[NarrativeBlock(proposition="fact", fact_ids=["scenario_short_units"])]))))
    payload = {"run_id": str(uuid.uuid4()), "baseline": {"short_units": 2, "fill_rate": 0.9},
               "result": {"short_units": 8, "fill_rate": 0.7, "gross_margin": None, "currency": "INR"},
               "config": {"horizon_weeks": 12}, "readiness": {"advisory": True}}
    result = await service.explain_result(request(), ai, context("scenario_explanation"), payload)
    assert "8" in result["blocks"][0]["text"]
    assert payload["result"]["short_units"] == 8
    assert any("advisory" in b["text"].lower() for b in result["blocks"])
    facts = ai.run.await_args.args[1].input.facts
    assert next(f for f in facts if f.id == "scenario_gross_margin").value is None


async def test_http_disconnect_cancels_inflight_operation():
    from app.routers.ai_interactive import _until_disconnect
    started = asyncio.Event()
    stopped = asyncio.Event()
    disconnected = False
    class Request:
        async def is_disconnected(self):
            return disconnected
    async def operation():
        started.set()
        try:
            await asyncio.Future()
        finally:
            stopped.set()
    task = asyncio.create_task(_until_disconnect(Request(), operation()))
    await started.wait()
    disconnected = True
    assert (await asyncio.wait_for(task, 1))["state"] == "cancelled"
    assert stopped.is_set()


def test_saved_forecast_projects_bounded_source_quantities_and_dates():
    from app.services.llm.interactive import ToolStep
    from app.services.llm.interactive_service import project_operation
    from app.services.llm.context import Ledger
    ledger = Ledger()
    project_operation(ledger, ToolStep(operation="saved_forecast"), {"stale": True, "forecast": {
        "run_id": "source-run", "total_skus": 2, "horizon_weeks": 12,
        "completed_at": "2026-10-27", "rows": [{"forecast_date": "2026-11-02", "p10": 8, "p50": 10, "p90": 12}]}})
    facts = {f.id:f for f in ledger.finish().facts}
    assert facts["saved_forecast_week_0_p50"].value == "10"
    assert "2026-11-02" in facts["saved_forecast_week_0_p50"].period
    assert "source-run" in facts["saved_forecast_week_0_p50"].period
    assert facts["saved_forecast_week_0_p50"].source == "/forecasts"
    assert facts["saved_forecast_stale"].kind == "data_gap"
