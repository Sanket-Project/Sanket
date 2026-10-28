import pytest

from app.services.notifications.localization import translate, CATALOG


def test_every_catalog_entry_has_four_languages_and_no_fact_placeholders_added():
    for english, row in CATALOG.items():
        assert set(row) == {"hi", "te", "ta"}
        assert all(row.values())
        assert not any(char.isdigit() for char in "".join(row.values())) or any(char.isdigit() for char in english)


@pytest.mark.parametrize("language", ["hi", "te", "ta"])
def test_localized_labels_retain_fact_values_outside_translation(language):
    assert translate("Realised savings", language) != "Realised savings"
    assert translate("INR", language) == "INR"
    assert translate("1234.50", language) == "1234.50"
