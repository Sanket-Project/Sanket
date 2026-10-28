"""V2 Canonical Sales and Returns Engine (P0-04, P0-05).

Enforces:
- Single return ownership: V2 sales rows require returns=0; returns must post via returns.csv.
- Non-negative sale quantities (quantity_sold >= 0; > 0 for completed, = 0 for cancelled).
- Cancelled rows must have zero financial values.
- Returns are strictly positive magnitudes (returns > 0).
- Returns require original transaction link (original_source_system, original_transaction_id, original_order_line_id).
- Decimal financial calculations with 2-decimal half-up rounding in paise.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from app.services.integrations.v2.catalog import ValidationError

_TWO_DP = Decimal("0.01")
_FOUR_DP = Decimal("0.0001")


def _round_paise(d: Decimal) -> Decimal:
    return d.quantize(_TWO_DP, rounding=ROUND_HALF_UP)


def _to_decimal(value: Any, field_name: str, required: bool = False, default: Decimal = Decimal("0.00")) -> Decimal:
    val_str = "" if value is None else str(value).strip()
    if not val_str:
        if required:
            raise ValidationError(f"{field_name} is required", code="MISSING_REQUIRED_FIELD")
        return default
    try:
        value = Decimal(val_str)
        if not value.is_finite():
            raise ValidationError(f"{field_name} must be finite", code="INVALID_TYPE")
        return value
    except InvalidOperation as exc:
        raise ValidationError(f"{field_name} must be a valid decimal number", code="INVALID_TYPE") from exc


def _to_int(value: Any, field_name: str, required: bool = False, default: int = 0) -> int:
    val_str = "" if value is None else str(value).strip()
    if not val_str:
        if required:
            raise ValidationError(f"{field_name} is required", code="MISSING_REQUIRED_FIELD")
        return default
    try:
        f = float(val_str)
        if not f.is_integer():
            raise ValidationError(f"{field_name} must be an integer piece quantity", code="INVALID_TYPE")
        return int(f)
    except (ValueError, OverflowError) as exc:
        raise ValidationError(f"{field_name} must be an integer", code="INVALID_TYPE") from exc


@dataclass
class ValidatedSale:
    source_system: str
    transaction_id: str
    order_id: str
    order_line_id: str
    transaction_at: datetime
    sku_code: str
    location_code: str
    fulfillment_location_code: str
    channel_code: str
    quantity_sold: int
    returns: int
    unit_price_ex_tax: Decimal
    mrp_incl_tax: Decimal | None
    discount_ex_tax: Decimal
    gross_sales_ex_tax: Decimal
    net_sale_ex_tax: Decimal
    tax_code: str
    tax_rate_pct: Decimal
    tax_amount: Decimal
    currency: str
    order_status: str
    invoice_number: str | None = None
    place_of_supply_state_code: str | None = None
    payment_method: str | None = None
    payment_reference: str | None = None
    payment_amount: Decimal | None = None

    @property
    def customer_charge(self) -> Decimal:
        return _round_paise(self.net_sale_ex_tax + self.tax_amount)


@dataclass
class ValidatedReturn:
    source_system: str
    return_id: str
    return_line_id: str
    return_at: datetime
    original_source_system: str
    original_transaction_id: str
    original_order_line_id: str
    sku_code: str
    location_code: str
    returns: int
    return_value_ex_tax: Decimal
    tax_code: str
    tax_amount: Decimal
    currency: str
    reason_code: str
    disposition: str
    status: str
    credit_note_number: str | None = None
    refund_reference: str | None = None
    refund_amount: Decimal | None = None
    refund_method: str | None = None
    refund_at: datetime | None = None
    exchange_order_id: str | None = None


def validate_sale_row(row: dict[str, Any]) -> ValidatedSale:
    txn_id = str(row.get("transaction_id") or "").strip()
    if not txn_id:
        raise ValidationError("transaction_id is required", code="MISSING_REQUIRED_FIELD")

    order_id = str(row.get("order_id") or "").strip()
    if not order_id:
        raise ValidationError("order_id is required", code="MISSING_REQUIRED_FIELD")

    line_id = str(row.get("order_line_id") or "").strip()
    if not line_id:
        raise ValidationError("order_line_id is required", code="MISSING_REQUIRED_FIELD")

    txn_at_str = str(row.get("transaction_at") or "").strip()
    if not txn_at_str:
        raise ValidationError("transaction_at is required", code="MISSING_REQUIRED_FIELD")
    try:
        txn_at = datetime.fromisoformat(txn_at_str)
    except ValueError as exc:
        raise ValidationError(f"invalid transaction_at '{txn_at_str}'", code="INVALID_TIMESTAMP") from exc
    if txn_at.tzinfo is None or txn_at.utcoffset() is None:
        raise ValidationError("transaction_at must include a timezone offset", code="NAIVE_TIMESTAMP")

    sku = str(row.get("sku_code") or "").strip()
    if not sku:
        raise ValidationError("sku_code is required", code="MISSING_REQUIRED_FIELD")

    location = str(row.get("location_code") or "").strip()
    if not location:
        raise ValidationError("location_code is required", code="MISSING_REQUIRED_FIELD")

    fulfill_loc = str(row.get("fulfillment_location_code") or "").strip() or location
    channel = str(row.get("channel_code") or "").strip()
    if not channel:
        raise ValidationError("channel_code is required", code="MISSING_REQUIRED_FIELD")

    # Quantities
    qty_sold = _to_int(row.get("quantity_sold"), "quantity_sold", required=True)
    if qty_sold < 0:
        raise ValidationError("quantity_sold cannot be negative", code="NEGATIVE_SALES_QTY")

    returns_val = _to_int(row.get("returns"), "returns", default=0)
    if returns_val != 0:
        raise ValidationError(
            "returns must be exactly 0 in V2 sales; returns post exclusively through returns.csv",
            code="RETURNS_NOT_ALLOWED_IN_SALES",
        )

    order_status = str(row.get("order_status") or "completed").strip().lower()
    if order_status not in ("completed", "cancelled"):
        raise ValidationError(f"invalid order_status '{order_status}'", code="INVALID_STATUS")

    if order_status == "completed" and qty_sold <= 0:
        raise ValidationError("completed sales must have quantity_sold > 0", code="INVALID_SALE_STATUS")

    unit_price = _to_decimal(row.get("unit_price_ex_tax"), "unit_price_ex_tax", required=True)
    if unit_price < Decimal("0"):
        raise ValidationError("unit_price_ex_tax cannot be negative", code="NEGATIVE_PRICE")

    mrp_raw = row.get("mrp_incl_tax")
    mrp = _to_decimal(mrp_raw, "mrp_incl_tax") if mrp_raw else None

    discount = _to_decimal(row.get("discount_ex_tax"), "discount_ex_tax", default=Decimal("0.00"))
    if discount < Decimal("0"):
        raise ValidationError("discount_ex_tax cannot be negative", code="NEGATIVE_DISCOUNT")

    gross = _round_paise(Decimal(qty_sold) * unit_price)
    if discount > gross:
        raise ValidationError("discount_ex_tax cannot exceed gross_sales_ex_tax", code="FINANCIAL_MISMATCH")

    net_sale = _round_paise(gross - discount)

    tax_code = str(row.get("tax_code") or "").strip()
    if not tax_code:
        raise ValidationError("tax_code is required", code="MISSING_REQUIRED_FIELD")

    tax_rate = _to_decimal(row.get("tax_rate_pct"), "tax_rate_pct", required=True)
    if tax_rate < Decimal("0"):
        raise ValidationError("tax_rate_pct cannot be negative", code="INVALID_TAX_RATE")

    tax_amount = _to_decimal(row.get("tax_amount"), "tax_amount", default=Decimal("0.00"))
    if tax_amount < Decimal("0"):
        raise ValidationError("tax_amount cannot be negative", code="INVALID_TAX_AMOUNT")
    expected_tax = _round_paise(net_sale * tax_rate / Decimal("100"))
    if tax_amount != expected_tax:
        raise ValidationError(
            f"tax_amount {tax_amount} does not match taxable value {net_sale} at {tax_rate}%",
            code="TAX_MISMATCH",
        )

    currency = str(row.get("currency") or "").strip().upper()
    if not currency or len(currency) != 3:
        raise ValidationError("currency is required (3-letter ISO code)", code="MISSING_CURRENCY")

    pay_amount_raw = row.get("payment_amount")
    pay_amount = _to_decimal(pay_amount_raw, "payment_amount") if pay_amount_raw else None

    if order_status == "cancelled":
        if (
            qty_sold != 0
            or gross != Decimal("0")
            or discount != Decimal("0")
            or tax_amount != Decimal("0")
            or pay_amount not in (None, Decimal("0"))
        ):
            raise ValidationError(
                "cancelled sales rows must have zero payment_amount, zero quantity and zero revenue",
                code="CANCELLED_SALE_NOT_ZERO",
            )

    return ValidatedSale(
        source_system=str(row.get("source_system") or "upload").strip(),
        transaction_id=txn_id,
        order_id=order_id,
        order_line_id=line_id,
        transaction_at=txn_at,
        sku_code=sku,
        location_code=location,
        fulfillment_location_code=fulfill_loc,
        channel_code=channel,
        quantity_sold=qty_sold,
        returns=0,
        unit_price_ex_tax=unit_price,
        mrp_incl_tax=mrp,
        discount_ex_tax=discount,
        gross_sales_ex_tax=gross,
        net_sale_ex_tax=net_sale,
        tax_code=tax_code,
        tax_rate_pct=tax_rate,
        tax_amount=tax_amount,
        currency=currency,
        order_status=order_status,
        invoice_number=str(row.get("invoice_number") or "").strip() or None,
        place_of_supply_state_code=str(row.get("place_of_supply_state_code") or "").strip() or None,
        payment_method=str(row.get("payment_method") or "").strip() or None,
        payment_reference=str(row.get("payment_reference") or "").strip() or None,
        payment_amount=pay_amount,
    )


def validate_return_row(row: dict[str, Any]) -> ValidatedReturn:
    ret_id = str(row.get("return_id") or "").strip()
    if not ret_id:
        raise ValidationError("return_id is required", code="MISSING_REQUIRED_FIELD")

    ret_line_id = str(row.get("return_line_id") or "").strip()
    if not ret_line_id:
        raise ValidationError("return_line_id is required", code="MISSING_REQUIRED_FIELD")

    ret_at_str = str(row.get("return_at") or "").strip()
    if not ret_at_str:
        raise ValidationError("return_at is required", code="MISSING_REQUIRED_FIELD")
    try:
        ret_at = datetime.fromisoformat(ret_at_str)
    except ValueError as exc:
        raise ValidationError(f"invalid return_at '{ret_at_str}'", code="INVALID_TIMESTAMP") from exc
    if ret_at.tzinfo is None or ret_at.utcoffset() is None:
        raise ValidationError("return_at must include a timezone offset", code="NAIVE_TIMESTAMP")

    orig_src = str(row.get("original_source_system") or "").strip()
    orig_txn = str(row.get("original_transaction_id") or "").strip()
    orig_line = str(row.get("original_order_line_id") or "").strip()
    if not orig_src or not orig_txn or not orig_line:
        raise ValidationError("original_transaction_id is required for linked returns", code="MISSING_ORIGINAL_LINK")

    sku = str(row.get("sku_code") or "").strip()
    if not sku:
        raise ValidationError("sku_code is required", code="MISSING_REQUIRED_FIELD")

    location = str(row.get("location_code") or "").strip()
    if not location:
        raise ValidationError("location_code is required", code="MISSING_REQUIRED_FIELD")

    returned_units = _to_int(row.get("returns"), "returns", required=True)
    if returned_units <= 0:
        raise ValidationError("returns quantity must be strictly positive", code="INVALID_RETURN_QTY")

    val_ex_tax = _to_decimal(row.get("return_value_ex_tax"), "return_value_ex_tax", required=True)
    if val_ex_tax < Decimal("0"):
        raise ValidationError("return_value_ex_tax cannot be negative", code="NEGATIVE_VALUE")

    tax_amount = _to_decimal(row.get("tax_amount"), "tax_amount", default=Decimal("0.00"))
    if tax_amount < Decimal("0"):
        raise ValidationError("tax_amount cannot be negative", code="NEGATIVE_TAX")

    tax_code = str(row.get("tax_code") or "").strip()
    if not tax_code:
        raise ValidationError("tax_code is required", code="MISSING_REQUIRED_FIELD")

    currency = str(row.get("currency") or "").strip().upper()
    if not currency or len(currency) != 3:
        raise ValidationError("currency is required (3-letter ISO code)", code="MISSING_CURRENCY")

    reason_code = str(row.get("reason_code") or "").strip()
    if not reason_code:
        raise ValidationError("reason_code is required", code="MISSING_REQUIRED_FIELD")

    disposition = str(row.get("disposition") or "").strip().lower()
    if disposition not in ("restock", "quarantine", "damaged", "no_receipt"):
        raise ValidationError(f"invalid disposition '{disposition}'", code="INVALID_DISPOSITION")

    status = str(row.get("status") or "approved").strip().lower()
    if status not in ("approved", "draft", "rejected"):
        raise ValidationError(f"invalid return status '{status}'", code="INVALID_STATUS")

    refund_ref = str(row.get("refund_reference") or "").strip() or None
    refund_amt_raw = row.get("refund_amount")
    refund_amt = _to_decimal(refund_amt_raw, "refund_amount") if refund_amt_raw is not None and str(refund_amt_raw).strip() else None
    if refund_amt is not None and refund_amt < 0:
        raise ValidationError("refund_amount cannot be negative", code="NEGATIVE_REFUND")

    refund_method = str(row.get("refund_method") or "").strip() or None
    refund_at_str = str(row.get("refund_at") or "").strip()
    try:
        refund_at = datetime.fromisoformat(refund_at_str) if refund_at_str else None
    except ValueError as exc:
        raise ValidationError("refund_at must be a valid timestamp", code="INVALID_TIMESTAMP") from exc
    if refund_at is not None and (refund_at.tzinfo is None or refund_at.utcoffset() is None):
        raise ValidationError("refund_at must include a timezone offset", code="NAIVE_TIMESTAMP")
    if refund_amt is not None and refund_amt != _round_paise(val_ex_tax + tax_amount):
        raise ValidationError("refund_amount must equal the credited value including tax", code="REFUND_MISMATCH")

    return ValidatedReturn(
        source_system=str(row.get("source_system") or "upload").strip(),
        return_id=ret_id,
        return_line_id=ret_line_id,
        return_at=ret_at,
        original_source_system=orig_src,
        original_transaction_id=orig_txn,
        original_order_line_id=orig_line,
        sku_code=sku,
        location_code=location,
        returns=returned_units,
        return_value_ex_tax=val_ex_tax,
        tax_code=tax_code,
        tax_amount=tax_amount,
        currency=currency,
        reason_code=reason_code,
        disposition=disposition,
        status=status,
        credit_note_number=str(row.get("credit_note_number") or "").strip() or None,
        refund_reference=refund_ref,
        refund_amount=refund_amt,
        refund_method=refund_method,
        refund_at=refund_at,
        exchange_order_id=str(row.get("exchange_order_id") or "").strip() or None,
    )
