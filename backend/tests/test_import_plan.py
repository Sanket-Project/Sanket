from app.services.integrations import import_plan as p
from app.services.integrations.import_layout import PhysicalColumn


def cols(*labels, kinds=None):
    out = [PhysicalColumn(f"c{i+1}", label, label) for i, label in enumerate(labels)]
    for column, kind in zip(out, kinds or [], strict=False):
        column.kind = kind
    return out


STOCK = cols("Company Name", "Stock No", "Item Description", "Category", "Brand", "Style No",
             "Sub Category", "Cost Price", "Retail Price", "Closing Bal.Qty", "Closing Bal.Val")
GROSS = cols("Company Name", "Stock No", "Item Description", "Brand", "Sales Qty", "Net Sales Value",
             "Sale Value (Without Tax)", "Cost of Goods (With Tax)", "Cost of Goods (Without Tax)")
DSR = cols("Company Name", "Voucher Date", "Type", "Total Sales Bill", "Sales Qty", "Sales Amount",
           kinds=["text", "date", "text", "integer", "integer", "integer"])
PURCHASE = cols("Voucher Type", "Voucher Date", "Voucher Number", "Party Name", "Quantity",
                kinds=["text", "date", "text", "text", "integer"])
LEDGER = cols("SKU", "Qty", "Order Date", kinds=["text", "integer", "date"])


def test_stock_balance_maps_to_products_and_inventory_with_retail_price():
    m = p.rules_mapping(STOCK)
    expected = {"sku": "c2", "available": "c10", "warehouse": "c1", "price": "c9", "style": "c6",
                "description": "c3", "brand": "c5", "category": "c4"}
    assert {k: m.get(k) for k in expected} == expected
    assert p.rules_destinations(m, STOCK) == (["products", "inventory"], None)
    assert p.missing_fields("inventory", m, period=None) == []


def test_gross_profit_is_period_sales_and_needs_a_period():
    m = p.rules_mapping(GROSS)
    assert (m["quantity"], m["revenue"]) == ("c5", "c6")
    assert p.rules_destinations(m, GROSS) == (["products", "period_sales"], None)
    assert p.missing_fields("period_sales", m, period=None) == ["period"]
    assert p.missing_fields("period_sales", m, period=("2026-01-01", "2026-10-25")) == []


def test_store_day_totals_and_invoice_lists_are_unusable():
    for columns in (DSR, PURCHASE):
        m = p.rules_mapping(columns)
        assert p.rules_destinations(m, columns) == ([], "no_item_column")


def test_dated_item_lines_are_sales():
    m = p.rules_mapping(LEDGER)
    assert m["timestamp"] == "c3"
    assert p.rules_destinations(m, LEDGER) == (["sales"], None)


def test_missing_fields_reports_required_groups():
    assert p.missing_fields("inventory", {"sku": "c1"}, period=None) == ["available"]
    assert p.missing_fields("sales", {"quantity": "c2"}, period=None) == ["sku", "timestamp"]


def test_ai_fills_gaps_but_never_replaces():
    m = {"sku": "c2"}
    suggestion = {"selections": [{"column_id": "c2", "field": "name"}, {"column_id": "c5", "field": "quantity"},
                                 {"column_id": "c7", "field": "sku"}],
                  "destinations": ["period_sales"]}
    mapping, dest, provenance = p.merge_ai(m, ["products"], suggestion)
    assert mapping == {"sku": "c2", "quantity": "c5"}
    assert dest == ["period_sales"]
    assert provenance == {"c5": "ai"}


def test_ai_without_destinations_keeps_rules_destinations():
    mapping, dest, provenance = p.merge_ai({"sku": "c1"}, ["products"], {"selections": [], "destinations": []})
    assert (dest, provenance) == (["products"], {})
