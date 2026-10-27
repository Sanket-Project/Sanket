"""Rules planner for smart import: where a report's columns go, and which destinations it can feed.

Deterministic first. The AI suggestion (``import_plan`` task) may fill fields the
rules left unmapped and pick destinations; it never overrides a rules mapping.
"""
from __future__ import annotations

from app.services.integrations.file_import import _build_header_map, _norm

DESTINATIONS = ("products", "inventory", "sales", "period_sales")

#: Fields each destination reads. ``style`` and ``cogs`` exist only for the planner.
DESTINATION_FIELDS: dict[str, tuple[str, ...]] = {
    "products": ("sku", "name", "brand", "category", "description", "gtin", "price", "size", "color", "currency"),
    "inventory": ("sku", "available", "reserved", "inbound", "warehouse"),
    "sales": ("sku", "name", "quantity", "timestamp", "price", "revenue", "discount", "channel", "region",
              "order_id", "line_id", "in_stock", "stockout", "returns", "warehouse", "currency"),
    "period_sales": ("sku", "quantity", "revenue", "cogs", "warehouse"),
}
PLAN_FIELDS: tuple[str, ...] = tuple(dict.fromkeys(
    [f for fields in DESTINATION_FIELDS.values() for f in fields] + ["style"]))

#: Any-of groups that must each have a mapped field.
REQUIRED: dict[str, list[tuple[str, ...]]] = {
    "products": [("sku", "name")],
    "inventory": [("sku",), ("available",)],
    "sales": [("sku", "name"), ("quantity",), ("timestamp",)],
    "period_sales": [("sku",), ("quantity",)],
}

# Report-export spellings seen in Indian retail POS/ERP exports. Applied only by
# this planner, after the shared aliases, and only to fields still unmapped.
_EXTRA: dict[str, set[str]] = {
    "sku": {"stockno", "stockcode", "barcodeno"},
    "available": {"closingbalqty", "closingqty", "closingstock", "balanceqty"},
    "warehouse": {"companyname", "storename", "branch", "outlet", "store"},
    "description": {"itemdescription", "itemdesc"},
    "style": {"styleno", "style", "stylenumber", "stylecode", "designno", "designnumber"},
    "cogs": {"costofgoodswithouttax", "costofgoods"},
    "revenue": {"netsalesvalue", "netsales", "netamount"},
}
_RETAIL = ("retailprice", "mrp", "sellingprice", "saleprice", "price", "unitprice")


def rules_mapping(columns) -> dict[str, str]:
    """field → column id from header names alone."""
    by_label = {}
    for column in columns:
        by_label.setdefault(column.label, column.id)
    mapping = {f: by_label[label] for f, label in _build_header_map(list(by_label)).items() if f in PLAN_FIELDS}
    norms = {column.id: _norm(column.label) for column in columns}
    retail = next((cid for name in _RETAIL for cid, n in norms.items() if n == name), None)
    if retail:
        mapping["price"] = retail
    for field, aliases in _EXTRA.items():
        if field in mapping:
            continue
        used = set(mapping.values())
        match = next((cid for cid, n in norms.items() if n in aliases and cid not in used), None)
        if match:
            mapping[field] = match
    if "timestamp" not in mapping:
        used = set(mapping.values())
        dated = next((c.id for c in columns if c.kind == "date" and c.id not in used), None)
        if dated:
            mapping["timestamp"] = dated
    return mapping


def rules_destinations(mapping: dict[str, str], columns) -> tuple[list[str], str | None]:
    """Destinations the mapped fields can feed, or ``([], reason)`` when nothing can be imported."""
    if "sku" not in mapping and "name" not in mapping:
        return [], "no_item_column"
    if "available" in mapping:
        quantity = "inventory"
    elif "quantity" in mapping and "timestamp" in mapping:
        quantity = "sales"
    elif "quantity" in mapping:
        quantity = "period_sales"
    else:
        quantity = None
    catalogue = any(f in mapping for f in ("brand", "category", "price", "description", "size", "color"))
    destinations = (["products"] if catalogue or quantity is None else []) + ([quantity] if quantity else [])
    return destinations, None


def missing_fields(destination: str, mapping: dict[str, str], *, period) -> list[str]:
    missing = [group[0] for group in REQUIRED[destination] if not any(f in mapping for f in group)]
    if destination == "period_sales" and not period:
        missing.append("period")
    return missing


def merge_ai(mapping: dict[str, str], destinations: list[str], suggestion: dict) -> tuple[dict, list[str], dict]:
    """Fill unmapped fields from an AI suggestion; take its destinations when it gave valid ones."""
    merged = dict(mapping)
    provenance: dict[str, str] = {}
    for selection in suggestion.get("selections", []):
        field, column = selection.get("field"), selection.get("column_id")
        if field in PLAN_FIELDS and field not in merged and column not in merged.values():
            merged[field] = column
            provenance[column] = "ai"
    proposed = [d for d in suggestion.get("destinations", []) if d in DESTINATIONS]
    return merged, (proposed or list(destinations)), provenance

