import uuid
from types import SimpleNamespace

import pytest

from app.models.enums import IndustryCode
from app.services.llm.errors import AIError
from app.services.llm.policy import AIContext, PolicyStore, resolve_policy
from test_policy import FakeDB


def test_task_flags_and_sharing_do_not_broaden_header_permission():
    flags = {"ai_enabled": True, "ai_import_mapping": True, "ai_planning_brief": True}
    policy = resolve_policy("fashion", flags, {}, task_name="planning_brief")
    assert policy.task_enabled
    assert not policy.aggregate_context
    assert not policy.product_names
    policy = resolve_policy("fashion", flags, {"ai": {"allow_aggregate_context": True}}, task_name="planning_brief")
    assert policy.aggregate_context
    assert not resolve_policy("fashion", flags, {}, task_name="weekly_summary").task_enabled
    disabled = resolve_policy("pharma", flags, {"ai": {"allow_aggregate_context": True}}, task_name="planning_brief")
    assert disabled.sharing == "disabled"
    assert not disabled.aggregate_context
    malformed = resolve_policy("fashion", flags, {"ai": {"allow_aggregate_context": "yes"}}, task_name="planning_brief")
    assert not malformed.aggregate_context


async def test_nonmapping_tasks_require_current_actor_and_independent_flag():
    ctx = AIContext(uuid.uuid4(), uuid.uuid4(), IndustryCode.fashion, task_name="planning_brief")
    db = FakeDB([SimpleNamespace(role="viewer"), SimpleNamespace(settings={"ai": {"allow_aggregate_context": True}}),
                 SimpleNamespace(feature_flags={"ai_enabled": True, "ai_import_mapping": True})])
    assert not (await PolicyStore(db).load(ctx)).task_enabled
    with pytest.raises(AIError, match="invalid_input"):
        resolve_policy("fashion", {}, {}, task_name="send_anything")


def test_cache_separates_task_schema_language_actor_and_snapshot():
    from app.services.llm.state import cache_key
    from test_config import settings
    args = dict(tenant="t", policy="headers_only", payload={}, config=settings())
    original = cache_key(**args)
    for extra in [{"task_name": "planning_brief"}, {"schema_version": "2"}, {"language": "hi"},
                  {"actor_scope": "viewer-a"}, {"snapshot": "another-run"}]:
        assert cache_key(**args, **extra) != original
