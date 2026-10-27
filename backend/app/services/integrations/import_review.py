"""One analysis/confirmation boundary shared by onboarding and integrations."""
from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import replace

from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from app.models.tenant import User
from app.services import audit
from app.services.integrations.file_import import import_rows, map_inventory_row, map_product_row, map_sales_row
from app.services.integrations.import_layout import discover_tables, fields_for, validate_mapping
from app.services.integrations.import_dates import date_preview, resolve_dates
from app.services.integrations.import_profiles import issue_analysis, load_profile, save_profile, verify_analysis
from app.services.llm.contracts import Column, TaskInput
from app.services.llm.policy import AIContext


async def _member(session, ctx, *, writing=False):
    query = select(User).where(User.id == ctx.user_id, User.tenant_id == ctx.tenant_id, User.is_active.is_(True))
    user = await session.scalar(query.with_for_update() if writing else query)
    if user is None or (writing and user.role not in {"owner", "admin", "analyst"}):
        raise ValueError("Current workspace membership does not permit this import")
    return user


def _compatible(profile, table):
    if profile["options"].get("disabled") is True:
        return False
    current = {c.id: c.kind for c in table.columns}
    for key, previous in profile["column_types"].items():
        actual = current.get(key)
        if previous != actual and {previous, actual} - {"integer", "decimal"}:
            return False
    return set(profile["mapping"].values()) <= set(current)


async def analyze_import(db, ai, ctx: AIContext, secret, filename, content, kind, *, header_overrides=None, suggest_table=None):
    async with db.session(str(ctx.tenant_id)) as session:
        await _member(session, ctx)
    tables = await run_in_threadpool(discover_tables, filename, content, kind, header_overrides=header_overrides)
    if suggest_table is not None and suggest_table not in {t.id for t in tables}:
        raise ValueError("Unknown table for mapping suggestions")
    target_table = suggest_table or tables[0].id
    output, revisions = [], {}
    for table in tables:
        async with db.session(str(ctx.tenant_id)) as session:
            profile = await load_profile(session, ctx.tenant_id, kind, table.fingerprint)
        revisions[table.id] = profile["revision"] if profile else 0
        mapping = dict(table.mapping)
        confidence = {c.id: "high" if c.id in mapping.values() else "unknown" for c in table.columns}
        provenance = {c.id: "alias" if c.id in mapping.values() else "manual" for c in table.columns}
        source, ai_state = "alias", "disabled"
        if profile and _compatible(profile, table):
            mapping = dict(profile["mapping"])
            source = "saved"
            provenance.update({c.id: "saved" if c.id in mapping.values() else "manual" for c in table.columns})
        elif ai is not None and table.id == target_table and any(c.label and c.id not in mapping.values() for c in table.columns):
            task = TaskInput(columns=[Column(id=c.id, label=c.label or c.display_label, kind=c.kind) for c in table.columns],
                             allowed_fields=list(fields_for(kind)))
            result = await ai.run(replace(ctx, task_name="import_mapping"), task, rows=table.records[:3])
            ai_state = result.state
            if result.state == "success":
                for suggestion in result.value.selections:
                    # A suggestion may fill a gap, never replace a saved/deterministic assignment.
                    if suggestion.field and suggestion.field not in mapping and suggestion.column_id not in mapping.values():
                        mapping[suggestion.field] = suggestion.column_id
                        confidence[suggestion.column_id] = suggestion.confidence
                        provenance[suggestion.column_id] = "ai"
                source = "ai" if "ai" in provenance.values() else "alias"
        item = table.preview()
        item.update(mapping=mapping, mapping_source=source, confidence=confidence, provenance=provenance,
                    ai_state=ai_state, profile_revision=revisions[table.id],
                    warning_count=len(table.warnings), warnings=table.warnings[:100])
        item["saved_options"] = profile["options"] if profile and source == "saved" else {}
        if kind == "sales":
            reviews = {c.id: date_preview(table.records, c.id, table.row_numbers) for c in table.columns}
            item["date_reviews"] = {key: values[:50] for key, values in reviews.items() if values}
            item["date_review_counts"] = {key: len(values) for key, values in reviews.items() if values}
        if profile and source != "saved":
            item["warnings"].append("Saved format is disabled or has incompatible data types; review this mapping")
        output.append(item)
    top = output[0]
    # Legacy fields are retained for clients that have not adopted physical IDs yet.
    names = {c["id"]: c["display_label"] for c in top["columns"]}
    return {"tables": output, "fields": list(fields_for(kind)),
            "headers": list(names.values()),
            "suggested_mapping": {k: names[v] for k, v in top["mapping"].items()},
            "sample_rows": [{names[k]: v for k, v in row.items()} for row in top["sample_rows"]],
            "analysis_token": issue_analysis(secret, ctx.tenant_id, ctx.user_id, kind, content,
                                              [t.id for t in tables], overrides=header_overrides,
                                              profile_revisions=revisions)}


class _BoundDB:
    def __init__(self, session):
        self.session_obj = session

    @asynccontextmanager
    async def session(self, tenant):
        yield self.session_obj


async def confirm_import(db, ctx: AIContext, secret, filename, content, kind, token, selections, *,
                         remember=False, identity="transaction", currency=None):
    claims = verify_analysis(token, secret, ctx.tenant_id, ctx.user_id, kind, content)
    if (not isinstance(selections, list) or not 1 <= len(selections) <= 20
            or any(not isinstance(s, dict) for s in selections)):
        raise ValueError("Select one or more data tables")
    ids = [s.get("id") for s in selections]
    if len(set(ids)) != len(ids) or not set(ids) <= set(claims["tables"]):
        raise ValueError("Selection differs from file analysis")
    if identity not in {"transaction", "period"}:
        raise ValueError("Invalid sales identity mode")
    tables = {t.id: t for t in await run_in_threadpool(discover_tables, filename, content, kind,
                                                      header_overrides=claims["overrides"])}
    validated = []
    mapper = {"sales": map_sales_row, "inventory": map_inventory_row, "products": map_product_row}[kind]
    for selection in selections:
        if set(selection) - {"id", "mapping", "include_review_rows", "exclude_rows", "date_order"}:
            raise ValueError("Unknown confirmation fields")
        table = tables[selection["id"]]
        mapping = validate_mapping(kind, selection.get("mapping", {}), [c.id for c in table.columns])
        includes, excludes = selection.get("include_review_rows", []), selection.get("exclude_rows", [])
        if not isinstance(includes, list) or not isinstance(excludes, list) or any(type(n) is not int for n in includes + excludes):
            raise ValueError("Invalid row review")
        if set(includes) & set(excludes) or not set(excludes) <= set(table.row_numbers) or not set(includes) <= set(table.review_rows):
            raise ValueError("Unknown or conflicting row review")
        if set(table.review_rows) - set(includes) - set(excludes):
            raise ValueError("Review ambiguous rows before importing")
        records = [record for number, record in zip(table.row_numbers, table.records, strict=True) if number not in excludes]
        if kind == "sales":
            records = resolve_dates(records, mapping["timestamp"], selection.get("date_order"))
        if not records:
            raise ValueError("No accepted detail rows selected")
        for record in records:
            mapper(record, mapping)  # All selected tables must validate before opening the write transaction.
        validated.append((table, mapping, records, selection.get("date_order")))
    total = {}
    async with db.session(str(ctx.tenant_id)) as session:
        await _member(session, ctx, writing=True)
        for table, mapping, records, date_order in validated:
            stats = await import_rows(db=_BoundDB(session), tenant_id=ctx.tenant_id, industry=ctx.industry,
                                      kind=kind, headers=[c.id for c in table.columns], records=records,
                                      column_mapping=mapping, identity=identity, currency=currency)
            if stats["rows_imported"] + stats.get("rows_unchanged", 0) <= 0:
                raise ValueError("No rows accepted; saved format was not trusted")
            if stats["rows_skipped"]:
                raise ValueError("Selected rows did not all validate; review the source before importing")
            if remember:
                await save_profile(session, ctx.tenant_id, kind, table.fingerprint, mapping,
                                   {c.id: c.kind for c in table.columns}, expected_revision=claims["profiles"][table.id],
                                   options={"identity": identity, "currency": currency, "date_order": date_order})
            for key, value in stats.items():
                if type(value) is int:
                    total[key] = total.get(key, 0) + value
                elif isinstance(value, list):
                    total.setdefault(key, []).extend(value)
                else:
                    total[key] = value
        await audit.record(session, tenant_id=ctx.tenant_id, user_id=ctx.user_id, industry=ctx.industry,
                           action="import.confirmed", entity_type="import", strict=True,
                           new_value={"kind": kind, "tables": len(validated), "remembered": remember,
                                      "rows": total["rows_imported"]})
    return total
