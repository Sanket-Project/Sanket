"""Tests for V2 Catalog (Product & SKU) Validation."""

from __future__ import annotations

from decimal import Decimal
import pytest

from app.services.integrations.v2 import catalog as v2_catalog
from app.services.integrations.v2.contracts import SCHEMA_PRODUCTS, SCHEMA_SKUS


def test_validate_v2_product_row_valid():
    row = {
        "schema_version": SCHEMA_PRODUCTS,
        "product_code": "DEMO-KUR-001",
        "product_name": "Demo cotton printed kurti",
        "brand_code": "DEMO-BRAND",
        "category_code": "KURTI",
        "style_number": "DEMO-ST-101",
        "description": "Cotton printed straight kurti",
        "collection_code": "DEMO-FESTIVE-26",
        "season_code": "AW26",
        "status": "active",
        "hsn_code": "",
        "tax_class_code": "DEMO-TAX-5",
        "manufacturer_supplier_code": "DEMO-SUP-001",
        "image_urls": "",
        "attributes_json": '{"fabric":"cotton","pattern":"floral"}',
    }
    validated = v2_catalog.validate_product_row(row)
    assert validated.product_code == "DEMO-KUR-001"
    assert validated.category_code == "KURTI"
    assert validated.status == "active"
    assert validated.attributes == {"fabric": "cotton", "pattern": "floral"}


def test_validate_v2_product_rejects_missing_product_code():
    row = {
        "schema_version": SCHEMA_PRODUCTS,
        "product_code": "",
        "product_name": "Nameless kurti",
        "category_code": "KURTI",
        "status": "active",
    }
    with pytest.raises(v2_catalog.ValidationError, match="product_code is required"):
        v2_catalog.validate_product_row(row)


def test_validate_v2_product_rejects_missing_category_code():
    row = {
        "schema_version": SCHEMA_PRODUCTS,
        "product_code": "P-100",
        "product_name": "Kurti without category",
        "category_code": "",
        "status": "active",
    }
    with pytest.raises(v2_catalog.ValidationError, match="category_code is required"):
        v2_catalog.validate_product_row(row)


def test_validate_v2_product_rejects_invalid_status():
    row = {
        "schema_version": SCHEMA_PRODUCTS,
        "product_code": "P-100",
        "product_name": "Test",
        "category_code": "KURTI",
        "status": "in_stock",  # invalid status enum
    }
    with pytest.raises(v2_catalog.ValidationError, match="invalid product status"):
        v2_catalog.validate_product_row(row)


def test_validate_v2_sku_row_valid():
    row = {
        "schema_version": SCHEMA_SKUS,
        "sku_code": "DEMO-KUR-001-BLU-M",
        "product_code": "DEMO-KUR-001",
        "external_sku_id": "",
        "color_code": "BLUE",
        "color_name": "Indigo Blue",
        "size_code": "M",
        "size_system": "IN_ALPHA",
        "barcode": "8901234567890",
        "gtin": "",
        "mrp_incl_tax": "1575.00",
        "selling_price_incl_tax": "1575.00",
        "reference_cost_ex_tax": "600.0000",
        "currency": "INR",
        "price_valid_from": "2026-09-01T00:00:00+05:30",
        "status": "active",
        "attributes_json": "",
    }
    validated = v2_catalog.validate_sku_row(row)
    assert validated.sku_code == "DEMO-KUR-001-BLU-M"
    assert validated.product_code == "DEMO-KUR-001"
    assert validated.currency == "INR"
    assert validated.option_signature == "color:BLUE|size:M|sys:IN_ALPHA"
    assert validated.mrp_incl_tax == Decimal("1575.00")
    assert validated.reference_cost_ex_tax == Decimal("600.0000")


def test_validate_v2_sku_rejects_missing_parent():
    row = {
        "schema_version": SCHEMA_SKUS,
        "sku_code": "SKU-ORPHAN-001",
        "product_code": "",  # missing parent product code
        "currency": "INR",
        "status": "active",
    }
    with pytest.raises(v2_catalog.ValidationError, match="product_code is required"):
        v2_catalog.validate_sku_row(row)


def test_validate_v2_sku_rejects_missing_currency():
    row = {
        "schema_version": SCHEMA_SKUS,
        "sku_code": "SKU-001",
        "product_code": "P-001",
        "currency": "",  # currency cannot be empty or silently default to USD
        "status": "active",
    }
    with pytest.raises(v2_catalog.ValidationError, match="currency is required"):
        v2_catalog.validate_sku_row(row)


def test_validate_v2_sku_rejects_negative_price():
    row = {
        "schema_version": SCHEMA_SKUS,
        "sku_code": "SKU-001",
        "product_code": "P-001",
        "currency": "INR",
        "selling_price_incl_tax": "-100.00",
        "status": "active",
    }
    with pytest.raises(v2_catalog.ValidationError, match="cannot be negative"):
        v2_catalog.validate_sku_row(row)


def test_check_duplicate_variant_signatures():
    # Two SKUs under the same product with the same color/size option signature must be rejected
    sku1 = v2_catalog.validate_sku_row({
        "schema_version": SCHEMA_SKUS,
        "sku_code": "KUR-BLU-M-1",
        "product_code": "KUR-01",
        "color_code": "BLUE",
        "size_code": "M",
        "size_system": "IN_ALPHA",
        "currency": "INR",
        "status": "active",
    })
    sku2 = v2_catalog.validate_sku_row({
        "schema_version": SCHEMA_SKUS,
        "sku_code": "KUR-BLU-M-2",
        "product_code": "KUR-01",
        "color_code": "BLUE",
        "size_code": "M",
        "size_system": "IN_ALPHA",
        "currency": "INR",
        "status": "active",
    })
    with pytest.raises(v2_catalog.ValidationError, match="duplicate option signature"):
        v2_catalog.validate_sku_batch([sku1, sku2])
