"""Sales record identity — the key that makes re-imports idempotent (F01).

Expected keys are hand-written literals, not recomputed with the module under
test, so a change to the canonical form is caught here rather than silently
re-keying every stored row.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

from app.services import sales_identity as si

SKU = uuid.UUID("00000000-0000-0000-0000-000000000001")
T = datetime(2026, 8, 24, tzinfo=UTC)


def _base(**overrides):
    args = {
        "source": "upload",
        "mode": "transaction",
        "sku_id": SKU,
        "sale_time": T,
        "channel": "Boduppal",
        "region": None,
        "location": None,
        "units": 5,
        "gross": Decimal("6000"),
        "net": Decimal("5900"),
        "order_id": None,
        "line_id": None,
    }
    args.update(overrides)
    return si.base_key(**args)


def test_order_key_prefers_explicit_line_and_falls_back_to_sku():
    assert _base(order_id="A-1") == "upload|o|A-1|00000000-0000-0000-0000-000000000001"
    assert _base(order_id="A-1", line_id="2") == "upload|o|A-1|2"


def test_order_key_ignores_quantity_so_corrections_match():
    assert _base(order_id="A-1", units=5) == _base(order_id="A-1", units=7)


def test_fingerprint_is_the_md5_of_the_canonical_row():
    # Hand-written canonical row; must stay byte-identical to the SQL backfill
    # in migration 0022 or replays of pre-fix uploads would duplicate again.
    canonical = (
        "00000000-0000-0000-0000-000000000001|2026-08-24T00:00:00.000000"
        "|Boduppal|||5|6000.0000|5900.0000"
    )
    assert _base() == "upload|f|" + hashlib.md5(canonical.encode()).hexdigest()


def test_fingerprint_changes_with_any_sale_field():
    base = _base()
    assert base == _base()
    for change in (
        {"units": 6},
        {"gross": Decimal("6001")},
        {"net": None},
        {"channel": "Alwal"},
        {"region": "TS"},
        {"location": "Alwal"},
        {"sale_time": T + timedelta(microseconds=1)},
        {"sku_id": uuid.UUID(int=2)},
    ):
        assert _base(**change) != base, change


def test_fingerprint_is_independent_of_input_timezone():
    ist = timezone(timedelta(hours=5, minutes=30))
    assert _base(sale_time=T.astimezone(ist)) == _base(sale_time=T)


def test_money_canonical_form_matches_postgres_numeric_18_4_text():
    assert si.canonical_money(Decimal("6000")) == "6000.0000"
    assert si.canonical_money(Decimal("1.23455")) == "1.2346"  # half away from zero
    assert si.canonical_money(Decimal("-1.23455")) == "-1.2346"
    assert si.canonical_money(None) == ""


def test_time_canonical_form_is_utc_microseconds():
    ist = timezone(timedelta(hours=5, minutes=30))
    assert si.canonical_time(datetime(2026, 8, 31, 1, 30, tzinfo=ist)) == "2026-08-30T20:00:00.000000"


def test_occurrence_ordinals_keep_identical_rows_in_one_file_distinct():
    assert si.assign_record_keys(["b", "b", "c", "b"], "transaction") == ["b#1", "b#2", "c#1", "b#3"]


def test_period_key_is_sku_location_channel_date_without_ordinal():
    k = _base(mode="period", order_id="IGNORED", units=99)
    assert k == "upload|p|00000000-0000-0000-0000-000000000001||Boduppal|2026-08-24"
    assert si.assign_record_keys([k, k], "period") == [k, k]


def test_source_namespaces_keys():
    assert _base(source="rest_api", order_id="A-1").startswith("rest_api|o|A-1|")
