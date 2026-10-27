import json
from dataclasses import replace

import httpx
import pytest

from app.services.llm.policy import Policy
from app.services.llm.tasks import request_for
from test_facts import ledger
from test_service import context, service


async def test_narrative_requires_explicit_aggregate_permission_without_dispatch():
    calls = []
    ai, _, _ = service(None, lambda r: calls.append(r), policy=Policy(True, True, "headers_only"))
    try:
        result = await ai.run(replace(context(), task_name="planning_brief"),
                              request_for("planning_brief", ledger().model_dump()))
        assert result.reason == "sharing_disabled"
        assert not calls
    finally:
        await ai.aclose()


async def test_registered_request_runs_through_shared_controls_and_cache(ai_redis):
    calls = []
    def handler(request):
        calls.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {
            "content": '{"blocks":[{"proposition":"fact","fact_ids":["cover"]}]}'}}],
            "usage": {"prompt_tokens": 40, "completion_tokens": 12}})
    ai, _, telemetry = service(ai_redis, handler, policy=Policy(True, True, "headers_only", True))
    ctx = replace(context(), task_name="planning_brief")
    task = request_for("planning_brief", ledger().model_dump())
    try:
        result = await ai.run(ctx, task)
        assert result.state == "success", result.reason
        assert result.value.blocks[0].fact_ids == ["cover"]
        assert (await ai.run(ctx, task)).cached
        assert len(calls) == 1
        assert "blocks" in calls[0]["messages"][0]["content"]
        assert telemetry.record.await_args_list[0].args[0].task_name == "planning_brief"
        foreign_actor = replace(ctx, user_id=context().user_id)
        assert not (await ai.run(foreign_actor, task)).cached
        assert len(calls) == 2
    finally:
        await ai.aclose()


async def test_task_context_mismatch_never_dispatches():
    ai, _, _ = service(None, lambda r: pytest.fail("must not dispatch"), policy=Policy(True, True, "headers_only", True))
    try:
        result = await ai.run(context(), request_for("planning_brief", ledger().model_dump()))
        assert result.reason == "invalid_context"
    finally:
        await ai.aclose()
