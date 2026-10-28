"""Real app-role RLS and disposable Redis; provider transport always mocked."""
import json
import uuid
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import text

from app.models.inventory import InventoryLevel
from app.models.enums import IndustryCode
from app.services.llm.errors import AIError
from app.services.llm.interactive import ToolStep, question_input
from app.services.llm.interactive_service import read_operation, answer
from app.services.llm.policy import PolicyStore, Policy
from app.services.llm.tasks import request_for
from test_rls import seed_workspace


async def test_qa_adapters_enforce_real_rls_and_scope_foreign_sku(app_role_db):
    from test_roi_tiers import _rec
    a = replace(await seed_workspace(app_role_db), task_name="data_qa_plan")
    b = replace(await seed_workspace(app_role_db), task_name="data_qa_plan")
    ids = []
    for ctx, units in ((a, 17), (b, 9001)):
        async with app_role_db.session(str(ctx.tenant_id)) as session:
            rec = await _rec(session, ctx.tenant_id)
            ids.append(rec.sku_id)
            session.add(InventoryLevel(tenant_id=ctx.tenant_id, industry=IndustryCode.fashion,
                                      sku_id=rec.sku_id, on_hand_units=Decimal(units)))
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(db=app_role_db)))
    data = await read_operation(request, a, ToolStep(operation="inventory"))
    assert data["totals"]["available_units"] == 17
    assert str(ids[1]) not in json.dumps(data, default=str)
    from app.core.exceptions import NotFoundError
    with pytest.raises(NotFoundError):
        await read_operation(request, a, ToolStep(operation="sku", sku_id=ids[1]))


async def test_qa_disabled_or_inactive_user_never_dispatches_real_data(app_role_db):
    from unittest.mock import AsyncMock
    a = replace(await seed_workspace(app_role_db), task_name="data_qa_plan")
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(db=app_role_db)))
    ai = SimpleNamespace(run=AsyncMock())
    assert (await answer(request, ai, a, "Show inventory"))["state"] == "disabled"
    ai.run.assert_not_called()
    async with app_role_db.session(str(a.tenant_id)) as session:
        await session.execute(text("UPDATE users SET is_active=false WHERE id=:id"), {"id": a.user_id})
    with pytest.raises(AIError, match="invalid_context"):
        await answer(request, ai, a, "Show inventory")
    ai.run.assert_not_called()


async def test_question_tasks_never_store_questions_or_answers_in_redis(ai_redis):
    from test_client import envelope
    from test_service import service, context
    calls = []
    def handler(request):
        calls.append(request)
        response = envelope()
        response["choices"][0]["message"]["content"] = json.dumps({"steps": [{"operation": "inventory"}]})
        return httpx.Response(200, json=response)
    ai, _, _ = service(ai_redis, handler, policy=Policy(True, True, "headers_only", aggregate_context=True))
    ctx = replace(context(), task_name="data_qa_plan")
    question = "How much inventory does secretprivatequestion have?"
    task = request_for("data_qa_plan", question_input(question).model_dump(mode="json"))
    try:
        assert (await ai.run(ctx, task)).state == "success"
        assert (await ai.run(ctx, task)).state == "success"
        assert len(calls) == 2
        for key in await ai_redis.keys("*"):
            assert question not in key
            if await ai_redis.type(key) == "string":
                value = await ai_redis.get(key)
                assert "secretprivatequestion" not in value
                assert '"steps"' not in value
    finally:
        await ai.aclose()


async def test_authenticated_http_question_and_scenario_journey(client, signed_in_workspace, app_role_db, ai_redis, monkeypatch):
    from app.services.llm.client import ProviderClient
    from app.services.llm.service import AIService
    from app.services.llm.state import AIState
    from app.services.llm.telemetry import Telemetry
    from test_config import settings
    from test_client import envelope
    from test_roi_tiers import _rec
    tid, headers = await signed_in_workspace("fashion")
    async with app_role_db.session(str(tid)) as session:
        rec = await _rec(session, tid)
        session.add(InventoryLevel(tenant_id=tid, industry=IndustryCode.fashion,
                                  sku_id=rec.sku_id, on_hand_units=Decimal(17)))
    calls = []
    def handler(request):
        data = json.loads(request.content)
        payload = json.loads(data["messages"][1]["content"])
        calls.append(payload)
        content = ({"candidate_ids": ["a0"]} if "candidates" in payload else
                   {"blocks": [{"proposition": "fact", "fact_ids": ["inventory_available_units"]}]} if "facts" in payload else
                   {"steps": [{"operation": "inventory"}]})
        result = envelope()
        result["choices"][0]["message"]["content"] = json.dumps(content)
        return httpx.Response(200, json=result)
    config = settings()
    ai = AIService(config, PolicyStore(app_role_db), AIState(ai_redis, config),
                   ProviderClient(config, transport=httpx.MockTransport(handler)), Telemetry(app_role_db, config))
    app = client._transport.app
    original_db, original_ai = app.state.db, app.state.ai
    app.state.db, app.state.ai = app_role_db, ai
    try:
        disabled = await client.post("/api/v1/ai/data-qa", headers=headers, json={"text": "Show available inventory"})
        assert disabled.status_code == 200
        assert disabled.json()["state"] == "disabled"
        assert not calls
        enabled = await client.put("/api/v1/ai/settings", headers=headers, json={
            "enabled": True, "tasks": {"data_qa_plan": True, "data_qa_answer": True, "scenario_interpretation": True},
            "sharing": "headers_only", "aggregate_context": True, "product_names": False,
        })
        assert enabled.status_code == 200, enabled.text
        answer_response = await client.post("/api/v1/ai/data-qa", headers=headers, json={"text": "Show available inventory"})
        assert answer_response.status_code == 200, answer_response.text
        assert answer_response.json()["state"] == "success", answer_response.text
        assert "17" in answer_response.json()["blocks"][0]["text"]
        assert answer_response.headers["cache-control"] == "no-store"
        interpretation = await client.post("/api/v1/ai/scenarios/interpret", headers=headers, json={"text": "Demand increases by 20%"})
        assert interpretation.status_code == 200, interpretation.text
        assert interpretation.json()["assumptions"] == {"demand_shock_pct": 20.0}
        assert interpretation.json()["requires_confirmation"] is True
        assert len(calls) == 3
    finally:
        app.state.db, app.state.ai = original_db, original_ai
        await ai.aclose()
