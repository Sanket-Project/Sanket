import re

import pytest

from app.services.llm.facts import Fact, NarrativeInput, NarrativeOutput, render_narrative
from app.services.notifications.localization import CATALOG, translate


@pytest.mark.parametrize("language", ["hi", "te", "ta"])
def test_labels_units_and_status_localize_without_changing_facts(language):
    task = NarrativeInput(snapshot="s1", language=language, facts=[
        Fact(id="stock", label="Recorded stock", value="123.45", unit="units", period="7 days", source="/inventory", snapshot="s1"),
        Fact(id="state", label="Connector availability", value="planned", kind="status", source="/integrations", snapshot="s1"),
    ])
    result = render_narrative(task, NarrativeOutput(blocks=[{"proposition": "fact", "fact_ids": ["stock", "state"]}]))
    assert "Recorded stock" not in result[0]["text"]
    assert "units" not in result[0]["text"]
    assert "days" not in result[0]["text"]
    assert "planned" not in result[0]["text"]
    assert "123.45" in result[0]["text"]
    assert result[0]["sources"] == [{"fact_id": "stock", "href": "/inventory"}, {"fact_id": "state", "href": "/integrations"}]
    assert task.facts[0].value == "123.45"


@pytest.mark.parametrize("language", ["hi", "te", "ta"])
def test_dynamic_provenance_and_financial_disclosures_keep_placeholders(language):
    text = "Values describe the saved decision at 2026-10-27T12:34:56+00:00"
    assert translate(text, language) != text
    assert "2026-10-27T12:34:56+00:00" in translate(text, language)
    basis = "Only 7 comparable week(s) so far — need at least 8."
    translated = translate(basis, language)
    assert translated != basis
    assert re.findall(r"\d+", translated) == ["7", "8"]


def test_every_catalog_entry_has_all_languages_and_identical_placeholders():
    for english, translations in CATALOG.items():
        assert set(translations) == {"hi", "te", "ta"}, english
        for localized in translations.values():
            assert localized and localized != english
            assert sorted(re.findall(r"\{[^}]+\}", english)) == sorted(re.findall(r"\{[^}]+\}", localized)), english


def test_unknown_source_names_and_currency_codes_are_not_fabricated_translations():
    assert translate("INR", "te") == "INR"
    assert translate("A source system supplied this item name", "hi") == "A source system supplied this item name"


@pytest.mark.parametrize("language", ["hi", "te", "ta"])
def test_supplier_approval_fact_has_regional_label(language):
    assert translate("Approved order quantity", language) != "Approved order quantity"
