"""Stable, tenant-scoped identity for sales rows — what makes re-imports idempotent.

A sales row's ``record_key`` answers "have we stored this exact sale before?"
so a replayed upload, an overlapping export or a redelivered push event lands
once. Keys are namespaced by ``source`` and are only ever compared within one
tenant (the column is read under the tenant's RLS scope).

Three identities, from most to least specific:

* **Order line** (transaction mode, order id present):
  ``{source}|o|{order_id}|{line_id or sku_id}``. Quantity and price are not part
  of the key, so a corrected export of the same line updates it in place.
* **Row fingerprint** (transaction mode, no order id): ``{source}|f|{md5}`` over
  the canonical sale fields. Without a source identity a correction cannot be
  told apart from a new sale, so it is imported as new — the conservative
  choice, since merging two genuinely different sales would lose demand.
* **Period total** (period mode, opted into per upload):
  ``{source}|p|{sku_id}|{location}|{channel}|{date}``. One row per SKU, place
  and day, so a corrected aggregate export replaces the value.

In transaction mode the caller appends the occurrence of each base key within
the uploaded file (``#1``, ``#2``…), so two identical lines in one file stay
two sales while uploading that same file again matches both.

The canonical text forms are mirrored by the SQL backfill in migration 0022;
change them only together.
"""

from __future__ import annotations

import hashlib
import uuid
from collections import Counter
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

IdentityMode = Literal["transaction", "period"]

_FOUR_DP = Decimal("0.0001")


def canonical_money(value: Decimal | None) -> str:
    """Match PostgreSQL's ``numeric(18,4)::text`` (rounds half away from zero)."""
    if value is None:
        return ""
    return str(Decimal(value).quantize(_FOUR_DP, rounding=ROUND_HALF_UP))


def canonical_time(value: datetime) -> str:
    """UTC with microseconds, matching ``to_char(... AT TIME ZONE 'UTC', '...US')``."""
    utc = value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    return utc.strftime("%Y-%m-%dT%H:%M:%S.%f")


def base_key(
    *,
    source: str,
    mode: IdentityMode,
    sku_id: uuid.UUID,
    sale_time: datetime,
    channel: str,
    region: str | None,
    location: str | None,
    units: int,
    gross: Decimal | None,
    net: Decimal | None,
    order_id: str | None,
    line_id: str | None,
) -> str:
    """The identity of one sale before its in-file occurrence is appended."""
    if mode == "period":
        day = (sale_time.astimezone(UTC) if sale_time.tzinfo else sale_time).date()
        return f"{source}|p|{sku_id}|{location or ''}|{channel}|{day.isoformat()}"

    if order_id:
        return f"{source}|o|{order_id}|{line_id or sku_id}"

    canonical = "|".join(
        (
            str(sku_id),
            canonical_time(sale_time),
            channel,
            region or "",
            location or "",
            str(units),
            canonical_money(gross),
            canonical_money(net),
        )
    )
    return f"{source}|f|{hashlib.md5(canonical.encode('utf-8')).hexdigest()}"  # noqa: S324 - identity, not security


def assign_record_keys(bases: list[str], mode: IdentityMode) -> list[str]:
    """Append each base key's occurrence within the file (transaction mode only).

    Period keys carry no ordinal: two rows for the same SKU, place and day in
    one file are a conflict for the caller to reject, not two sales.
    """
    if mode == "period":
        return list(bases)
    seen: Counter[str] = Counter()
    keys: list[str] = []
    for base in bases:
        seen[base] += 1
        keys.append(f"{base}#{seen[base]}")
    return keys
