"""Bounded local workbook discovery. Suggestions never determine which rows are written."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import unicodedata
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime
from xml.etree.ElementTree import ParseError, iterparse

from app.services.integrations.file_import import _build_header_map, _to_datetime, _to_decimal

PARSER_VERSION = "1"
_FIELDS = {
    "sales": ("sku", "name", "quantity", "timestamp", "price", "revenue", "discount", "channel", "region",
              "order_id", "line_id", "in_stock", "stockout", "returns", "warehouse", "currency"),
    "inventory": ("sku", "available", "reserved", "inbound", "warehouse"),
    "products": ("sku", "name", "brand", "category", "description", "gtin", "price", "size", "color", "currency"),
}
_REQUIRED = {"sales": ({"sku", "name"}, {"quantity"}, {"timestamp"}),
             "inventory": ({"sku"}, {"available"}), "products": ({"sku", "name"},)}


def fields_for(kind: str) -> tuple[str, ...]:
    if kind not in _FIELDS:
        raise ValueError("Unknown import kind")
    return _FIELDS[kind]


def validate_mapping(kind: str, mapping: dict[str, str], columns: list[str]) -> dict[str, str]:
    active = {key: value for key, value in mapping.items() if value}
    if not set(active) <= set(fields_for(kind)) or not set(active.values()) <= set(columns):
        raise ValueError("Mapping refers to unsupported fields or unknown columns")
    if len(set(active.values())) != len(active):
        raise ValueError("A column cannot map to multiple fields")
    if any(not set(active).intersection(group) for group in _REQUIRED[kind]):
        raise ValueError("Map all required fields before importing")
    return active


def _norm(value) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip().casefold()


def _type(value) -> str:
    if value is None or value == "":
        return "unknown"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (date, datetime)):
        return "date"
    numeric = isinstance(value, (int, float)) or bool(re.fullmatch(r"[₹$€£¥+\-\s]*\d[\d,.\s]*(?:%|INR|USD|EUR)?", str(value).strip(), re.IGNORECASE))
    if numeric and _to_decimal(value) is not None:
        return "integer" if _to_decimal(value) % 1 == 0 else "decimal"
    if _to_datetime(value) is not None:
        return "date"
    return "text"


@dataclass
class PhysicalColumn:
    id: str
    label: str
    display_label: str
    kind: str = "unknown"


@dataclass
class ImportTable:
    id: str
    sheet: str
    header_start: int
    header_end: int
    columns: list[PhysicalColumn]
    records: list[dict]
    row_numbers: list[int]
    mapping: dict[str, str]
    fingerprint: str
    score: float
    exclusions: list[dict] = field(default_factory=list)
    review_rows: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def preview(self) -> dict:
        from dataclasses import asdict
        result = asdict(self)
        result["sample_rows"] = result.pop("records")[:3]
        result["rows_total"] = len(self.records)
        result.pop("row_numbers")
        return result


def _read(filename: str, content: bytes):
    if len(content) > 10 * 1024 * 1024:
        raise ValueError("File exceeds the 10 MiB limit")
    if not content:
        raise ValueError("File is empty")
    suffix = filename.rsplit(".", 1)[-1].lower()
    if suffix in {"xlsx", "xlsm"}:
        from openpyxl import load_workbook
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                if sum(info.file_size for info in archive.infolist()) > 100 * 1024 * 1024:
                    raise ValueError("Expanded workbook exceeds 100 MiB")
                sheets = [n for n in archive.namelist() if re.fullmatch(r"xl/worksheets/sheet\d+\.xml", n)]
                if len(sheets) > 20:
                    raise ValueError("Workbook exceeds 20 sheets")
                cells = 0
                for name in sheets:
                    with archive.open(name) as source:
                        for _, element in iterparse(source, events=("end",)):
                            if element.tag.endswith("}c"):
                                cells += 1
                                if cells > 1_000_000:
                                    raise ValueError("Workbook exceeds 1,000,000 examined cells")
                            element.clear()
            wb = load_workbook(io.BytesIO(content), data_only=True, keep_links=False)
            formulas = load_workbook(io.BytesIO(content), data_only=False, keep_links=False)
            result = []
            for ws in wb.worksheets:
                if ws.max_column > 200:
                    raise ValueError("Table exceeds 200 columns")
                if ws.max_row * ws.max_column > 1_000_000:
                    raise ValueError("Workbook exceeds 1,000,000 examined cells")
                rows = [list(row) for row in ws.iter_rows(values_only=True)]
                missing = {cell.coordinate for row in formulas[ws.title] for cell in row
                           if cell.data_type == "f" and ws[cell.coordinate].value is None}
                result.append((ws.title, rows, list(ws.merged_cells.ranges), missing))
            wb.close()
            formulas.close()
            return result
        except (zipfile.BadZipFile, KeyError, OSError, ParseError) as exc:
            raise ValueError("Invalid Excel workbook") from exc
    if suffix not in {"csv", "tsv", "txt"}:
        raise ValueError("Use CSV, TSV or XLSX")
    text = content.decode("utf-8-sig", errors="strict")
    try:
        delimiter = "\t" if suffix == "tsv" else csv.Sniffer().sniff(text[:8192], delimiters=",;\t|").delimiter
    except csv.Error:
        delimiter = "\t" if suffix == "tsv" else ","
    rows, cells = [], 0
    for row in csv.reader(io.StringIO(text), delimiter=delimiter):
        if len(row) > 200:
            raise ValueError("Table exceeds 200 columns")
        cells += len(row)
        if cells > 1_000_000:
            raise ValueError("Table exceeds 1,000,000 examined cells")
        rows.append([cell.strip() for cell in row])
    return [("CSV", rows, [], set())]


def _candidate(sheet, rows, merges, missing, start, end, kind, *, preview_only=False):
    width = max((len(row) for row in rows[start - 1:]), default=0)
    labels = []
    for column in range(width):
        parts = []
        for row_index in range(start, end + 1):
            value = rows[row_index - 1][column] if column < len(rows[row_index - 1]) else None
            for merge in merges:
                if merge.min_row <= row_index <= merge.max_row and merge.min_col <= column + 1 <= merge.max_col:
                    if merge.min_row >= start and merge.max_row <= end:
                        value = rows[merge.min_row - 1][merge.min_col - 1]
            label = str(value or "").strip()
            if label and (not parts or parts[-1] != label):
                parts.append(label)
        labels.append(" / ".join(parts))
    if sum(bool(label) for label in labels) < 2:
        return None
    columns = [PhysicalColumn(f"c{i+1}", label, label or f"Column {i+1}") for i, label in enumerate(labels)]
    for i, column in enumerate(columns):
        if labels.count(column.label) > 1:
            column.display_label += f" [{i+1}]"
    mapping = {}
    for column in columns:
        for path in [column.label, *reversed(column.label.split(" / "))]:
            for key in _build_header_map([path]):
                if key in fields_for(kind) and key not in mapping:
                    mapping[key] = column.id
    records, numbers, exclusions, reviews, warnings = [], [], [], [], []
    following = rows[end:end + 8] if preview_only else rows[end:]
    for offset, row in enumerate(following, end + 1):
        padded = (row + [None] * width)[:width]
        if not any(value is not None and value != "" for value in padded):
            continue
        if [_norm(v) for v in padded] == [_norm(label.split(" / ")[-1]) for label in labels]:
            exclusions.append({"row": offset, "reason": "repeated_header"})
            continue
        first = _norm(next((v for v in padded if v is not None and v != ""), ""))
        date_index = int(mapping["timestamp"][1:]) - 1 if "timestamp" in mapping else None
        has_date = date_index is not None and _type(padded[date_index]) == "date"
        summary_label = first in {"subtotal", "grand total", "total", "कुल", "మొత్తం", "மொத்தம்"}
        # For stock/catalogues, a complete SKU row named Total is a real detail.
        required_values_present = all(any(key in mapping and padded[int(mapping[key][1:]) - 1] not in (None, "")
                                          for key in group) for group in _REQUIRED[kind])
        if summary_label and not has_date and (kind == "sales" or not required_values_present):
            exclusions.append({"row": offset, "reason": "subtotal"})
            continue
        record = {column.id: padded[i] for i, column in enumerate(columns)}
        identity = [record.get(mapping[key]) for key in ("sku", "name") if key in mapping]
        if identity and not any(identity):
            reviews.append(offset)
        records.append(record)
        numbers.append(offset)
        for merge in merges:
            if merge.min_row <= offset <= merge.max_row and merge.max_row > end and offset > merge.min_row:
                from openpyxl.utils import get_column_letter
                warnings.append(f"{sheet}!{get_column_letter(merge.min_col)}{offset}: merged data cell is missing; no forward fill")
    if not records:
        return None
    for column in columns:
        types = [_type(record[column.id]) for record in records[:8] if record[column.id] not in (None, "")]
        column.kind = max(set(types), key=types.count) if types else "unknown"
    warnings.extend(f"{sheet}!{cell}: formula has no cached value" for cell in sorted(missing if not preview_only else [])
                    if int(re.sub(r"\D", "", cell)) > end)
    structural = sum(column.kind != "text" and column.kind != "unknown" for column in columns)
    required = sum(bool(set(mapping) & group) for group in _REQUIRED[kind])
    score = required * 20 + len(mapping) * 3 + structural + sum(bool(v) for v in labels) / max(width, 1)
    # Workbook roles are ranking evidence, never automatic semantic assignments.
    role_terms = {"sales": {"sales", "ledger", "transactions"},
                  "inventory": {"inventory", "warehouse", "stock"},
                  "products": {"products", "catalog", "catalogue"}}[kind]
    score += 12 * bool(set(re.findall(r"\w+", sheet.casefold())) & role_terms)
    if kind == "inventory":
        score += 12 * any("stock" in _norm(label) or "inventory" in _norm(label) for label in labels)
    shape = {"parser": PARSER_VERSION, "kind": kind, "headers": [_norm(v) for v in labels],
             "span": end - start, "merges": [(m.min_row-start, m.max_row-start, m.min_col, m.max_col)
                                              for m in merges if start <= m.min_row <= m.max_row <= end]}
    fingerprint = hashlib.sha256(json.dumps(shape, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    table_id = "t" + hashlib.sha256(f"{sheet}:{start}:{end}".encode()).hexdigest()[:16]
    return ImportTable(table_id, sheet, start, end, columns, records, numbers, mapping, fingerprint,
                       score, exclusions, reviews, warnings)


def discover_tables(filename: str, content: bytes, kind: str, *, header_overrides: dict | None = None,
                    sheets: list | None = None) -> list[ImportTable]:
    """``sheets`` is a prior ``_read`` result, so callers trying several kinds parse a workbook once."""
    fields_for(kind)
    sheets = sheets if sheets is not None else _read(filename, content)
    overrides = header_overrides or {}
    if not set(overrides) <= {s[0] for s in sheets}:
        raise ValueError("Unknown sheet for header selection")
    result = []
    for sheet, rows, merges, missing in sheets:
        spans = []
        if sheet in overrides:
            span = overrides[sheet]
            if (not isinstance(span, list) or len(span) != 2 or any(type(i) is not int for i in span)
                    or not 1 <= span[0] <= span[1] <= len(rows) or span[1] - span[0] > 2):
                raise ValueError("Invalid header row selection")
            spans.append(tuple(span))
        else:
            for i, row in enumerate(rows[:100], 1):
                populated = [v for v in row if v is not None and v != ""]
                if len(populated) < 2 or not all(_type(value) == "text" for value in populated):
                    continue
                spans.append((i, i))
                if i < len(rows) and any(m.min_row == i and m.max_row == i and m.max_col > m.min_col for m in merges):
                    spans.append((i, i + 1))
        candidates = [t for start, end in spans if (t := _candidate(sheet, rows, merges, missing, start, end, kind,
                                                                  preview_only=sheet not in overrides))]
        if candidates:
            # One best table per sheet; explicit row selection can choose an alternative.
            selected = max(candidates, key=lambda t: (t.score, -t.header_start))
            result.append(selected if sheet in overrides else _candidate(sheet, rows, merges, missing,
                                                                         selected.header_start, selected.header_end, kind))
    if not result:
        raise ValueError("No data table found; select a sheet and header row")
    return sorted(result, key=lambda table: table.score, reverse=True)
