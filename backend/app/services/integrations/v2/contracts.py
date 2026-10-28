"""Fashion Retail V2 Canonical CSV Contracts, Schema Detection, and Sanitization.

Exact definitions from DATA_DICTIONARY.md and ARCHITECTURE.md:
- retail_v2.0.products
- retail_v2.0.skus
- retail_v2.0.inventory
- retail_v2.0.sales
- retail_v2.0.returns
- retail_v2.0.purchases
- retail_v2.0.suppliers
- retail_v2.0.locations
"""

from __future__ import annotations

import csv
import io
import re
from typing import Any

SCHEMA_PRODUCTS = "retail_v2.0.products"
SCHEMA_SKUS = "retail_v2.0.skus"
SCHEMA_INVENTORY = "retail_v2.0.inventory"
SCHEMA_SALES = "retail_v2.0.sales"
SCHEMA_RETURNS = "retail_v2.0.returns"
SCHEMA_PURCHASES = "retail_v2.0.purchases"
SCHEMA_SUPPLIERS = "retail_v2.0.suppliers"
SCHEMA_LOCATIONS = "retail_v2.0.locations"

ALL_V2_SCHEMAS = (
    SCHEMA_PRODUCTS,
    SCHEMA_SKUS,
    SCHEMA_INVENTORY,
    SCHEMA_SALES,
    SCHEMA_RETURNS,
    SCHEMA_PURCHASES,
    SCHEMA_SUPPLIERS,
    SCHEMA_LOCATIONS,
)

CONTRACT_HEADERS: dict[str, list[str]] = {
    SCHEMA_PRODUCTS: [
        "schema_version",
        "product_code",
        "product_name",
        "brand_code",
        "category_code",
        "style_number",
        "description",
        "collection_code",
        "season_code",
        "status",
        "hsn_code",
        "tax_class_code",
        "manufacturer_supplier_code",
        "image_urls",
        "attributes_json",
    ],
    SCHEMA_SKUS: [
        "schema_version",
        "sku_code",
        "product_code",
        "external_sku_id",
        "color_code",
        "color_name",
        "size_code",
        "size_system",
        "barcode",
        "gtin",
        "mrp_incl_tax",
        "selling_price_incl_tax",
        "reference_cost_ex_tax",
        "currency",
        "price_valid_from",
        "status",
        "attributes_json",
    ],
    SCHEMA_INVENTORY: [
        "schema_version",
        "snapshot_id",
        "as_of",
        "sku_code",
        "location_code",
        "on_hand_qty",
        "reserved_qty",
        "damaged_qty",
        "quarantine_qty",
        "in_transit_qty",
        "open_po_qty",
        "source_system",
        "count_reference",
        "reported_stock_value_ex_tax",
        "currency",
    ],
    SCHEMA_SALES: [
        "schema_version",
        "source_system",
        "transaction_id",
        "order_id",
        "order_line_id",
        "transaction_at",
        "sku_code",
        "location_code",
        "fulfillment_location_code",
        "channel_code",
        "quantity_sold",
        "returns",
        "unit_price_ex_tax",
        "mrp_incl_tax",
        "discount_ex_tax",
        "tax_code",
        "tax_rate_pct",
        "tax_amount",
        "currency",
        "order_status",
        "invoice_number",
        "place_of_supply_state_code",
        "payment_method",
        "payment_reference",
        "payment_amount",
    ],
    SCHEMA_RETURNS: [
        "schema_version",
        "source_system",
        "return_id",
        "return_line_id",
        "return_at",
        "original_source_system",
        "original_transaction_id",
        "original_order_line_id",
        "sku_code",
        "location_code",
        "returns",
        "return_value_ex_tax",
        "tax_code",
        "tax_amount",
        "currency",
        "reason_code",
        "disposition",
        "credit_note_number",
        "refund_reference",
        "refund_amount",
        "refund_method",
        "refund_at",
        "exchange_order_id",
        "status",
    ],
    SCHEMA_PURCHASES: [
        "schema_version",
        "source_system",
        "document_type",
        "document_id",
        "document_line_id",
        "document_at",
        "supplier_code",
        "sku_code",
        "location_code",
        "po_id",
        "po_line_id",
        "related_document_id",
        "related_document_line_id",
        "quantity",
        "unit_cost_ex_tax",
        "discount_ex_tax",
        "freight_ex_tax",
        "tax_code",
        "tax_rate_pct",
        "tax_amount",
        "currency",
        "invoice_number",
        "expected_delivery_date",
        "status",
    ],
    SCHEMA_SUPPLIERS: [
        "schema_version",
        "supplier_code",
        "supplier_name",
        "supplier_type",
        "gstin",
        "state_code",
        "country_code",
        "currency",
        "payment_terms_days",
        "default_lead_time_days",
        "contact_email",
        "phone",
        "address",
        "status",
    ],
    SCHEMA_LOCATIONS: [
        "schema_version",
        "location_code",
        "location_name",
        "location_type",
        "parent_location_code",
        "timezone",
        "state_code",
        "country_code",
        "address",
        "fulfills_orders",
        "status",
    ],
}

_HEADERS_TO_SCHEMA: dict[tuple[str, ...], str] = {
    tuple(cols): schema for schema, cols in CONTRACT_HEADERS.items()
}

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def escape_formula(value: Any) -> Any:
    """Escape text that begins with spreadsheet formula triggers (=, +, -, @, \\t, \\r)."""
    if not isinstance(value, str):
        return value
    if value.startswith(_FORMULA_PREFIXES):
        return f"'{value}"
    return value


def detect_v2_schema(headers: list[str], sample_row: dict[str, Any] | None = None) -> str | None:
    """Detect whether a set of headers or sample row corresponds to a V2 contract.

    Returns the canonical schema_version string (e.g. 'retail_v2.0.sales') or None.
    """
    if sample_row and "schema_version" in sample_row:
        sv = str(sample_row.get("schema_version") or "").strip()
        if sv in ALL_V2_SCHEMAS:
            return sv

    clean_headers = [str(h).strip() for h in headers if h is not None]
    return _HEADERS_TO_SCHEMA.get(tuple(clean_headers))


def parse_v2_csv(content: bytes) -> tuple[list[str], list[dict[str, Any]]]:
    """Parse CSV bytes into headers and rows with UTF-8 BOM tolerance."""
    text = content.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    try:
        first = next(reader)
    except StopIteration as exc:
        raise ValueError("CSV is empty") from exc

    headers = [str(col).strip() for col in first]
    if not headers or any(not header for header in headers):
        raise ValueError("CSV headers must not be blank")
    normalized = [re.sub(r"[\s_]+", "_", header.casefold()) for header in headers]
    if len(set(normalized)) != len(normalized):
        raise ValueError("CSV contains duplicate or normalization-colliding headers")
    rows: list[dict[str, Any]] = []
    for r in reader:
        if not r or all(c.strip() == "" for c in r):
            continue
        if len(r) != len(headers):
            raise ValueError(
                f"CSV row {reader.line_num} has {len(r)} cells; expected {len(headers)}"
            )
        row_dict = {headers[i]: r[i].strip() for i in range(len(headers))}
        rows.append(row_dict)
    return headers, rows
