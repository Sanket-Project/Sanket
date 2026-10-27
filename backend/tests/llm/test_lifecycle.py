from contextlib import nullcontext

import pytest

from app.config import get_settings
from app.services.llm.service import AIService


@pytest.mark.parametrize("fail_in_body", [False, True])
async def test_lifecycle_inert_and_closes_on_error(setup_schema, monkeypatch, fail_in_body):
    from app.main import create_app
    monkeypatch.setenv("DEEPSEEK_API_KEY", "")
    monkeypatch.setenv("REDIS_URL", "")
    get_settings.cache_clear()
    app = create_app()
    captured = []
    with pytest.raises(RuntimeError, match="controlled body failure") if fail_in_body else nullcontext():
        async with app.router.lifespan_context(app):
            assert isinstance(app.state.ai, AIService)
            captured.append(app.state.ai.client.http)
            assert not captured[0].is_closed
            if fail_in_body:
                raise RuntimeError("controlled body failure")
    assert captured
    assert captured[0].is_closed


async def test_existing_analyze_works_with_ai_off(client, signed_in_workspace):
    _, headers = await signed_in_workspace("fashion")
    response = await client.post("/api/v1/integrations/upload/analyze",
        headers=headers,
        data={"kind": "sales"}, files={"file": ("example.csv", b"SKU,Quantity,Date\nA,2,2026-01-01\n", "text/csv")})
    assert response.status_code == 200
    assert response.json()["suggested_mapping"]["quantity"] == "Quantity"


async def test_running_foundation_with_mock_provider_and_degraded_dependencies(app_role_db, ai_redis, monkeypatch):
    from unittest.mock import AsyncMock

    import httpx
    from test_client import envelope
    from test_rls import seed_workspace

    from app import main
    from app.services.llm import client as provider_module
    from app.services.llm.client import ProviderClient
    from app.services.llm.contracts import Column, TaskInput
    from app.services.llm.policy import PolicyStore

    ctx = await seed_workspace(app_role_db)
    await PolicyStore(app_role_db).update(ctx, enabled=True, task_enabled=True, sharing="headers_only")
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=envelope()) if len(calls) == 1 else httpx.Response(503)

    monkeypatch.setattr(main, "Database", lambda config: app_role_db)
    monkeypatch.setattr(main, "_init_redis", AsyncMock(return_value=ai_redis))
    monkeypatch.setattr(provider_module, "ProviderClient", lambda config: ProviderClient(config, transport=httpx.MockTransport(handler)))
    get_settings.cache_clear()
    app = main.create_app()
    async with app.router.lifespan_context(app):
        assert not calls  # Even enabled policy does not warm up a model at startup.
        task = TaskInput(columns=[Column(id="c1", label="Qty")], allowed_fields=["quantity"])
        result = await app.state.ai.run(ctx, task)
        assert result.state == "success"
        assert len(calls) == 1
        changed = TaskInput(columns=[Column(id="c2", label="Qty")], allowed_fields=["quantity"])
        assert (await app.state.ai.run(ctx, changed)).state == "unavailable"
        assert len(calls) == 3  # Exactly one retry on the transient failure.
        app.state.ai.state.redis = None
        assert (await app.state.ai.run(ctx, task)).reason == "infrastructure_unavailable"
        assert len(calls) == 3
