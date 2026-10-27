from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.llm.errors import AIError
from app.services.llm.policy import PolicyStore
from test_policy import FakeDB
from test_service import context


async def test_configuration_updates_task_flags_and_permissions_without_overwriting_settings(monkeypatch):
    from app.services import audit
    ctx = context()
    tenant = SimpleNamespace(settings={"planning": {"keep": True}, "ai": {"old": "keep"}})
    profile = SimpleNamespace(feature_flags={"focus": {"keep": True}, "ai_import_mapping": True})
    db = FakeDB([SimpleNamespace(role="owner"), tenant, profile])
    monkeypatch.setattr(audit, "record", AsyncMock())
    await PolicyStore(db).configure(ctx, enabled=True, tasks={"planning_brief": True}, sharing="headers_only",
                                    aggregate_context=True, product_names=False)
    assert tenant.settings["planning"] == {"keep": True}
    assert tenant.settings["ai"]["old"] == "keep"
    assert tenant.settings["ai"]["allow_aggregate_context"] is True
    assert profile.feature_flags["ai_import_mapping"] is True
    assert profile.feature_flags["ai_planning_brief"] is True
    assert audit.record.await_args.kwargs["strict"] is True


@pytest.mark.parametrize("role", ["analyst", "viewer"])
async def test_only_current_admin_can_change_ai_settings(role):
    ctx = context()
    db = FakeDB([SimpleNamespace(role=role), SimpleNamespace(settings={}), SimpleNamespace(feature_flags={})])
    with pytest.raises(AIError, match="invalid_context"):
        await PolicyStore(db).configure(ctx, enabled=True, tasks={}, sharing="headers_only", aggregate_context=True, product_names=True)


async def test_unknown_task_and_nonboolean_permissions_are_rejected():
    ctx = context()
    db = FakeDB([])
    for patch in [{"tasks": {"send_sql": True}}, {"aggregate_context": "yes"}]:
        args = dict(enabled=True, tasks={}, sharing="headers_only", aggregate_context=False, product_names=False)
        with pytest.raises(AIError, match="invalid_input"):
            await PolicyStore(db).configure(ctx, **{**args, **patch})


async def test_authenticated_settings_routes_preserve_default_off(client, signed_in_workspace):
    _, headers = await signed_in_workspace("fashion")
    response = await client.get("/api/v1/ai/settings", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["enabled"] is False
    assert response.json()["aggregate_context"] is False
    changed = await client.put("/api/v1/ai/settings", headers=headers, json={
        "enabled": True, "tasks": {"import_mapping": True}, "sharing": "headers_only",
        "aggregate_context": False, "product_names": False,
    })
    assert changed.status_code == 200, changed.text
    assert changed.json()["tasks"]["import_mapping"] is True
    assert "key" not in changed.text.lower()


async def test_saved_format_management_routes_are_authenticated(client, signed_in_workspace):
    _, headers = await signed_in_workspace("fashion")
    response = await client.get("/api/v1/ai/import-formats", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json() == []
