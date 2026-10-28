"""Tests for V2 Sales & Returns Canonical Engine (P0-04, P0-05)."""

from __future__ import annotations

from decimal import Decimal
import pytest

from app.services.integrations.v2 import sales_returns as v2_sr
from app.services.integrations.v2.catalog import ValidationError
from app.services.integrations.v2.contracts import SCHEMA_RETURNS, SCHEMA_SALES


def test_validate_v2_sales_row_valid():
    row = {
        "schema_version": SCHEMA_SALES,
        "source_system": "DEMO-POS",
        "transaction_id": "DEMO-TXN-001",
        "order_id": "DEMO-ORDER-001",
        "order_line_id": "DEMO-LINE-001",
        "transaction_at": "2026-10-02T12:00:00+05:30",
        "sku_code": "DEMO-KUR-001-BLU-M",
        "location_code": "demo-hyd-store",
        "fulfillment_location_code": "demo-hyd-store",
        "channel_code": "pos",
        "quantity_sold": "2",
        "returns": "0",
        "unit_price_ex_tax": "1000.0000",
        "mrp_incl_tax": "1575.00",
        "discount_ex_tax": "200.00",
        "tax_code": "DEMO-TAX-5",
        "tax_rate_pct": "5.0000",
        "tax_amount": "90.00",
        "currency": "INR",
        "order_status": "completed",
        "invoice_number": "DEMO-INV-001",
        "place_of_supply_state_code": "36",
        "payment_method": "upi",
        "payment_reference": "DEMO-PAY-001",
        "payment_amount": "1890.00",
    }
    sale = v2_sr.validate_sale_row(row)
    assert sale.transaction_id == "DEMO-TXN-001"
    assert sale.quantity_sold == 2
    assert sale.returns == 0
    assert sale.unit_price_ex_tax == Decimal("1000.0000")
    assert sale.gross_sales_ex_tax == Decimal("2000.00")
    assert sale.discount_ex_tax == Decimal("200.00")
    assert sale.net_sale_ex_tax == Decimal("1800.00")
    assert sale.tax_amount == Decimal("90.00")
    assert sale.customer_charge == Decimal("1890.00")


def test_validate_v2_sales_rejects_returns_greater_than_zero():
    # V2 non-negotiable rule: V2 sales rows have returns=0; returns.csv is the single return owner!
    row = {
        "schema_version": SCHEMA_SALES,
        "source_system": "DEMO-POS",
        "transaction_id": "DEMO-TXN-001",
        "order_id": "DEMO-ORDER-001",
        "order_line_id": "DEMO-LINE-001",
        "transaction_at": "2026-10-02T12:00:00+05:30",
        "sku_code": "DEMO-KUR-001-BLU-M",
        "location_code": "demo-hyd-store",
        "channel_code": "pos",
        "quantity_sold": "2",
        "returns": "1",  # Invalid in V2 sales
        "unit_price_ex_tax": "1000.0000",
        "discount_ex_tax": "0.00",
        "tax_code": "DEMO-TAX-5",
        "tax_rate_pct": "5.0000",
        "tax_amount": "100.00",
        "currency": "INR",
        "order_status": "completed",
    }
    with pytest.raises(ValidationError, match="returns must be exactly 0 in V2 sales"):
        v2_sr.validate_sale_row(row)


def test_validate_v2_sales_rejects_negative_quantity_sold():
    row = {
        "schema_version": SCHEMA_SALES,
        "source_system": "DEMO-POS",
        "transaction_id": "DEMO-TXN-001",
        "order_id": "DEMO-ORDER-001",
        "order_line_id": "DEMO-LINE-001",
        "transaction_at": "2026-10-02T12:00:00+05:30",
        "sku_code": "DEMO-KUR-001-BLU-M",
        "location_code": "demo-hyd-store",
        "channel_code": "pos",
        "quantity_sold": "-1",
        "returns": "0",
        "unit_price_ex_tax": "1000.0000",
        "discount_ex_tax": "0.00",
        "tax_code": "DEMO-TAX-5",
        "tax_rate_pct": "5.0000",
        "tax_amount": "0.00",
        "currency": "INR",
        "order_status": "completed",
    }
    with pytest.raises(ValidationError, match="quantity_sold cannot be negative"):
        v2_sr.validate_sale_row(row)


def test_validate_v2_sales_cancelled_requires_zero_financials():
    # Cancelled row has quantity_sold = 0 and zero financial values
    row = {
        "schema_version": SCHEMA_SALES,
        "source_system": "DEMO-POS",
        "transaction_id": "DEMO-TXN-002",
        "order_id": "DEMO-ORDER-002",
        "order_line_id": "DEMO-LINE-002",
        "transaction_at": "2026-10-02T12:00:00+05:30",
        "sku_code": "DEMO-KUR-001-BLU-M",
        "location_code": "demo-hyd-store",
        "channel_code": "pos",
        "quantity_sold": "0",
        "returns": "0",
        "unit_price_ex_tax": "1000.0000",
        "discount_ex_tax": "0.00",
        "tax_code": "DEMO-TAX-5",
        "tax_rate_pct": "5.0000",
        "tax_amount": "0.00",
        "currency": "INR",
        "order_status": "cancelled",
        "payment_amount": "500.00",  # Invalid! Cancelled rows cannot have non-zero payment
    }
    with pytest.raises(ValidationError, match="cancelled sales rows must have zero payment_amount"):
        v2_sr.validate_sale_row(row)


def test_validate_v2_return_row_valid():
    row = {
        "schema_version": SCHEMA_RETURNS,
        "source_system": "DEMO-POS",
        "return_id": "DEMO-RET-001",
        "return_line_id": "DEMO-RLINE-001",
        "return_at": "2026-10-03T13:00:00+05:30",
        "original_source_system": "DEMO-POS",
        "original_transaction_id": "DEMO-TXN-001",
        "original_order_line_id": "DEMO-LINE-001",
        "sku_code": "DEMO-KUR-001-BLU-M",
        "location_code": "demo-hyd-store",
        "returns": "1",
        "return_value_ex_tax": "900.00",
        "tax_code": "DEMO-TAX-5",
        "tax_amount": "45.00",
        "currency": "INR",
        "reason_code": "size_issue",
        "disposition": "restock",
        "credit_note_number": "DEMO-CN-001",
        "refund_reference": "DEMO-REF-001",
        "refund_amount": "945.00",
        "refund_method": "upi",
        "refund_at": "2026-10-03T14:00:00+05:30",
        "exchange_order_id": "",
        "status": "approved",
    }
    ret = v2_sr.validate_return_row(row)
    assert ret.return_id == "DEMO-RET-001"
    assert ret.returns == 1
    assert ret.original_transaction_id == "DEMO-TXN-001"
    assert ret.original_order_line_id == "DEMO-LINE-001"
    assert ret.return_value_ex_tax == Decimal("900.00")
    assert ret.tax_amount == Decimal("45.00")
    assert ret.refund_amount == Decimal("945.00")
    assert ret.disposition == "restock"
    assert ret.status == "approved"


def test_validate_v2_return_rejects_non_positive_returns():
    row = {
        "schema_version": SCHEMA_RETURNS,
        "source_system": "DEMO-POS",
        "return_id": "DEMO-RET-001",
        "return_line_id": "DEMO-RLINE-001",
        "return_at": "2026-10-03T13:00:00+05:30",
        "original_source_system": "DEMO-POS",
        "original_transaction_id": "DEMO-TXN-001",
        "original_order_line_id": "DEMO-LINE-001",
        "sku_code": "DEMO-KUR-001-BLU-M",
        "location_code": "demo-hyd-store",
        "returns": "0",  # Returns must be strictly positive
        "return_value_ex_tax": "900.00",
        "tax_code": "DEMO-TAX-5",
        "tax_amount": "45.00",
        "currency": "INR",
        "reason_code": "size_issue",
        "disposition": "restock",
        "status": "approved",
    }
    with pytest.raises(ValidationError, match="returns quantity must be strictly positive"):
        v2_sr.validate_return_row(row)


def test_validate_v2_return_rejects_missing_original_transaction():
    row = {
        "schema_version": SCHEMA_RETURNS,
        "source_system": "DEMO-POS",
        "return_id": "DEMO-RET-001",
        "return_line_id": "DEMO-RLINE-001",
        "return_at": "2026-10-03T13:00:00+05:30",
        "original_source_system": "",
        "original_transaction_id": "",  # Missing original link
        "original_order_line_id": "",
        "sku_code": "DEMO-KUR-001-BLU-M",
        "location_code": "demo-hyd-store",
        "returns": "1",
        "return_value_ex_tax": "900.00",
        "tax_code": "DEMO-TAX-5",
        "tax_amount": "45.00",
        "currency": "INR",
        "reason_code": "size_issue",
        "disposition": "restock",
        "status": "approved",
    }
    with pytest.raises(ValidationError, match="original_transaction_id is required"):
        v2_sr.validate_return_row(row)
