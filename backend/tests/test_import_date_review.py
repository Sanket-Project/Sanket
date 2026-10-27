import pytest


def test_ambiguous_dates_need_explicit_interpretation_and_never_guess():
    from app.services.integrations.import_dates import date_preview, resolve_dates
    rows = [{"c1": "A", "c3": "01/02/2026"}, {"c1": "B", "c3": "13/02/2026"}]
    preview = date_preview(rows, "c3", [4, 5])
    assert preview[0] == {"row": 4, "value": "01/02/2026", "dmy": "2026-02-01", "mdy": "2026-01-02"}
    with pytest.raises(ValueError, match="date order"):
        resolve_dates(rows, "c3", None)
    resolved = resolve_dates(rows, "c3", "dmy")
    assert resolved[0]["c3"] == "2026-02-01"
    assert resolved[1]["c3"] == "2026-02-13"
    assert rows[0]["c3"] == "01/02/2026"
    with pytest.raises(ValueError, match="date"):
        resolve_dates(rows, "c3", "mdy")


def test_iso_dates_unchanged_and_invalid_numeric_dates_rejected():
    from app.services.integrations.import_dates import resolve_dates
    assert resolve_dates([{"date": "2026-02-01"}], "date", None)[0]["date"] == "2026-02-01"
    with pytest.raises(ValueError, match="date"):
        resolve_dates([{"date": "31/02/2026"}], "date", "dmy")
