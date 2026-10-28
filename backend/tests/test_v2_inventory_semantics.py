"""Tests for V2 Inventory Quantity Semantics & Snapshot Validation (P0-03)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import pytest

from app.services.integrations.v2 import inventory as v2_inventory
from app.services.integrations.v2.catalog import ValidationError
from app.services.integrations.v2.contracts import SCHEMA_INVENTORY


def test_validate_v2_inventory_row_valid():
    row = {
        "schema_version": SCHEMA_INVENTORY,
        "snapshot_id": "DEMO-SNAP-001",
        "as_of": "2026-10-01T00:00:00+05:30",
        "sku_code": "DEMO-KUR-001-BLU-M",
        "location_code": "demo-hyd-store",
        "on_hand_qty": "20",
        "reserved_qty": "2",
        "damaged_qty": "1",
        "quarantine_qty": "0",
        "in_transit_qty": "0",
        "open_po_qty": "0",
        "source_system": "DEMO-ERP",
        "count_reference": "COUNT-2026-10",
        "reported_stock_value_ex_tax": "12000.0000",
        "currency": "INR",
    }
    validated = v2_inventory.validate_inventory_row(row)
    assert validated.snapshot_id == "DEMO-SNAP-001"
    assert validated.sku_code == "DEMO-KUR-001-BLU-M"
    assert validated.on_hand_qty == 20
    assert validated.reserved_qty == 2
    assert validated.damaged_qty == 1
    assert validated.quarantine_qty == 0
    assert validated.available_to_sell == 17  # 20 - 2 - 1 - 0


def test_validate_v2_inventory_rejects_negative_stock():
    # V2 non-negotiable rule: never silently clamp invalid stock quantities to zero!
    row = {
        "schema_version": SCHEMA_INVENTORY,
        "snapshot_id": "DEMO-SNAP-001",
        "as_of": "2026-10-01T00:00:00+05:30",
        "sku_code": "DEMO-KUR-001-BLU-M",
        "location_code": "demo-hyd-store",
        "on_hand_qty": "-5",
        "source_system": "DEMO-ERP",
    }
    with pytest.raises(ValidationError, match="on_hand_qty cannot be negative"):
        v2_inventory.validate_inventory_row(row)


def test_validate_v2_inventory_rejects_missing_as_of():
    # as_of is mandatory; cannot default to upload time
    row = {
        "schema_version": SCHEMA_INVENTORY,
        "snapshot_id": "DEMO-SNAP-001",
        "as_of": "",
        "sku_code": "DEMO-KUR-001-BLU-M",
        "location_code": "demo-hyd-store",
        "on_hand_qty": "10",
        "source_system": "DEMO-ERP",
    }
    with pytest.raises(ValidationError, match="as_of timestamp is required"):
        v2_inventory.validate_inventory_row(row)


def test_validate_v2_inventory_rejects_oversubscribed_buckets():
    # on_hand_qty (10) < reserved (8) + damaged (3) + quarantine (0) = 11
    # Must reject, not silently clamp to healthy zero available!
    row = {
        "schema_version": SCHEMA_INVENTORY,
        "snapshot_id": "DEMO-SNAP-001",
        "as_of": "2026-10-01T00:00:00+05:30",
        "sku_code": "DEMO-KUR-001-BLU-M",
        "location_code": "demo-hyd-store",
        "on_hand_qty": "10",
        "reserved_qty": "8",
        "damaged_qty": "3",
        "quarantine_qty": "0",
        "source_system": "DEMO-ERP",
    }
    with pytest.raises(ValidationError, match="exceeds on_hand_qty"):
        v2_inventory.validate_inventory_row(row)


def test_stale_snapshot_detection():
    # If existing balance is as of 2026-10-02, an incoming snapshot from 2026-10-01 is stale
    existing_as_of = datetime.fromisoformat("2026-10-02T12:00:00+05:30")
    incoming_as_of = datetime.fromisoformat("2026-10-01T12:00:00+05:30")
    assert v2_inventory.is_stale_snapshot(incoming_as_of, existing_as_of) is True

    newer_as_of = datetime.fromisoformat("2026-10-03T12:00:00+05:30")
    assert v2_inventory.is_stale_snapshot(newer_as_of, existing_as_of) is False
