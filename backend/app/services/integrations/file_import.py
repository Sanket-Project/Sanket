"""File upload → canonical schema import (CSV / Excel).

This is the universal, always-available connector: whatever a customer's stack
is, they can export sales / inventory / products to a spreadsheet and land it in
SANKET's canonical tables (products / skus / inventory_levels / historical_sales).

Design mirrors the Shopify sync: the pure ``map_*_row`` helpers do all the field
mapping and column-alias resolution with no DB dependency (so they're unit
tested), and a thin DB orchestrator upserts the mapped rows in one tenant-scoped
transaction.

Column matching is forgiving — headers are lower-cased, stripped of spaces /
underscores, and matched against an alias set — so "Selling Price", "unit_price"
and "price" all resolve to the same field.
"""

from __future__ import annotations

import csv
import hashlib
import io
import re
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.models.enums import IndustryCode, ProductStatus
from app.models.inventory import InventoryLevel
from app.models.product import Product, Sku
from app.models.sales import HistoricalSale

log = structlog.get_logger(__name__)

SOURCE = "upload"

# Uploaded sale_time must land inside an existing range partition of
# historical_sales (static quarters cover ~2022-2027 + rolling maintenance).
# Rows outside this window are skipped with a clear error rather than failing
# the whole transaction with "no partition found".
_MIN_SALE_DATE = date(2022, 1, 1)


def _max_sale_date() -> date:
    return date(datetime.now(tz=UTC).year + 1, 12, 31)


# ── Column alias resolution ──────────────────────────────────────────────────
def _norm(header: str) -> str:
    return "".join(ch for ch in header.lower() if ch.isalnum())


def _slugify(value: str) -> str:
    """Best-effort URL/code-safe slug used to derive a SKU code from a name."""
    slug = "-".join(re.findall(r"[a-z0-9]+", value.lower()))
    return slug[:40] or "item"


# Each canonical field maps to a set of accepted (normalized) header aliases.
# The alias keys are always the result of _norm() — lowercase, alphanumeric only.
_ALIASES: dict[str, set[str]] = {
    "sku": {
        "sku",
        "skucode",
        "skuid",
        "item",
        "itemcode",
        "itemsku",
        "productcode",
        "productsku",
        "variantsku",
        "code",
        "externalid",
    },
    "quantity": {
        "quantity",
        "qty",
        "units",
        "unitssold",
        "unitvelocity",
        "unitsvelocity",       # "Units Velocity" variant
        "sold",
        "count",
        "volume",
        "qtyordered",
        "ordered",
        "quantitysold",        # "Quantity Sold"
        "quantityordered",     # "Quantity Ordered"
        "orderqty",            # "Order Qty"
        "orderedqty",          # "Ordered Qty"
        "salesqty",            # "Sales Qty"
        "itemssold",           # "Items Sold"
        "totalunits",          # "Total Units"
        "numberofunits",       # "Number of Units"
        "noofunits",           # "No. of Units"
        "unitsordered",        # "Units Ordered"
        "piecesordered",       # "Pieces Ordered"
        "pieces",              # "Pieces"
        "pcs",                 # "Pcs"
    },
    "price": {
        "sellingprice",
        "price",
        "unitprice",
        "saleprice",
        "amount",
        "rate",
        "retailprice",
        "costprice",
        "unitcost",
        "cost",
    },
    "revenue": {
        "revenue",
        "grossrevenue",
        "totalrevenue",
        "sales",
        "total",
        "linetotal",
        "totalsales",
        "saleamount",
        "linerevenueamount",
        "totalamount",
    },
    "cogs": {"cogs", "totalcogs", "costofgoodssold", "costofsales"},
    "discount": {"discount", "markdown", "discountamount"},
    "timestamp": {
        "timestamp",
        "date",
        "saledate",
        "orderdate",
        "ordertimestamp",
        "transactiondate",
        "transactiontimestamp",
        "datetime",
        "time",
        "soldat",
        "createdat",
        "invoicedate",
        "salestimestamp",
    },
    "channel": {
        "channel",
        "source",
        "saleschannel",
        "store",
        "platform",
        "checkoutchannel",
        "multichannelcheckoutpath",
        "ordertype",
    },
    "order_id": {
        "orderid",
        "order",
        "ordernumber",
        "transactionid",
        "orderno",
        "invoice",
        "invoiceid",
        "invoicenumber",
        "receiptid",
    },
    "region": {"region", "country", "state", "market"},
    # ── inventory ────────────────────────────────────────────────────────────
    # NOTE: "quantity" and "qty" are intentionally NOT listed here — they belong
    # exclusively to the "quantity" canonical field above.  This prevents a column
    # literally named "Quantity" in a sales file from being stolen by the inventory
    # field and leaving the actual sales quantity unmapped.
    "available": {
        "availablestock",
        "available",
        "onhand",
        "stock",
        "stockonhand",
        "currentstock",
        "currentstockonhand",
        "onhandunits",
        "inventoryonhand",
        "unitsonhand",
        "physicalstock",
        "physicalinventory",
        "netstock",
    },
    "reserved": {"reservedstock", "reserved", "allocated", "reservedunits"},
    "inbound": {"inboundstock", "inbound", "incoming", "onorder", "inboundunits"},
    "reorder_point": {
        "reorderpoint",
        "reorderthreshold",
        "safetystock",
        "safetylevel",
        "safetythreshold",
        "reorderqty",
        "minstock",
        "minimumstock",
    },
    "warehouse": {
        "warehouseid",
        "warehouse",
        "location",
        "hub",
        "hubname",
        "hubregion",
        "fulfillmenthub",
        "fulfillmentcenter",
        "dc",
        "site",
        "binlocation",
        "storagelocation",
    },
    # products
    "name": {"name", "productname", "title", "product", "itemname", "skudescription"},
    "brand": {"brand", "vendor", "manufacturer", "supplier"},
    "category": {
        "category",
        "producttype",
        "type",
        "department",
        "productcategory",
        "categoryindexing",
        "categoryindex",
    },
    "size": {"size", "sizevariant", "sizecode", "productsize"},
    "description": {"description", "desc", "variant", "option"},
    "gtin": {"gtin", "barcode", "ean", "upc"},
}


def _build_header_map(headers: list[str]) -> dict[str, str]:
    """Map canonical field name → the actual header present in the file."""
    found: dict[str, str] = {}
    for raw in headers:
        n = _norm(raw)
        for field_name, aliases in _ALIASES.items():
            if n in aliases and field_name not in found:
                found[field_name] = raw
    return found


# ── File parsing ─────────────────────────────────────────────────────────────
def parse_table(filename: str, content: bytes) -> tuple[list[str], list[dict[str, Any]]]:
    """Parse an uploaded CSV/TSV/XLSX into (headers, list-of-row-dicts).

    Raises ValueError on an unsupported type, empty file, or missing header row.
    """
    name = (filename or "").lower()
    if name.endswith(".xlsx") or name.endswith(".xlsm"):
        return _parse_xlsx(content)
    if name.endswith((".csv", ".tsv", ".txt")):
        return _parse_csv(content, delimiter="\t" if name.endswith(".tsv") else None)
    raise ValueError("Unsupported file type — upload a .csv, .tsv or .xlsx file")


def _parse_csv(content: bytes, delimiter: str | None) -> tuple[list[str], list[dict[str, Any]]]:
    text_data = content.decode("utf-8-sig", errors="replace")
    sample = text_data[:4096]
    if delimiter is None:
        try:
            delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
        except csv.Error:
            delimiter = ","
    reader = csv.reader(io.StringIO(text_data), delimiter=delimiter)
    rows = list(reader)
    if not rows:
        raise ValueError("File is empty")
    headers = [h.strip() for h in rows[0]]
    records = [
        {
            headers[i]: (cell.strip() if isinstance(cell, str) else cell)
            for i, cell in enumerate(r)
            if i < len(headers)
        }
        for r in rows[1:]
        if any((c or "").strip() for c in r)
    ]
    return headers, records


def _parse_xlsx(content: bytes) -> tuple[list[str], list[dict[str, Any]]]:
    """Parse an XLSX workbook into (headers, records).

    For multi-tab workbooks (e.g. a dashboard + data sheets) we score every
    sheet by how many of its first-row headers match a known canonical alias,
    then pick the best candidate.  This avoids landing on dashboard / summary
    tabs that have no tabular data recognizable by the importer.
    """
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise ValueError(
            "Excel support is unavailable on this server — upload a CSV instead"
        ) from exc

    # Build a flat set of every known alias for quick membership tests.
    _all_aliases: set[str] = set()
    for aliases in _ALIASES.values():
        _all_aliases.update(aliases)

    def _score_sheet(ws) -> int:  # type: ignore[return]
        """Return the number of first-row cells that match a known alias."""
        try:
            first_row = next(ws.iter_rows(values_only=True))
        except StopIteration:
            return 0
        if first_row is None:
            return 0
        return sum(
            1
            for h in first_row
            if h is not None and _norm(str(h)) in _all_aliases
        )

    def _read_sheet(ws) -> tuple[list[str], list[dict[str, Any]]]:
        rows_iter = ws.iter_rows(values_only=True)
        try:
            first = next(rows_iter)
        except StopIteration as exc:
            raise ValueError("Worksheet is empty") from exc
        headers = [
            str(h).strip() if h is not None else f"col{i}" for i, h in enumerate(first)
        ]
        records: list[dict[str, Any]] = []
        for row in rows_iter:
            if row is None or all(c is None for c in row):
                continue
            records.append({headers[i]: row[i] for i in range(len(headers)) if i < len(row)})
        return headers, records

    wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    try:
        sheet_names = wb.sheetnames
        if not sheet_names:
            raise ValueError("Workbook is empty")

        if len(sheet_names) == 1:
            # Single-sheet workbook — just use it directly.
            return _read_sheet(wb[sheet_names[0]])

        # Multi-sheet: pick the sheet with the highest alias-match score.
        # Tie-break: prefer later sheets (data tabs are usually after summary tabs).
        best_name: str | None = None
        best_score = -1
        for name in sheet_names:
            ws = wb[name]
            score = _score_sheet(ws)
            if score > best_score:
                best_score = score
                best_name = name

        if best_name is None or best_score == 0:
            # No sheet matched any alias — fall back to the first sheet so the
            # user at least sees real headers in the column-mapping UI.
            # wb.active can be None in openpyxl ≥ 3.1, so use sheet_names[0].
            best_name = sheet_names[0]

        log.debug(
            "xlsx.sheet_selected",
            sheet=best_name,
            score=best_score,
            all_sheets=sheet_names,
        )
        return _read_sheet(wb[best_name])
    finally:
        wb.close()


# ── Value coercion ───────────────────────────────────────────────────────────
def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value))
    s = str(value).strip()
    # Remove currency symbols and other non-numeric chars except digits, comma, period, minus
    s = re.sub(r"[^\d,.-]", "", s)
    if not s:
        return None
    
    # Handle comma as decimal separator
    if "," in s and "." not in s:
        parts = s.split(",")
        if len(parts) == 2 and len(parts[1]) != 3:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s and "." in s:
        if s.find(",") > s.find("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
            
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    d = _to_decimal(value)
    return int(d) if d is not None else None


_DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d-%m-%Y",
    "%m/%d/%Y %H:%M",
    "%d/%m/%Y %H:%M",
    "%b %d, %Y",      # Jul 15, 2026
    "%d-%b-%Y",      # 15-Jul-2026
    "%Y/%m/%d",
    "%Y/%m/%d %H:%M:%S",
    "%Y%m%d",        # 20260715
)


def _to_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    s = str(value).strip()
    # Strip common day names and timezones
    s = re.sub(r"^(Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s*", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s+(EST|EDT|PST|PDT|CST|CDT|MST|MDT|GMT|UTC)$", "", s, flags=re.IGNORECASE)

    # Standardize trailing Z/z to +00:00 for robust parsing across Python versions
    if s.endswith(("Z", "z")):
        s = s[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt.astimezone(UTC)
    except ValueError:
        pass

    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=UTC)
            return dt.astimezone(UTC)
        except ValueError:
            continue
    return None


# ── Pure row mappers (unit tested) ───────────────────────────────────────────
class RowError(ValueError):
    """A row that can't be mapped; message is surfaced to the user."""


def map_sales_row(row: dict[str, Any], hmap: dict[str, str]) -> dict[str, Any]:
    """Map a raw row to a partial historical_sales dict (no tenant/sku_id).

    Requires a SKU or Name, a positive quantity, and an in-window timestamp.
    """
    sku = str(row.get(hmap.get("sku", ""), "") or "").strip()
    name = str(row.get(hmap.get("name", ""), "") or "").strip()
    if not sku and not name:
        raise RowError("missing SKU or product name")
    if not sku:
        digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:6]
        sku = f"{_slugify(name)}-{digest}"
    qty = _to_int(row.get(hmap.get("quantity", "")))
    if qty is None or qty <= 0:
        raise RowError(f"invalid quantity for SKU {sku}")
    when = _to_datetime(row.get(hmap.get("timestamp", "")))
    if when is None:
        raise RowError(f"missing/invalid date for SKU {sku}")
    if not (_MIN_SALE_DATE <= when.date() <= _max_sale_date()):
        raise RowError(f"date {when.date()} for SKU {sku} is outside the supported range")

    price = _to_decimal(row.get(hmap.get("price", "")))
    discount = _to_decimal(row.get(hmap.get("discount", ""))) or Decimal("0")
    revenue = _to_decimal(row.get(hmap.get("revenue", "")))
    if revenue is None and price is not None:
        revenue = price * qty
    net = (revenue - discount) if revenue is not None else None
    channel = str(row.get(hmap.get("channel", ""), "") or "upload").strip() or "upload"
    region = str(row.get(hmap.get("region", ""), "") or "").strip() or None
    order_id = str(row.get(hmap.get("order_id", ""), "") or "").strip() or None

    return {
        "_sku_code": sku,
        "sale_time": when,
        "channel": channel,
        "region": region,
        "units_sold": qty,
        "gross_revenue": revenue,
        "net_revenue": net,
        "metadata_": {"source": SOURCE, "order_id": order_id},
    }


def map_inventory_row(row: dict[str, Any], hmap: dict[str, str]) -> dict[str, Any]:
    sku = str(row.get(hmap.get("sku", ""), "") or "").strip()
    if not sku:
        raise RowError("missing SKU")
    available = _to_decimal(row.get(hmap.get("available", "")))
    if available is None:
        raise RowError(f"missing stock quantity for SKU {sku}")
    reserved = _to_decimal(row.get(hmap.get("reserved", ""))) or Decimal("0")
    inbound = _to_decimal(row.get(hmap.get("inbound", ""))) or Decimal("0")
    location = str(row.get(hmap.get("warehouse", ""), "") or "default").strip() or "default"
    return {
        "_sku_code": sku,
        "location": location,
        "on_hand_units": max(Decimal("0"), available),
        "reserved_units": max(Decimal("0"), reserved),
        "inbound_units": max(Decimal("0"), inbound),
    }


def map_product_row(row: dict[str, Any], hmap: dict[str, str]) -> dict[str, Any]:
    sku = str(row.get(hmap.get("sku", ""), "") or "").strip()
    name = str(row.get(hmap.get("name", ""), "") or "").strip()
    if not sku and not name:
        raise RowError("missing SKU or product name")
    if not sku:
        # Common real-world catalog exports (and the in-app Products importer)
        # only require a name/category — not an explicit SKU code. Derive a
        # deterministic code from the name rather than rejecting the row, so
        # the two import paths accept the same files. The hash suffix is a pure
        # function of the name, so re-importing the same file upserts the same
        # sku_code (idempotent) instead of creating duplicate SKUs each run,
        # while still keeping distinct full names that slugify alike apart.
        digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:6]
        sku = f"{_slugify(name)}-{digest}"
    name = name or sku
    return {
        "_sku_code": sku,
        "name": name,
        "brand": (str(row.get(hmap.get("brand", ""), "") or "").strip() or None),
        "category": (str(row.get(hmap.get("category", ""), "") or "").strip() or "Uncategorized"),
        "description": (str(row.get(hmap.get("description", ""), "") or "").strip() or None),
        "gtin": (str(row.get(hmap.get("gtin", ""), "") or "").strip() or None),
        "unit_price": _to_decimal(row.get(hmap.get("price", ""))),
    }


# ── DB orchestration ─────────────────────────────────────────────────────────
_REQUIRED: dict[str, set[str]] = {
    "sales": {"sku", "quantity", "timestamp"},
    "inventory": {"sku", "available"},
    # "sku" is NOT required here: map_product_row accepts either a sku/code
    # column or a name column (deriving a SKU code from the name when no
    # explicit code is given), matching what the in-app Products importer
    # already accepts. The per-row check still rejects rows with neither.
    "products": set(),
}


async def _ensure_import_product(
    session, tenant_id: uuid.UUID, industry: IndustryCode
) -> uuid.UUID:
    """Get-or-create the catch-all product that imported SKUs hang off of."""
    existing = await session.scalar(
        select(Product.id).where(
            Product.tenant_id == tenant_id,
            Product.external_id == "__imported__",
        )
    )
    if existing:
        return existing
    stmt = (
        pg_insert(Product)
        .values(
            tenant_id=tenant_id,
            industry=industry,
            external_id="__imported__",
            name="Imported items",
            category="Imported",
            status=ProductStatus.active,
            attributes={"source": SOURCE},
        )
        .on_conflict_do_update(
            index_elements=[Product.tenant_id, Product.external_id],
            index_where=Product.external_id.isnot(None),
            set_={"name": "Imported items"},
        )
        .returning(Product.id)
    )
    return (await session.execute(stmt)).scalar_one()


async def _load_sku_map(session, tenant_id: uuid.UUID) -> dict[str, uuid.UUID]:
    rows = await session.execute(select(Sku.sku_code, Sku.id).where(Sku.tenant_id == tenant_id))
    return dict(rows.all())


async def _get_or_create_sku(
    session,
    tenant_id: uuid.UUID,
    industry: IndustryCode,
    sku_code: str,
    sku_map: dict[str, uuid.UUID],
    import_product_id: uuid.UUID,
    *,
    unit_price: Decimal | None = None,
) -> uuid.UUID:
    if sku_code in sku_map:
        return sku_map[sku_code]
    stmt = (
        pg_insert(Sku)
        .values(
            tenant_id=tenant_id,
            product_id=import_product_id,
            industry=industry,
            sku_code=sku_code,
            unit_price=unit_price,
            attributes={"source": SOURCE},
            is_active=True,
        )
        .on_conflict_do_update(
            index_elements=[Sku.tenant_id, Sku.sku_code],
            set_={"is_active": True},
        )
        .returning(Sku.id)
    )
    sku_id = (await session.execute(stmt)).scalar_one()
    sku_map[sku_code] = sku_id
    return sku_id


async def import_rows(
    *,
    db,
    tenant_id: uuid.UUID,
    industry: IndustryCode,
    kind: str,
    headers: list[str],
    records: list[dict[str, Any]],
    column_mapping: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Map and persist parsed rows for one ``kind`` (sales|inventory|products).

    Returns a stats dict matching the UploadResult schema fields.
    """
    if kind not in _REQUIRED:
        raise ValueError(f"Unknown import kind: {kind}")
    
    if column_mapping is not None:
        mapped_keys = {k for k, v in column_mapping.items() if v}
        if kind == "sales":
            if "sku" not in mapped_keys and "name" not in mapped_keys:
                raise ValueError("Must map either SKU or Product Name")
            if "quantity" not in mapped_keys or "timestamp" not in mapped_keys:
                raise ValueError("Missing mapping for required column(s): quantity, timestamp")
        elif kind == "inventory":
            if "sku" not in mapped_keys or "available" not in mapped_keys:
                raise ValueError("Missing mapping for required column(s): SKU, Available Stock")
        elif kind == "products":
            if "sku" not in mapped_keys and "name" not in mapped_keys:
                raise ValueError("Must map either SKU or Product Name")
        
        header_set = set(headers)
        hmap = {k: v for k, v in column_mapping.items() if v in header_set}
    else:
        hmap = _build_header_map(headers)
        missing = _REQUIRED[kind] - set(hmap)
        if missing:
            pretty = ", ".join(sorted(missing))
            raise ValueError(f"File is missing required column(s) for {kind}: {pretty}")

    mapper = {"sales": map_sales_row, "inventory": map_inventory_row, "products": map_product_row}[
        kind
    ]
    mapped: list[dict[str, Any]] = []
    errors: list[str] = []
    for idx, row in enumerate(records, start=2):  # row 1 is the header
        try:
            mapped.append(mapper(row, hmap))
        except RowError as exc:
            if len(errors) < 50:
                errors.append(f"Row {idx}: {exc}")

    stats: dict[str, Any] = {
        "rows_total": len(records),
        "rows_imported": 0,
        "rows_skipped": len(records) - len(mapped),
        "products_created": 0,
        "skus_created": 0,
        "inventory_rows": 0,
        "sales_rows": 0,
        "errors": errors,
    }
    if not mapped:
        return stats

    upload_id = uuid.uuid4().hex
    async with db.session(str(tenant_id)) as session:
        import_product_id = await _ensure_import_product(session, tenant_id, industry)
        sku_map = await _load_sku_map(session, tenant_id)
        before = set(sku_map)

        if kind == "products":
            for m in mapped:
                # gtin lives in attributes (not the column) to avoid tripping the
                # partial-unique gtin index on dirty catalogs — same choice the
                # Shopify sync makes for the barcode field.
                attrs = {"source": SOURCE, "brand": m["brand"], "gtin": m["gtin"]}
                stmt = (
                    pg_insert(Sku)
                    .values(
                        tenant_id=tenant_id,
                        product_id=import_product_id,
                        industry=industry,
                        sku_code=m["_sku_code"],
                        description=m["description"],
                        unit_price=m["unit_price"],
                        attributes=attrs,
                        is_active=True,
                    )
                    .on_conflict_do_update(
                        index_elements=[Sku.tenant_id, Sku.sku_code],
                        set_={
                            "description": m["description"],
                            "unit_price": m["unit_price"],
                            "attributes": attrs,
                            "is_active": True,
                        },
                    )
                    .returning(Sku.id)
                )
                sku_map[m["_sku_code"]] = (await session.execute(stmt)).scalar_one()
                stats["rows_imported"] += 1

        elif kind == "inventory":
            for m in mapped:
                sku_id = await _get_or_create_sku(
                    session, tenant_id, industry, m["_sku_code"], sku_map, import_product_id
                )
                await session.execute(
                    pg_insert(InventoryLevel)
                    .values(
                        tenant_id=tenant_id,
                        sku_id=sku_id,
                        industry=industry,
                        location=m["location"],
                        on_hand_units=m["on_hand_units"],
                        reserved_units=m["reserved_units"],
                        inbound_units=m["inbound_units"],
                        source=SOURCE,
                        as_of=datetime.now(tz=UTC),
                    )
                    .on_conflict_do_update(
                        constraint="uq_inventory_tenant_sku_loc",
                        set_={
                            "on_hand_units": m["on_hand_units"],
                            "reserved_units": m["reserved_units"],
                            "inbound_units": m["inbound_units"],
                            "source": SOURCE,
                            "as_of": datetime.now(tz=UTC),
                        },
                    )
                )
                stats["inventory_rows"] += 1
                stats["rows_imported"] += 1

        else:  # sales
            for m in mapped:
                sku_id = await _get_or_create_sku(
                    session, tenant_id, industry, m["_sku_code"], sku_map, import_product_id
                )
                meta = {**m["metadata_"], "upload_id": upload_id}
                session.add(
                    HistoricalSale(
                        tenant_id=tenant_id,
                        sku_id=sku_id,
                        industry=industry,
                        sale_time=m["sale_time"],
                        channel=m["channel"],
                        region=m["region"],
                        units_sold=m["units_sold"],
                        gross_revenue=m["gross_revenue"],
                        net_revenue=m["net_revenue"],
                        metadata_=meta,
                    )
                )
                stats["sales_rows"] += 1
                stats["rows_imported"] += 1

        stats["skus_created"] = len(set(sku_map) - before)

    log.info(
        "file_import.done",
        tenant=str(tenant_id),
        kind=kind,
        imported=stats["rows_imported"],
        skipped=stats["rows_skipped"],
    )
    return stats
