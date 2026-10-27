
import pytest
from pydantic import ValidationError

from app.services.llm.contracts import (
    AIResult,
    Column,
    TaskInput,
    validate_output,
)
from app.services.llm.errors import AIError


def task_input():
    return TaskInput(columns=[Column(id="c1", label="Qty Sold (Pcs)", kind="integer")],
                     allowed_fields=["quantity"])


def test_result_contract():
    assert AIResult(state="disabled", reason="feature_disabled").value is None
    with pytest.raises(ValidationError):
        AIResult(state="success")
    with pytest.raises(ValidationError):
        AIResult(state="unavailable", reason="raw secret error")
    with pytest.raises(ValidationError):
        AIResult(state="disabled", prompt="secret")


def test_bound_output_to_supplied_ids():
    output = validate_output('{"selections":[{"column_id":"c1","field":"quantity",'
                             '"confidence":"high","reason":"header_meaning"}]}', task_input())
    assert output.selections[0].field == "quantity"
    assert output.selections[0].confidence == "high"


@pytest.mark.parametrize("content", [
    "", "not json", '{"selections":[],"extra":"SQL"}',
    '{"selections":[{"column_id":"c2","field":"quantity","confidence":"high"}]}',
    '{"selections":[{"column_id":"c1","field":"revenue","confidence":"high"}]}',
    '{"selections":[{"column_id":"c1","field":"quantity","confidence":0.99}]}',
    '{"selections":[{"column_id":"c1","field":"quantity","confidence":"high","value":42}]}',
    '{"selections":[{"column_id":"c1","field":"quantity","confidence":"high"},'
    '{"column_id":"c1","field":null,"confidence":"low"}]}',
])
def test_invalid_contract(content):
    with pytest.raises(AIError, match="invalid_output"):
        validate_output(content, task_input())


def test_duplicates_and_bounds():
    with pytest.raises(ValidationError):
        TaskInput(columns=[Column(id="c1", label="x"), Column(id="c1", label="y")], allowed_fields=[])
    with pytest.raises(ValidationError):
        Column(id="c1", label="x" * 513)
    with pytest.raises(ValidationError):
        TaskInput(columns=[], allowed_fields=["write_sql"])
