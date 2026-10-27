"""Fixed, deterministic reshaping steps for smart import.

The AI planner may switch these on; it never supplies their logic. Each step is
a pure function over row dicts keyed by column id, so a preview and the
confirmed import run exactly the same code.
"""
from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from datetime import date
from decimal import Decimal, InvalidOperation

from app.services.fashion_sizes import normalize_size

_SUMMARY = {"total", "subtotal", "grandtotal"}
_RANGE = re.compile(r"date\s*range\s*:\s*(\d{2})-(\d{2})-(\d{4})\s*-\s*(\d{2})-(\d{2})-(\d{4})", re.IGNORECASE)


def _norm(value: object) -> str:
    return "".join(ch for ch in str(value or "").lower() if ch.isalnum())


def _blank(value: object) -> bool:
    return value is None or str(value).strip() == ""


def is_summary_row(record: dict, identity_ids: list[str]) -> bool:
    """A report total line: no item identity, and some cell reads Total/Sub Total/Grand Total."""
    if any(not _blank(record.get(cid)) for cid in identity_ids):
        return False
    return any(isinstance(v, str) and _norm(v) in _SUMMARY for v in record.values())


def parse_variant(description: str | None) -> tuple[str | None, str | None]:
    """(colour, size code) from a POS description's last two parts. ``NA`` means no colour."""
    text = str(description or "").strip()
    parts = [p.strip() for p in (text.split(" - ") if " - " in text else text.split("-"))]
    parts = [p for p in parts if p]
    if len(parts) < 2:
        return None, None
    size = parts[-1].upper()
    colour = parts[-2].upper()
    return (None if colour == "NA" else colour), size


def size_codes(codes: Iterable[str | None]) -> list[dict]:
    """Distinct size codes with counts, and the canonical size only when it is recognised."""
    counts = Counter(str(c).strip().upper() for c in codes if not _blank(c))
    return [{"code": code, "count": n, "suggestion": normalize_size(code)} for code, n in counts.most_common()]


def _part(value: object) -> str:
    return "-".join(re.findall(r"[A-Z0-9]+", str(value or "").upper()))


def variant_sku(*parts: object) -> str:
    return "-".join(p for p in (_part(v) for v in parts) if p and p != "NA")


def _number(value: object) -> Decimal:
    try:
        return Decimal(str(value).replace(",", "").strip()) if not _blank(value) else Decimal("0")
    except InvalidOperation:
        return Decimal("0")


def _plain(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral_value() else float(value)


def group_pieces(records: list[dict], *, brand: str | None, style: str, colour: str | None,
                 size: str | None, location: str | None, sums: list[str]) -> tuple[list[dict], int]:
    """Merge per-piece rows into one row per (brand-style-colour-size, location).

    ``sums`` columns are added; every other column takes its most common value.
    Returns the rows (with ``x_sku``) and how many groups had disagreeing values.
    """
    groups: dict[tuple[str, object], list[dict]] = {}
    for record in records:
        sku = variant_sku(record.get(brand) if brand else None, record.get(style),
                          record.get(colour) if colour else None, record.get(size) if size else None)
        key = (sku, record.get(location) if location else None)
        groups.setdefault(key, []).append(record)
    out, conflicts = [], 0
    for (sku, _), rows in groups.items():
        merged: dict = {}
        conflicted = False
        for column in dict.fromkeys(k for row in rows for k in row):
            if column in sums:
                merged[column] = _plain(sum((_number(r.get(column)) for r in rows), Decimal("0")))
                continue
            values = Counter(r.get(column) for r in rows if not _blank(r.get(column)))
            merged[column] = values.most_common(1)[0][0] if values else rows[0].get(column)
            conflicted |= len(values) > 1
        merged["x_sku"] = sku
        conflicts += conflicted
        out.append(merged)
    return out, conflicts


def parse_period(lines: list[str]) -> tuple[date, date] | None:
    """``Date Range : DD-MM-YYYY - DD-MM-YYYY`` from report letterhead text, if present and ordered."""
    for line in lines:
        match = _RANGE.search(str(line or ""))
        if not match:
            continue
        d1, m1, y1, d2, m2, y2 = (int(g) for g in match.groups())
        try:
            start, end = date(y1, m1, d1), date(y2, m2, d2)
        except ValueError:
            return None
        return (start, end) if start <= end else None
    return None
