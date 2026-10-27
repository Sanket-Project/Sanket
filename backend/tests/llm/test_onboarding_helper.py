from dataclasses import replace
from unittest.mock import AsyncMock

import pytest

from app.services.llm.contracts import AIResult
from test_rls import seed_workspace


async def test_readiness_facts_are_engine_owned_and_missing_inventory_explicit(app_role_db):
    from app.services.llm.context import build_context
    ctx = replace(await seed_workspace(app_role_db), task_name="onboarding")
    context = await build_context(app_role_db, ctx)
    facts = {f.id: f for f in context.facts}
    assert facts["sales_rows"].value == "0"
    assert facts["skus_with_stock"].value == "0"
    assert any(f.kind == "data_gap" and "inventory" in f.label.lower() for f in context.facts)
    assert all(f.snapshot == context.snapshot for f in context.facts)


async def test_catalog_answers_use_actual_availability_and_unknowns_rejected(app_role_db):
    from app.connectors import get_spec
    from app.services.llm.context import build_context
    ctx = replace(await seed_workspace(app_role_db), task_name="onboarding")
    data = await build_context(app_role_db, ctx, connector="shopify")
    status = next(f for f in data.facts if f.id == "connector_status")
    assert status.value == get_spec("shopify").availability.value
    question = await build_context(app_role_db, ctx, connector="How do I connect Shopify?")
    assert next(f for f in question.facts if f.id == "connector_status").value == status.value
    with pytest.raises(ValueError, match="connector"):
        await build_context(app_role_db, ctx, connector="invented-connector")


async def test_disabled_summary_never_loads_business_data_or_dispatches(app_role_db, monkeypatch):
    import app.services.llm.context as contexts
    ctx = replace(await seed_workspace(app_role_db), task_name="onboarding")
    build = AsyncMock(side_effect=AssertionError("disabled task must not load data"))
    monkeypatch.setattr(contexts, "build_context", build)
    ai = AsyncMock()
    result = await contexts.generate_summary(app_role_db, ai, ctx)
    assert result["state"] == "disabled"
    assert result["blocks"] == []
    build.assert_not_awaited()
    ai.run.assert_not_awaited()


async def test_summary_route_is_scoped_and_defaults_off(client, signed_in_workspace):
    _, headers = await signed_in_workspace("fashion")
    response = await client.post("/api/v1/ai/summary/onboarding", headers=headers, json={})
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "disabled"
    invalid = await client.post("/api/v1/ai/summary/onboarding", headers=headers, json={"facts": [{"value": 999}]})
    assert invalid.status_code == 422
