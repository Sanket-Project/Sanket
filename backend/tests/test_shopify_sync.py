"""Unit tests for the pure Shopify→SANKET mapping helpers.

These cover the field mapping that's easy to get wrong, with no DB or network —
the payloads mirror the shape Shopify's Admin REST API returns.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import uuid

from app.services.integrations.shopify_client import (
    normalize_shop_domain,
    verify_webhook_hmac,
)
from app.services.integrations.shopify_sync import (
    SALES_SOURCE,
    order_to_sale_rows,
    product_to_row,
    variant_to_row,
)

SAMPLE_PRODUCT = {
    "id": 8001,
    "title": "Cordless Drill",
    "vendor": "TorqueMax",
    "product_type": "Power Tools",
    "status": "active",
    "handle": "cordless-drill",
    "tags": "tools, sale",
    "variants": [
        {"id": 9001, "sku": "DRILL-18V", "title": "18V", "price": "149.00",
         "barcode": "0123456789012", "inventory_item_id": 5001, "grams": 1500},
        {"id": 9002, "sku": "", "title": "12V", "price": "99.00",
         "barcode": None, "inventory_item_id": 5002},
    ],
}


def test_product_to_row_maps_core_fields() -> None:
    row = product_to_row(SAMPLE_PRODUCT, "hardware")
    assert row["external_id"] == "8001"
    assert row["name"] == "Cordless Drill"
    assert row["brand"] == "TorqueMax"
    assert row["category"] == "Power Tools"
    assert row["status"] == "active"
    assert row["attributes"]["shopify_handle"] == "cordless-drill"


def test_product_to_row_defaults_category_when_blank() -> None:
    row = product_to_row({"id": 1, "title": "X", "product_type": ""}, "hardware")
    assert row["category"] == "Uncategorized"


def test_product_to_row_non_active_status() -> None:
    row = product_to_row({"id": 1, "title": "X", "status": "archived"}, "hardware")
    assert row["status"] == "discontinued"


def test_variant_to_row_uses_sku_and_extracts_barcode() -> None:
    row = variant_to_row(SAMPLE_PRODUCT["variants"][0], industry="hardware", currency="USD")
    assert row["sku_code"] == "DRILL-18V"
    assert row["external_id"] == "9001"
    assert row["unit_price"] == 149.0
    assert row["currency"] == "USD"
    # Barcode goes into attributes, NOT the gtin column.
    assert row["attributes"]["barcode"] == "0123456789012"
    assert row["attributes"]["inventory_item_id"] == 5001


def test_variant_to_row_falls_back_to_shopify_id_when_sku_blank() -> None:
    row = variant_to_row(SAMPLE_PRODUCT["variants"][1], industry="hardware", currency="EUR")
    assert row["sku_code"] == "shopify-9002"
    assert row["unit_price"] == 99.0


def test_order_to_sale_rows_resolves_variants_and_computes_revenue() -> None:
    sku_a, sku_b = uuid.uuid4(), uuid.uuid4()
    variant_to_sku = {"9001": sku_a, "9002": sku_b}
    order = {
        "id": 777,
        "created_at": "2026-01-15T10:30:00-05:00",
        "line_items": [
            {"id": 1, "variant_id": 9001, "quantity": 3, "price": "149.00"},
            {"id": 2, "variant_id": 9002, "quantity": 2, "price": "99.00"},
            {"id": 3, "variant_id": 5555, "quantity": 1, "price": "10.00"},  # unknown → skip
            {"id": 4, "variant_id": 9001, "quantity": 0, "price": "149.00"},  # zero → skip
        ],
    }
    rows = order_to_sale_rows(order, variant_to_sku, "hardware")
    assert len(rows) == 2
    first = rows[0]
    assert first["sku_id"] == sku_a
    assert first["units_sold"] == 3
    assert first["gross_revenue"] == 447.0
    assert first["channel"] == SALES_SOURCE
    assert first["metadata_"]["source"] == SALES_SOURCE
    assert first["metadata_"]["order_id"] == 777
    # sale_time parsed with timezone
    assert rows[0]["sale_time"].year == 2026


def test_order_with_no_resolvable_lines_returns_empty() -> None:
    rows = order_to_sale_rows(
        {"id": 1, "created_at": "2026-01-01T00:00:00Z", "line_items": [
            {"id": 1, "variant_id": None, "quantity": 1, "price": "5.00"},
        ]},
        {},
        "hardware",
    )
    assert rows == []


def test_normalize_shop_domain_variants() -> None:
    assert normalize_shop_domain("my-store") == "my-store.myshopify.com"
    assert normalize_shop_domain("my-store.myshopify.com") == "my-store.myshopify.com"
    assert normalize_shop_domain("https://my-store.myshopify.com/") == "my-store.myshopify.com"
    assert normalize_shop_domain("  My-Store  ") == "my-store.myshopify.com"


def _sign(secret: str, body: bytes) -> str:
    return base64.b64encode(
        hmac.new(secret.encode(), body, hashlib.sha256).digest()
    ).decode()


def test_verify_webhook_hmac_accepts_valid_signature() -> None:
    body = b'{"id":123,"line_items":[]}'
    secret = "super-secret-key"
    assert verify_webhook_hmac(secret, body, _sign(secret, body)) is True


def test_verify_webhook_hmac_rejects_tampered_or_missing() -> None:
    body = b'{"id":123}'
    assert verify_webhook_hmac("super-secret-key", body, _sign("wrong-key", body)) is False
    assert verify_webhook_hmac("super-secret-key", body, None) is False
    assert verify_webhook_hmac("", body, "anything") is False
    # body tampered after signing
    sig = _sign("super-secret-key", body)
    assert verify_webhook_hmac("super-secret-key", b'{"id":999}', sig) is False
