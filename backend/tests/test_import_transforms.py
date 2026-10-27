from datetime import date

from app.services.integrations import import_transforms as t


def test_summary_rows_need_blank_identity_and_total_label():
    assert t.is_summary_row({"c1": "", "c2": "", "c3": "Grand Total : ", "c10": "38419"}, ["c2"])
    assert t.is_summary_row({"c1": "Sub Total : ", "c4": 971}, ["c9"])
    assert not t.is_summary_row({"c2": "TOTAL-01", "c3": "Grand Total"}, ["c2"])
    assert not t.is_summary_row({"c2": "", "c3": "Kurta"}, ["c2"])


def test_parse_variant_spaced_and_compact():
    assert t.parse_variant("WESTREN - Straight Pant - SUKANYA - 49159 - STEEL GREY - L") == ("STEEL GREY", "L")
    assert t.parse_variant("KURTIS - KURTIS - MYVI - 0007 - NA - 0L") == (None, "0L")
    assert t.parse_variant("KURTHI-ZOLA-81807-NA-00M") == (None, "00M")
    assert t.parse_variant("mix-KINZA-2917-ASST-S TO XXL") == ("ASST", "S TO XXL")
    assert t.parse_variant("") == (None, None)
    assert t.parse_variant(None) == (None, None)
    assert t.parse_variant("ONEWORD") == (None, None)


def test_size_codes_suggest_only_known_sizes():
    out = t.size_codes(["0L", "0L", "XL", "2XL", "free", None, ""])
    assert out[0] == {"code": "0L", "count": 2, "suggestion": None}
    assert {"code": "2XL", "count": 1, "suggestion": "XXL"} in out
    assert {"code": "FREE", "count": 1, "suggestion": "FREE"} in out
    assert len(out) == 4


def test_group_pieces_sums_per_location_and_counts_conflicts():
    rows = [
        {"b": "SUKANYA", "s": "49159", "col": "WHITE", "sz": "L", "loc": "ALWAL", "q": 1, "p": 699},
        {"b": "SUKANYA", "s": "49159", "col": "WHITE", "sz": "L", "loc": "ALWAL", "q": "2.0000", "p": 799},
        {"b": "SUKANYA", "s": "49159", "col": "WHITE", "sz": "L", "loc": "WH", "q": 5, "p": 699},
        {"b": "MYVI", "s": "0007", "col": None, "sz": "0L", "loc": "ALWAL", "q": 1, "p": 699},
    ]
    out, conflicts = t.group_pieces(rows, brand="b", style="s", colour="col", size="sz", location="loc", sums=["q"])
    by = {(r["x_sku"], r["loc"]): r for r in out}
    assert by[("SUKANYA-49159-WHITE-L", "ALWAL")]["q"] == 3
    assert by[("SUKANYA-49159-WHITE-L", "WH")]["q"] == 5
    assert by[("SUKANYA-49159-WHITE-L", "ALWAL")]["p"] in (699, 799)
    assert ("MYVI-0007-0L", "ALWAL") in by
    assert conflicts == 1
    assert len(out) == 3


def test_group_pieces_without_location_merges_all_rows_of_a_variant():
    rows = [{"b": "A", "s": "1", "col": "RED", "sz": "M", "q": 1}, {"b": "A", "s": "1", "col": "RED", "sz": "M", "q": 4}]
    out, _ = t.group_pieces(rows, brand="b", style="s", colour="col", size="sz", location=None, sums=["q"])
    assert out == [{"b": "A", "s": "1", "col": "RED", "sz": "M", "q": 5, "x_sku": "A-1-RED-M"}]


def test_parse_period_from_letterhead():
    lines = ["Sai Balaji Fashions - WH\nGross Margin Report\nDate Range : 01-01-2026 - 25-10-2026"]
    assert t.parse_period(lines) == (date(2026, 1, 1), date(2026, 10, 25))
    assert t.parse_period(["no range here"]) is None
    assert t.parse_period(["Date Range : 25-10-2026 - 01-01-2026"]) is None


def test_parse_variant_keeps_blank_parts_in_place():
    assert t.parse_variant("WESTREN - Straight Pant - SUKANYA - 49159 -  - M") == (None, "M")


def test_parse_style_is_third_from_last():
    assert t.parse_style("WESTREN - Straight Pant - SUKANYA - 49159 - STEEL GREY - L") == "49159"
    assert t.parse_style("WESTREN - Straight Pant - SUKANYA - 49159 -  - M") == "49159"
    assert t.parse_style("mix-KINZA-2917-ASST-S TO XXL") == "2917"
    assert t.parse_style("PLAZO SETS - PLAZO SETS - 7SHADES - 7SHAD - NA - 0L") == "7SHAD"
    assert t.parse_style("A - B") is None


def test_group_conflicts_count_only_compared_columns():
    rows = [{"st": "1", "id": "P1", "p": 699, "q": 1}, {"st": "1", "id": "P2", "p": 699, "q": 1}]
    _, conflicts = t.group_pieces(rows, brand=None, style="st", colour=None, size=None, location=None,
                                  sums=["q"], compare=["p"])
    assert conflicts == 0
