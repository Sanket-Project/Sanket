"""V2 Inventory Semantics, Disjoint Buckets, and Snapshot Validation (P0-03).

Enforces:
- Explicit as_of timestamp (ISO 8601 with timezone offset).
- Disjoint inventory buckets: on_hand_qty >= reserved_qty + damaged_qty + quarantine_qty.
- Good unreserved stock = on_hand_qty - reserved_qty - damaged_qty - quarantine_qty.
- Available-to-sell = good_unreserved.
- Rejection of negative stock quantities (no silent clamping to 0!).
- Detection of stale snapshots (older snapshots cannot overwrite newer balances).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.services.integrations.v2.catalog import ValidationError


@dataclass
class ValidatedInventory:
    snapshot_id: str
    as_of: datetime
    sku_code: str
    location_code: str
    on_hand_qty: int
    reserved_qty: int = 0
    damaged_qty: int = 0
    quarantine_qty: int = 0
    in_transit_qty: int = 0
    open_po_qty: int = 0
    source_system: str = "upload"
    count_reference: str | None = None
    reported_stock_value_ex_tax: Decimal | None = None
    currency: str | None = None

    @property
    def good_unreserved(self) -> int:
        return self.on_hand_qty - self.reserved_qty - self.damaged_qty - self.quarantine_qty

    @property
    def available_to_sell(self) -> int:
        return self.good_unreserved


def _parse_int(value: Any, field_name: str, required: bool = False, default: int = 0) -> int:
    val_str = "" if value is None else str(value).strip()
    if not val_str:
        if required:
            raise ValidationError(f"{field_name} is required", code="MISSING_REQUIRED_FIELD")
        return default
    try:
        # Accept float string like "20.0" from excel export
        num = float(val_str)
        if not num.is_integer():
            raise ValidationError(f"{field_name} must be an integer piece quantity", code="INVALID_TYPE")
        return int(num)
    except (ValueError, OverflowError) as exc:
        raise ValidationError(f"{field_name} must be an integer", code="INVALID_TYPE") from exc


def validate_inventory_row(row: dict[str, Any]) -> ValidatedInventory:
    snap_id = str(row.get("snapshot_id") or "").strip()
    if not snap_id:
        raise ValidationError("snapshot_id is required", code="MISSING_REQUIRED_FIELD")

    as_of_str = "" if row.get("as_of") is None else str(row.get("as_of")).strip()
    if not as_of_str:
        raise ValidationError("as_of timestamp is required", code="MISSING_REQUIRED_FIELD")
    try:
        as_of = datetime.fromisoformat(as_of_str)
    except ValueError as exc:
        raise ValidationError(f"invalid as_of timestamp '{as_of_str}'", code="INVALID_TIMESTAMP") from exc
    if as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValidationError("as_of must include a timezone offset", code="NAIVE_TIMESTAMP")

    sku = str(row.get("sku_code") or "").strip()
    if not sku:
        raise ValidationError("sku_code is required", code="MISSING_REQUIRED_FIELD")

    location = str(row.get("location_code") or "").strip()
    if not location:
        raise ValidationError("location_code is required", code="MISSING_REQUIRED_FIELD")

    source_system = str(row.get("source_system") or "").strip() or "upload"

    on_hand = _parse_int(row.get("on_hand_qty"), "on_hand_qty", required=True)
    if on_hand < 0:
        raise ValidationError("on_hand_qty cannot be negative", code="NEGATIVE_STOCK")

    reserved = _parse_int(row.get("reserved_qty"), "reserved_qty")
    if reserved < 0:
        raise ValidationError("reserved_qty cannot be negative", code="NEGATIVE_STOCK")

    damaged = _parse_int(row.get("damaged_qty"), "damaged_qty")
    if damaged < 0:
        raise ValidationError("damaged_qty cannot be negative", code="NEGATIVE_STOCK")

    quarantine = _parse_int(row.get("quarantine_qty"), "quarantine_qty")
    if quarantine < 0:
        raise ValidationError("quarantine_qty cannot be negative", code="NEGATIVE_STOCK")

    in_transit = _parse_int(row.get("in_transit_qty"), "in_transit_qty")
    open_po = _parse_int(row.get("open_po_qty"), "open_po_qty")
    if in_transit < 0 or open_po < 0:
        raise ValidationError("in_transit_qty and open_po_qty cannot be negative", code="NEGATIVE_STOCK")

    if reserved + damaged + quarantine > on_hand:
        raise ValidationError(
            f"sum of reserved ({reserved}), damaged ({damaged}), and quarantine ({quarantine}) "
            f"exceeds on_hand_qty ({on_hand})",
            code="STOCK_SEMANTICS_REQUIRED",
        )

    val_str = str(row.get("reported_stock_value_ex_tax") or "").strip()
    reported_val = None
    if val_str:
        try:
            reported_val = Decimal(val_str)
        except InvalidOperation as exc:
            raise ValidationError("reported_stock_value_ex_tax must be decimal", code="INVALID_TYPE") from exc

    return ValidatedInventory(
        snapshot_id=snap_id,
        as_of=as_of,
        sku_code=sku,
        location_code=location,
        on_hand_qty=on_hand,
        reserved_qty=reserved,
        damaged_qty=damaged,
        quarantine_qty=quarantine,
        in_transit_qty=in_transit,
        open_po_qty=open_po,
        source_system=source_system,
        count_reference=str(row.get("count_reference") or "").strip() or None,
        reported_stock_value_ex_tax=reported_val,
        currency=str(row.get("currency") or "").strip() or None,
    )


def is_stale_snapshot(incoming_as_of: datetime, latest_as_of: datetime | None) -> bool:
    """Return True if the incoming snapshot is stale relative to existing recorded stock."""
    if latest_as_of is None:
        return False
    return incoming_as_of <= latest_as_of
