import json

import pytest

from app.services.llm.contracts import Column
from app.services.llm.errors import AIError
from app.services.llm.import_plan_task import PlanInput, validate_plan
from app.services.llm.policy import Policy, project_input
from app.services.llm.tasks import TASK_NAMES, TaskRequest, get_task

TASK = PlanInput(columns=[Column(id="c1", label="Stock No", kind="text"), Column(id="c2", label="Qty", kind="integer")],
                 allowed_fields=["sku", "quantity", "style"], row_count=10)


def ok(**over):
    body = {"selections": [{"column_id": "c1", "field": "sku", "confidence": "high"},
                           {"column_id": "c2", "field": "quantity", "confidence": "medium"}],
            "destinations": ["period_sales"], "reason": None}
    body.update(over)
    return json.dumps(body)


def test_registered_with_its_own_flag():
    assert "import_plan" in TASK_NAMES
    spec = get_task("import_plan")
    assert spec.input_model is PlanInput
    assert spec.flag == "ai_import_plan"
    assert TaskRequest("import_plan", TASK).spec == spec


def test_accepts_valid_plan():
    plan = validate_plan(ok(), TASK)
    assert plan.destinations == ["period_sales"]
    assert plan.selections[0].field == "sku"


def test_unusable_needs_a_reason():
    assert validate_plan(ok(destinations=[], reason="no_item_column"), TASK).reason == "no_item_column"
    with pytest.raises(AIError):
        validate_plan(ok(destinations=[], reason=None), TASK)


@pytest.mark.parametrize("bad", [
    ok(selections=[{"column_id": "c9", "field": "sku", "confidence": "high"},
                   {"column_id": "c2", "field": None, "confidence": "low"}]),
    ok(destinations=["delete_everything"]),
    ok(selections=[{"column_id": "c1", "field": "sku", "confidence": "high"},
                   {"column_id": "c2", "field": "sku", "confidence": "high"}]),
    ok(selections=[{"column_id": "c1", "field": "price", "confidence": "high"},
                   {"column_id": "c2", "field": None, "confidence": "low"}]),
    ok(selections=[{"column_id": "c1", "field": "sku", "confidence": "high"}]),
    ok(extra="DROP TABLE"),
    "not json",
])
def test_rejects_invented_ids_fields_and_destinations(bad):
    with pytest.raises(AIError):
        validate_plan(bad, TASK)


def test_projection_sends_structure_not_values():
    policy = Policy(True, True, "headers_only")
    payload = project_input(TASK, policy, [{"c1": "SECRET-SKU", "c2": 3}])
    assert payload["row_count"] == 10
    assert "examples" not in payload
    assert "SECRET-SKU" not in json.dumps(payload)
