"""V2 Catalog (Product & SKU) Validation.

Enforces:
- Product is style/group master: required product_code, product_name, category_code, valid status.
  No inventory or forecast scalars.
- SKU is sellable variant: required sku_code, product_code (parent required; no orphans), currency.
- Unique normalized option signatures (product_code, color_code, size_code, size_system).
- Decimal financial prices, non-negative.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from app.services.integrations.v2.contracts import SCHEMA_PRODUCTS, SCHEMA_SKUS

VALID_PRODUCT_STATUSES = {"active", "seasonal", "clearance", "pre_launch", "discontinued"}
VALID_SKU_STATUSES = {"active", "inactive", "discontinued"}


class ValidationError(ValueError):
    """V2 validation failure with machine-readable error code."""

    def __init__(self, message: str, code: str = "VALIDATION_ERROR", details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}


@dataclass
class ValidatedProduct:
    product_code: str
    product_name: str
    category_code: str
    brand_code: str | None = None
    style_number: str | None = None
    description: str | None = None
    collection_code: str | None = None
    season_code: str | None = None
    status: str = "active"
    hsn_code: str | None = None
    tax_class_code: str | None = None
    manufacturer_supplier_code: str | None = None
    image_urls: list[str] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidatedSku:
    sku_code: str
    product_code: str
    currency: str
    status: str = "active"
    external_sku_id: str | None = None
    color_code: str | None = None
    color_name: str | None = None
    size_code: str | None = None
    size_system: str | None = None
    barcode: str | None = None
    gtin: str | None = None
    mrp_incl_tax: Decimal | None = None
    selling_price_incl_tax: Decimal | None = None
    reference_cost_ex_tax: Decimal | None = None
    price_valid_from: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    @property
    def option_signature(self) -> str:
        parts = []
        if self.color_code:
            parts.append(f"color:{self.color_code.upper()}")
        if self.size_code:
            parts.append(f"size:{self.size_code.upper()}")
        if self.size_system:
            parts.append(f"sys:{self.size_system.upper()}")
        return "|".join(parts) or "default"


def _parse_decimal(value: Any, field_name: str) -> Decimal | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        dec = Decimal(str(value).strip())
    except InvalidOperation as exc:
        raise ValidationError(f"{field_name} must be a valid number", code="INVALID_TYPE") from exc
    if dec < Decimal("0"):
        raise ValidationError(f"{field_name} cannot be negative", code="INVALID_PRICE")
    return dec


def _parse_attributes(value: Any) -> dict[str, Any]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValidationError("attributes_json must be valid JSON", code="INVALID_JSON") from exc
        if isinstance(parsed, dict):
            return parsed
    raise ValidationError("attributes_json must be a JSON object", code="INVALID_JSON")


def validate_product_row(row: dict[str, Any]) -> ValidatedProduct:
    p_code = str(row.get("product_code") or "").strip()
    if not p_code:
        raise ValidationError("product_code is required", code="MISSING_REQUIRED_FIELD")

    p_name = str(row.get("product_name") or "").strip()
    if not p_name:
        raise ValidationError("product_name is required", code="MISSING_REQUIRED_FIELD")

    c_code = str(row.get("category_code") or "").strip()
    if not c_code:
        raise ValidationError("category_code is required", code="MISSING_REQUIRED_FIELD")

    status = str(row.get("status") or "active").strip().lower()
    if status not in VALID_PRODUCT_STATUSES:
        raise ValidationError(
            f"invalid product status '{status}'. Must be one of: {', '.join(sorted(VALID_PRODUCT_STATUSES))}",
            code="INVALID_STATUS",
        )

    attrs = _parse_attributes(row.get("attributes_json"))

    return ValidatedProduct(
        product_code=p_code,
        product_name=p_name,
        category_code=c_code,
        brand_code=str(row.get("brand_code") or "").strip() or None,
        style_number=str(row.get("style_number") or "").strip() or None,
        description=str(row.get("description") or "").strip() or None,
        collection_code=str(row.get("collection_code") or "").strip() or None,
        season_code=str(row.get("season_code") or "").strip() or None,
        status=status,
        hsn_code=str(row.get("hsn_code") or "").strip() or None,
        tax_class_code=str(row.get("tax_class_code") or "").strip() or None,
        manufacturer_supplier_code=str(row.get("manufacturer_supplier_code") or "").strip() or None,
        image_urls=[u.strip() for u in str(row.get("image_urls") or "").split(",") if u.strip()],
        attributes=attrs,
    )


def validate_sku_row(row: dict[str, Any]) -> ValidatedSku:
    sku_code = str(row.get("sku_code") or "").strip()
    if not sku_code:
        raise ValidationError("sku_code is required", code="MISSING_REQUIRED_FIELD")

    product_code = str(row.get("product_code") or "").strip()
    if not product_code:
        raise ValidationError("product_code is required for SKU", code="MISSING_PARENT_PRODUCT")

    currency = str(row.get("currency") or "").strip().upper()
    if currency not in {"INR", "USD", "EUR", "GBP", "AED", "SGD"}:
        raise ValidationError("currency is required (3-letter ISO code)", code="MISSING_CURRENCY")

    status = str(row.get("status") or "active").strip().lower()
    if status not in VALID_SKU_STATUSES:
        raise ValidationError(
            f"invalid sku status '{status}'. Must be one of: {', '.join(sorted(VALID_SKU_STATUSES))}",
            code="INVALID_STATUS",
        )

    mrp = _parse_decimal(row.get("mrp_incl_tax"), "mrp_incl_tax")
    selling_price = _parse_decimal(row.get("selling_price_incl_tax"), "selling_price_incl_tax")
    ref_cost = _parse_decimal(row.get("reference_cost_ex_tax"), "reference_cost_ex_tax")

    color_code = str(row.get("color_code") or "").strip() or None
    size_code = str(row.get("size_code") or "").strip() or None
    size_sys = str(row.get("size_system") or "").strip() or None

    return ValidatedSku(
        sku_code=sku_code,
        product_code=product_code,
        currency=currency,
        status=status,
        external_sku_id=str(row.get("external_sku_id") or "").strip() or None,
        color_code=color_code,
        color_name=str(row.get("color_name") or "").strip() or None,
        size_code=size_code,
        size_system=size_sys,
        barcode=str(row.get("barcode") or "").strip() or None,
        gtin=str(row.get("gtin") or "").strip() or None,
        mrp_incl_tax=mrp,
        selling_price_incl_tax=selling_price,
        reference_cost_ex_tax=ref_cost,
        price_valid_from=str(row.get("price_valid_from") or "").strip() or None,
        attributes=_parse_attributes(row.get("attributes_json")),
    )


def validate_sku_batch(skus: list[ValidatedSku]) -> None:
    """Validate cross-row constraints in a batch of SKUs, such as duplicate option signatures."""
    signatures_by_product: dict[str, set[str]] = {}
    for sku in skus:
        sigs = signatures_by_product.setdefault(sku.product_code, set())
        sig = sku.option_signature
        if sig in sigs:
            raise ValidationError(
                f"duplicate option signature '{sig}' for product '{sku.product_code}'",
                code="DUPLICATE_OPTION_SIGNATURE",
            )
        sigs.add(sig)
