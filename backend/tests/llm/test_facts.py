import json

import pytest
from pydantic import ValidationError

from app.services.llm.errors import AIError


def ledger(**changes):
    from app.services.llm.facts import Fact, NarrativeInput
    return NarrativeInput(snapshot="run-a", language="en", facts=[Fact(
        id="cover", label="Stock cover", value="4.5", unit="days", source="/inventory",
        snapshot="run-a", kind="metric", **changes)])


def test_grounded_fact_renderer_owns_values_and_sources():
    from app.services.llm.facts import render_narrative
    from app.services.llm.tasks import request_for
    data = ledger()
    task = request_for("planning_brief", data.model_dump())
    output = task.validate('{"blocks":[{"proposition":"fact","fact_ids":["cover"]}]}')
    rendered = render_narrative(data, output)
    assert rendered[0]["text"] == "Stock cover: 4.5 days."
    assert rendered[0]["sources"] == [{"fact_id": "cover", "href": "/inventory"}]
    assert "4.5" not in task.spec.system


@pytest.mark.parametrize("body", [
    {"blocks": [{"proposition": "fact", "fact_ids": ["foreign"]}]},
    {"blocks": [{"proposition": "fact", "fact_ids": ["cover"], "text": "Buy fifty units"}]},
    {"blocks": [{"proposition": "caused_by_weather", "fact_ids": ["cover"]}]},
    {"blocks": [{"proposition": "data_gap", "fact_ids": ["cover"]}]},
])
def test_unbound_claims_and_false_propositions_fail(body):
    from app.services.llm.tasks import request_for
    with pytest.raises(AIError, match="invalid_output"):
        request_for("planning_brief", ledger().model_dump()).validate(json.dumps(body))


def test_fact_scope_and_bounds_reject_bad_sources_snapshots_values():
    from app.services.llm.facts import Fact, NarrativeInput
    for change in [{"source": "https://bad.test/steal"}, {"source": "//bad.test"},
                   {"source": "/inventory?token=secret"}, {"value": "NaN"}, {"value": "9999 units guessed"}]:
        raw = dict(id="f", label="Stock", value="5", unit="units", source="/inventory", snapshot="a")
        with pytest.raises(ValidationError):
            Fact(**{**raw, **change})
    with pytest.raises(ValidationError):
        NarrativeInput(snapshot="wrong", facts=ledger().facts)


@pytest.mark.parametrize("language", ["en", "hi", "te", "ta"])
def test_locales_preserve_quantities_and_citations(language):
    from app.services.llm.facts import render_narrative
    from app.services.llm.tasks import request_for
    data = ledger().model_copy(update={"language": language})
    result = render_narrative(data, request_for("roi_report", data.model_dump()).validate(
        '{"blocks":[{"proposition":"fact","fact_ids":["cover"]}]}'))
    assert "4.5" in result[0]["text"]
    assert result[0]["sources"][0]["fact_id"] == "cover"


def test_missing_facts_remain_explicit_and_cannot_be_rendered_as_known():
    from app.services.llm.facts import Fact, NarrativeInput, render_narrative
    from app.services.llm.tasks import request_for
    data = NarrativeInput(snapshot="a", facts=[Fact(id="cost", label="Unit cost", value=None,
                                                  source="/products", snapshot="a")])
    task = request_for("roi_report", data.model_dump())
    with pytest.raises(AIError, match="invalid_output"):
        task.validate('{"blocks":[{"proposition":"fact","fact_ids":["cost"]}]}')
    output = task.validate('{"blocks":[{"proposition":"missing","fact_ids":["cost"]}]}')
    assert "unavailable" in render_narrative(data, output)[0]["text"]
