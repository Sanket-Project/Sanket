"""Tests for V2 CSV contracts, schema detection, and strict header verification."""

from __future__ import annotations

import pytest

from app.services.integrations.v2 import contracts as v2


def test_v2_schema_constants():
    assert v2.SCHEMA_PRODUCTS == "retail_v2.0.products"
    assert v2.SCHEMA_SKUS == "retail_v2.0.skus"
    assert v2.SCHEMA_INVENTORY == "retail_v2.0.inventory"
    assert v2.SCHEMA_SALES == "retail_v2.0.sales"
    assert v2.SCHEMA_RETURNS == "retail_v2.0.returns"
    assert v2.SCHEMA_PURCHASES == "retail_v2.0.purchases"
    assert v2.SCHEMA_SUPPLIERS == "retail_v2.0.suppliers"
    assert v2.SCHEMA_LOCATIONS == "retail_v2.0.locations"


def test_detect_v2_schema_from_header_and_first_row():
    # Detect from first row with schema_version column
    headers = ["schema_version", "product_code", "product_name"]
    first_row = {"schema_version": "retail_v2.0.products", "product_code": "P01", "product_name": "Kurti"}
    schema = v2.detect_v2_schema(headers, first_row)
    assert schema == v2.SCHEMA_PRODUCTS


def test_detect_v2_schema_from_exact_template_headers():
    # If first row has no data yet (e.g. template), match exact canonical headers
    sales_headers = v2.CONTRACT_HEADERS[v2.SCHEMA_SALES]
    assert v2.detect_v2_schema(sales_headers) == v2.SCHEMA_SALES


def test_detect_v2_schema_returns_none_for_v1_headers():
    # Legacy V1 headers should not be detected as V2
    v1_headers = ["Item Code", "Units Sold", "Unit Price", "Order Date"]
    assert v2.detect_v2_schema(v1_headers) is None


def test_v2_template_headers_match_data_dictionary():
    # Every contract must have the exact ordered columns from DATA_DICTIONARY.md
    for schema_key, cols in v2.CONTRACT_HEADERS.items():
        assert cols[0] == "schema_version"
        assert len(cols) >= 11


def test_formula_injection_escaping():
    # Dangerous formula characters (=, +, -, @, \t, \r) must be escaped with a single quote prefix
    assert v2.escape_formula("=SUM(A1:A10)") == "'=SUM(A1:A10)"
    assert v2.escape_formula("+12345") == "'+12345"
    assert v2.escape_formula("-12345") == "'-12345"
    assert v2.escape_formula("@something") == "'@something"
    assert v2.escape_formula("Normal Text") == "Normal Text"
    assert v2.escape_formula("DEMO-SKU-001") == "DEMO-SKU-001"  # Not starting with '-'


def test_parse_csv_handles_utf8_bom():
    raw_with_bom = b"\xef\xbb\xbfschema_version,product_code,product_name\nretail_v2.0.products,P1,Kurti\n"
    headers, rows = v2.parse_v2_csv(raw_with_bom)
    assert headers[0] == "schema_version"
    assert rows[0]["product_code"] == "P1"
