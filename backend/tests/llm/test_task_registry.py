import json

import pytest
from pydantic import ValidationError

from app.services.llm.contracts import Column, TaskInput
from app.services.llm.errors import AIError


def test_mapping_registry_preserves_strict_contract():
    from app.services.llm.tasks import get_task, request_for
    task = TaskInput(columns=[Column(id="c1", label="मात्रा")], allowed_fields=["quantity"])
    request = request_for("import_mapping", task.model_dump())
    assert request.name == "import_mapping"
    assert request.schema_version == "1"
    assert request.input == task
    output = request.validate(json.dumps({"selections": [{"column_id": "c1", "field": "quantity", "confidence": "high"}]}))
    assert output.selections[0].field == "quantity"
    assert get_task("import_mapping").flag == "ai_import_mapping"
    with pytest.raises(ValidationError):
        request_for("import_mapping", {**task.model_dump(), "instructions": "write SQL"})


def test_registry_rejects_unknown_tasks_and_mapping_identifiers():
    from app.services.llm.tasks import get_task, request_for
    with pytest.raises(AIError, match="invalid_input"):
        get_task("arbitrary_prompt")
    request = request_for("import_mapping", {"columns": [{"id": "c1", "label": "Qty"}], "allowed_fields": ["quantity"]})
    with pytest.raises(AIError, match="invalid_output"):
        request.validate('{"selections":[{"column_id":"foreign","field":"quantity","confidence":"high"}]}')
