"""Smart import: plan several report files, preview each plan, import one file per transaction.

A plan is a *decision* the user can edit — destinations, field → column mapping,
two fixed transforms, a size-code map and an optional period. Nothing here
trusts the client's copy of the data: preview and confirm re-read the uploaded
bytes, bound by a signed token, and run the same deterministic pipeline.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import replace
from datetime import date
from decimal import Decimal

from sqlalchemy import text

from app.models.enums import IndustryCode
from app.services import audit
from app.services.fashion_sizes import CANONICAL_SIZES, normalize_size
from app.services.integrations import import_plan as planner
from app.services.integrations import import_transforms as tx
from app.services.integrations.file_import import (
    _ensure_import_product,
    _get_or_create_sku,
    _load_sku_map,
    _to_decimal,
    _workspace_currency,
    import_rows,
)
from app.services.integrations.import_layout import _read, discover_tables
from app.services.integrations.import_profiles import issue_analysis, verify_analysis
from app.services.integrations.import_review import _BoundDB, _member
from app.services.llm.contracts import Column
from app.services.llm.import_plan_task import PlanInput
from app.services.llm.policy import AIContext
from app.services.llm.tasks import TaskRequest

MAX_FILES = 10
_KINDS = ("inventory", "products", "sales")
#: Derived columns and the transform that produces each.
DERIVED = {"x_sku": "group_pieces", "x_colour": "parse_variant", "x_size": "parse_variant"}
_DERIVED_LABELS = {"x_sku": "Variant SKU (brand-style-colour-size)", "x_colour": "Colour (from description)",
                   "x_size": "Size (from description)"}
_SUMMED = ("available", "reserved", "inbound", "quantity", "revenue", "cogs", "returns")
_ORDER = ("products", "inventory", "sales", "period_sales")
_PREVIEW_ROWS = 5
_LISTED_EXCLUSIONS = 100


# ── Table discovery ──────────────────────────────────────────────────────────
def _discover(filename: str, content: bytes, kind: str | None = None, overrides: dict | None = None):
    """Best table across import kinds (or the token's kind), plus letterhead text above it."""
    best, best_kind = None, None
    for candidate in ([kind] if kind else _KINDS):
        try:
            table = discover_tables(filename, content, candidate, header_overrides=overrides)[0]
        except ValueError:
            continue
        if best is None or table.score > best.score:
            best, best_kind = table, candidate
    if best is None:
        raise ValueError("No data table found in this file")
    sheet_rows = next(rows for name, rows, _, _ in _read(filename, content) if name == best.sheet)
    lines = list(dict.fromkeys(str(v) for row in sheet_rows[:best.header_start - 1] for v in row if v))
    return best, best_kind, lines


def _columns(table) -> list[dict]:
    source = [{"id": c.id, "label": c.display_label, "kind": c.kind, "derived": False} for c in table.columns]
    return source + [{"id": k, "label": v, "kind": "text", "derived": True} for k, v in _DERIVED_LABELS.items()]


# ── Decision validation ──────────────────────────────────────────────────────
def _decision(raw, column_ids: set[str]) -> dict:
    if not isinstance(raw, dict) or set(raw) - {"destinations", "mapping", "transforms", "size_map", "period", "currency"}:
        raise ValueError("Unknown plan decision fields")
    destinations = raw.get("destinations") or []
    if (not isinstance(destinations, list) or len(set(destinations)) != len(destinations)
            or not set(destinations) <= set(planner.DESTINATIONS)):
        raise ValueError("Unknown import destination")
    mapping = {k: v for k, v in (raw.get("mapping") or {}).items() if v}
    if (not all(isinstance(k, str) and isinstance(v, str) for k, v in mapping.items())
            or not set(mapping) <= set(planner.PLAN_FIELDS)
            or not set(mapping.values()) <= column_ids | set(DERIVED)):
        raise ValueError("Mapping refers to unsupported fields or unknown columns")
    if len(set(mapping.values())) != len(mapping):
        raise ValueError("A column cannot map to multiple fields")
    transforms = raw.get("transforms") or {}
    if set(transforms) - {"parse_variant", "group_pieces"} or any(type(v) is not bool for v in transforms.values()):
        raise ValueError("Unknown transform")
    transforms = {"parse_variant": transforms.get("parse_variant", False),
                  "group_pieces": transforms.get("group_pieces", False)}
    for column in mapping.values():
        if column in DERIVED and not transforms[DERIVED[column]]:
            raise ValueError(f"Turn on {DERIVED[column].replace('_', ' ')} to use {_DERIVED_LABELS[column]}")
    if transforms["group_pieces"]:
        if "style" not in mapping:
            raise ValueError("Grouping pieces needs a style column")
        if "sales" in destinations:
            raise ValueError("Grouping pieces would merge dated sales lines; turn it off for sales")
    size_map = raw.get("size_map") or {}
    if (not isinstance(size_map, dict) or len(size_map) > 1000
            or any(not isinstance(k, str) or v not in (*CANONICAL_SIZES, "") for k, v in size_map.items())):
        raise ValueError("Size codes can map only to a known size or blank")
    period = raw.get("period")
    if period is not None:
        try:
            start, end = date.fromisoformat(period["start"]), date.fromisoformat(period["end"])
        except (TypeError, KeyError, ValueError):
            raise ValueError("Period needs ISO start and end dates") from None
        if start > end:
            raise ValueError("Period start is after its end")
        period = {"start": start.isoformat(), "end": end.isoformat()}
    currency = raw.get("currency")
    if currency is not None and not (isinstance(currency, str) and re.fullmatch(r"[A-Z]{3}", currency)):
        raise ValueError("Currency must be a 3-letter code")
    return {"destinations": [d for d in _ORDER if d in destinations], "mapping": mapping,
            "transforms": transforms, "size_map": {k.upper(): v for k, v in size_map.items()},
            "period": period, "currency": currency}


# ── Pipeline ─────────────────────────────────────────────────────────────────
def _identity(mapping: dict) -> list[str]:
    return [mapping[f] for f in ("sku", "name", "style") if f in mapping and mapping[f] not in DERIVED]


def _apply(table, decision: dict, rules_identity: list[str]):
    """Run exclusions and transforms. Returns (records, item rows before grouping, exclusions, conflicts, size codes)."""
    mapping, transforms = decision["mapping"], decision["transforms"]
    exclusions = [{"row": e["row"], "reason": e["reason"]} for e in table.exclusions]
    identity = _identity(mapping) or rules_identity
    records = []
    for number, record in zip(table.row_numbers, table.records, strict=True):
        if tx.is_summary_row(record, rules_identity or identity):
            exclusions.append({"row": number, "reason": "summary_row"})
        elif identity and all(tx._blank(record.get(c)) for c in identity):
            exclusions.append({"row": number, "reason": "no_item"})
        else:
            records.append(dict(record))
    codes = []
    if transforms["parse_variant"] and "description" in mapping:
        for record in records:
            colour, code = tx.parse_variant(record.get(mapping["description"]))
            codes.append(code)
            record["x_colour"], record["x_size_code"] = colour, code
            chosen = decision["size_map"].get(code) if code else None
            record["x_size"] = (chosen or None) if code in decision["size_map"] else normalize_size(code)
    conflicts, item_rows = 0, len(records)
    if transforms["group_pieces"]:
        colour = "x_colour" if transforms["parse_variant"] else mapping.get("color")
        size = "x_size_code" if transforms["parse_variant"] else mapping.get("size")
        sums = [mapping[f] for f in _SUMMED if f in mapping and mapping[f] not in DERIVED]
        location = mapping.get("warehouse") if mapping.get("warehouse") not in DERIVED else None
        records, conflicts = tx.group_pieces(records, brand=mapping.get("brand"), style=mapping["style"],
                                             colour=colour, size=size, location=location, sums=sums)
    return records, item_rows, exclusions, conflicts, tx.size_codes(codes)


def _preview(table, records, item_rows, decision, exclusions, conflicts) -> dict:
    mapping = decision["mapping"]
    sku_col, loc_col = mapping.get("sku") or mapping.get("name"), mapping.get("warehouse")
    return {
        "source_rows": item_rows,
        "excluded_rows": len(exclusions),
        "output_rows": len(records),
        "items": len({r.get(sku_col) for r in records}) if sku_col else 0,
        "locations": len({r.get(loc_col) for r in records}) if loc_col else 0,
        "conflicts": conflicts,
        "before": [{c.id: r.get(c.id) for c in table.columns} for r in table.records[:_PREVIEW_ROWS]],
        "after": [{f: r.get(c) for f, c in mapping.items()} for r in records[:_PREVIEW_ROWS]],
    }


def _missing(decision) -> dict:
    period = decision["period"] and (decision["period"]["start"], decision["period"]["end"])
    return {d: planner.missing_fields(d, decision["mapping"], period=period) for d in decision["destinations"]}


def _evaluate(table, decision, rules_identity) -> dict:
    records, item_rows, exclusions, conflicts, codes = _apply(table, decision, rules_identity)
    preview = _preview(table, records, item_rows, decision, exclusions, conflicts)
    return {"preview": preview, "exclusions": exclusions[:_LISTED_EXCLUSIONS], "size_codes": codes,
            "missing": _missing(decision)}


# ── Planning ─────────────────────────────────────────────────────────────────
def _rules_identity(table) -> list[str]:
    return _identity(planner.rules_mapping(table.columns))


async def _ai_suggestion(ai, ctx: AIContext, table):
    if ai is None:
        return None, "disabled"
    columns = [Column(id=c.id, label=(c.label or c.display_label)[:512], kind=c.kind) for c in table.columns]
    task = TaskRequest("import_plan", PlanInput(columns=columns, allowed_fields=list(planner.PLAN_FIELDS),
                                                row_count=len(table.records)))
    result = await ai.run(replace(ctx, task_name="import_plan"), task, rows=table.records[:3])
    return (result.value.model_dump() if result.state == "success" else None), result.state


async def _plan_one(ai, ctx: AIContext, secret: str, filename: str, content: bytes) -> dict:
    table, kind, lines = _discover(filename, content)
    mapping = planner.rules_mapping(table.columns)
    destinations, reason = planner.rules_destinations(mapping, table.columns)
    provenance = dict.fromkeys(mapping.values(), "alias")
    suggestion, ai_state = await _ai_suggestion(ai, ctx, table)
    source = "rules"
    if suggestion:
        mapping, destinations, added = planner.merge_ai(mapping, destinations, suggestion)
        provenance.update(added)
        source = "ai" if added or suggestion.get("destinations") else "rules"
        reason = None if destinations else (suggestion.get("reason") or reason)
    fashion = ctx.industry == IndustryCode.fashion
    parse = bool(fashion and "description" in mapping and "size" not in mapping)
    group = bool(parse and "style" in mapping and "sales" not in destinations)
    if parse:
        mapping.setdefault("size", "x_size")
        mapping.setdefault("color", "x_colour")
    if group:
        mapping["sku"] = "x_sku"
    period = tx.parse_period(lines)
    decision = _decision({"destinations": destinations, "mapping": mapping,
                          "transforms": {"parse_variant": parse, "group_pieces": group},
                          "period": period and {"start": period[0].isoformat(), "end": period[1].isoformat()}},
                         {c.id for c in table.columns})
    token = issue_analysis(secret, ctx.tenant_id, ctx.user_id, f"plan:{kind}", content, [table.id],
                           overrides={table.sheet: [table.header_start, table.header_end]})
    return {"filename": filename, "plan_token": token, "plan_source": source, "ai_state": ai_state,
            "table": {"sheet": table.sheet, "header_start": table.header_start, "header_end": table.header_end,
                      "rows_total": len(table.records)},
            "columns": _columns(table), "provenance": provenance, "decision": decision,
            "unusable_reason": reason, "warnings": table.warnings[:50],
            **_evaluate(table, decision, _rules_identity(table))}


async def plan_files(db, ai, ctx: AIContext, secret: str, files: list[tuple[str, bytes]]) -> dict:
    if not 1 <= len(files) <= MAX_FILES:
        raise ValueError(f"Upload between 1 and {MAX_FILES} files")
    async with db.session(str(ctx.tenant_id)) as session:
        await _member(session, ctx)
    out = []
    for index, (filename, content) in enumerate(files):
        try:
            slot = await _plan_one(ai, ctx, secret, filename, content)
        except (ValueError, UnicodeDecodeError) as exc:
            slot = {"filename": filename, "error": str(exc) or "This file could not be read"}
        out.append({"file_index": index, **slot})
    return {"files": out}


# ── Preview and confirm ──────────────────────────────────────────────────────
def _verified(ctx: AIContext, secret: str, filename: str, content: bytes, token: str, raw_decision):
    for kind in _KINDS:
        try:
            claims = verify_analysis(token, secret, ctx.tenant_id, ctx.user_id, f"plan:{kind}", content)
            break
        except ValueError:
            continue
    else:
        raise ValueError("File analysis is stale or invalid; analyze this file again")
    table, _, _ = _discover(filename, content, kind, claims["overrides"])
    if table.id not in claims["tables"]:
        raise ValueError("File analysis is stale or invalid; analyze this file again")
    return table, _decision(raw_decision, {c.id for c in table.columns})


async def preview_plan(db, ctx: AIContext, secret, filename, content, token, raw_decision) -> dict:
    async with db.session(str(ctx.tenant_id)) as session:
        await _member(session, ctx)
    table, decision = _verified(ctx, secret, filename, content, token, raw_decision)
    return {"decision": decision, **_evaluate(table, decision, _rules_identity(table))}


async def _write_period(session, ctx: AIContext, records, mapping, period, currency) -> dict:
    totals: dict[tuple[str, str], list[Decimal]] = defaultdict(lambda: [Decimal("0"), Decimal("0"), Decimal("0")])
    errors = []
    for number, record in enumerate(records, start=1):
        sku = str(record.get(mapping["sku"]) or "").strip()
        units = _to_decimal(record.get(mapping["quantity"]))
        if not sku or units is None or units < 0:
            errors.append(f"Item {number}: missing SKU or a non-negative quantity")
            continue
        location = str(record.get(mapping.get("warehouse", "")) or "default").strip() or "default"
        bucket = totals[(sku, location)]
        bucket[0] += units
        bucket[1] += _to_decimal(record.get(mapping.get("revenue", ""))) or Decimal("0")
        bucket[2] += _to_decimal(record.get(mapping.get("cogs", ""))) or Decimal("0")
    if errors:
        raise ValueError("; ".join(errors[:5]))
    product_id = await _ensure_import_product(session, ctx.tenant_id, ctx.industry)
    sku_map = await _load_sku_map(session, ctx.tenant_id)
    currency = currency or await _workspace_currency(session, ctx.tenant_id)
    for (sku, location), (units, net, cost) in totals.items():
        sku_id = await _get_or_create_sku(session, ctx.tenant_id, ctx.industry, sku, sku_map, product_id,
                                          currency=currency)
        await session.execute(text("""INSERT INTO sku_period_sales
            (tenant_id,sku_id,location,period_start,period_end,units,net_value,cost_value,source)
            VALUES (:t,:s,:l,:a,:b,:u,:n,:c,'smart_import')
            ON CONFLICT (tenant_id,sku_id,location,period_start,period_end) DO UPDATE SET
            units=EXCLUDED.units, net_value=EXCLUDED.net_value, cost_value=EXCLUDED.cost_value,
            updated_at=clock_timestamp()"""),
            {"t": ctx.tenant_id, "s": sku_id, "l": location, "a": date.fromisoformat(period["start"]),
             "b": date.fromisoformat(period["end"]), "u": units,
             "n": net if "revenue" in mapping else None, "c": cost if "cogs" in mapping else None})
    return {"period_rows": len(totals), "rows_imported": len(totals)}


async def confirm_plan(db, ctx: AIContext, secret, filename, content, token, raw_decision) -> dict:
    table, decision = _verified(ctx, secret, filename, content, token, raw_decision)
    if not decision["destinations"]:
        raise ValueError("Choose at least one destination for this file")
    missing = {d: m for d, m in _missing(decision).items() if m}
    if missing:
        raise ValueError("Map required fields first: " + "; ".join(f"{d}: {', '.join(m)}" for d, m in missing.items()))
    records, _, exclusions, _, _ = _apply(table, decision, _rules_identity(table))
    if not records:
        raise ValueError("No item rows left to import")
    headers = [c.id for c in table.columns] + list(DERIVED)
    results = {}
    async with db.session(str(ctx.tenant_id)) as session:
        await _member(session, ctx, writing=True)
        for destination in decision["destinations"]:
            fields = planner.DESTINATION_FIELDS[destination]
            mapping = {f: c for f, c in decision["mapping"].items() if f in fields}
            if destination == "period_sales":
                results[destination] = await _write_period(session, ctx, records, mapping, decision["period"],
                                                            decision["currency"])
                continue
            stats = await import_rows(db=_BoundDB(session), tenant_id=ctx.tenant_id, industry=ctx.industry,
                                      kind=destination, headers=headers, records=records, column_mapping=mapping,
                                      currency=decision["currency"])
            if stats["rows_skipped"]:
                raise ValueError(f"{destination}: {stats['rows_skipped']} rows did not validate — "
                                 + "; ".join(stats["errors"][:5]))
            results[destination] = stats
        await audit.record(session, tenant_id=ctx.tenant_id, user_id=ctx.user_id, industry=ctx.industry,
                           action="import.plan_confirmed", entity_type="import", strict=True,
                           new_value={"destinations": decision["destinations"], "rows": len(records),
                                      "excluded": len(exclusions), "transforms": decision["transforms"]})
    return {"destinations": results, "rows_excluded": len(exclusions)}
