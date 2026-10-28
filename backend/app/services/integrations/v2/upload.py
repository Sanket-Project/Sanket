"""Authenticated preview/confirmation boundary for supported retail V2 files."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from sqlalchemy import text

from app.services.integrations.v2.catalog import ValidationError
from app.services.integrations.v2.contracts import (
    SCHEMA_INVENTORY,
    SCHEMA_RETURNS,
    SCHEMA_SALES,
    detect_v2_schema,
    parse_v2_csv,
)
from app.services.integrations.v2.event_registry import EventRegistryService
from app.services.integrations.v2.inventory import validate_inventory_row
from app.services.integrations.v2.sales_returns import validate_return_row, validate_sale_row

SUPPORTED_SCHEMAS = {SCHEMA_INVENTORY, SCHEMA_SALES, SCHEMA_RETURNS}


def _token(secret: str, tenant_id: uuid.UUID, user_id: uuid.UUID, schema: str, content: bytes) -> str:
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "purpose": "retail_v2_preview",
            "tenant": str(tenant_id),
            "actor": str(user_id),
            "schema": schema,
            "digest": hashlib.sha256(content).hexdigest(),
            "iat": now,
            "exp": now + timedelta(minutes=30),
        },
        secret,
        algorithm="HS256",
    )


def _verify(token: str, secret: str, tenant_id: uuid.UUID, user_id: uuid.UUID, schema: str, content: bytes) -> None:
    try:
        claims = jwt.decode(token, secret, algorithms=["HS256"], options={"require": ["exp", "iat"]})
        expected = {
            "purpose": "retail_v2_preview",
            "tenant": str(tenant_id),
            "actor": str(user_id),
            "schema": schema,
            "digest": hashlib.sha256(content).hexdigest(),
        }
        if any(claims.get(key) != value for key, value in expected.items()):
            raise ValueError
    except (jwt.PyJWTError, ValueError, TypeError):
        raise ValueError("V2 preview is stale or invalid; preview this file again") from None


def _validated(schema: str, rows: list[dict[str, Any]]) -> tuple[list[Any], list[dict[str, Any]]]:
    validator = {
        SCHEMA_INVENTORY: validate_inventory_row,
        SCHEMA_SALES: validate_sale_row,
        SCHEMA_RETURNS: validate_return_row,
    }[schema]
    valid, errors = [], []
    for row_number, row in enumerate(rows, start=2):
        if row.get("schema_version") != schema:
            errors.append(
                {
                    "row": row_number,
                    "code": "SCHEMA_VERSION_MISMATCH",
                    "message": f"schema_version must be {schema}",
                }
            )
            continue
        try:
            valid.append(validator(row))
        except ValidationError as exc:
            errors.append({"row": row_number, "code": exc.code, "message": exc.message})
    return valid, errors


def preview(content: bytes, tenant_id: uuid.UUID, user_id: uuid.UUID, secret: str) -> dict[str, Any]:
    headers, rows = parse_v2_csv(content)
    schema = detect_v2_schema(headers, rows[0] if rows else None)
    if schema not in SUPPORTED_SCHEMAS:
        raise ValueError("This V2 file type is not enabled for import")
    _, errors = _validated(schema, rows)
    return {
        "schema": schema,
        "row_count": len(rows),
        "headers": headers,
        "errors": errors,
        "can_confirm": not errors,
        "preview_token": _token(secret, tenant_id, user_id, schema, content),
    }


async def validate_tenant_references(db, tenant_id: uuid.UUID, preview_result: dict[str, Any], content: bytes) -> dict[str, Any]:
    headers, rows = parse_v2_csv(content)
    schema = preview_result["schema"]
    values, errors = _validated(schema, rows)
    if not values:
        preview_result["errors"] = errors
        preview_result["can_confirm"] = False
        return preview_result
    async with db.session(str(tenant_id)) as session:
        skus = {
            str(code).lower()
            for code in (
                await session.scalars(
                    text("SELECT sku_code FROM skus WHERE tenant_id=:tenant"),
                    {"tenant": tenant_id},
                )
            ).all()
        }
        locations = {
            str(code).lower()
            for code in (
                await session.scalars(
                    text("SELECT code FROM locations WHERE tenant_id=:tenant"),
                    {"tenant": tenant_id},
                )
            ).all()
        }
    reference_errors = []
    for row_number, value in enumerate(values, start=2):
        if value.sku_code.lower() not in skus:
            reference_errors.append({"row": row_number, "code": "UNKNOWN_SKU", "message": f"SKU '{value.sku_code}' is not registered for this tenant"})
        if value.location_code.lower() not in locations:
            reference_errors.append({"row": row_number, "code": "UNKNOWN_LOCATION", "message": f"Location '{value.location_code}' is not registered for this tenant"})
        if schema == SCHEMA_SALES and value.fulfillment_location_code.lower() not in locations:
            reference_errors.append({"row": row_number, "code": "UNKNOWN_FULFILLMENT_LOCATION", "message": f"Fulfillment location '{value.fulfillment_location_code}' is not registered for this tenant"})
    preview_result["errors"] = [*errors, *reference_errors]
    preview_result["can_confirm"] = not preview_result["errors"]
    return preview_result


async def confirm(
    db,
    content: bytes,
    preview_token: str,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    industry,
    secret: str,
    validate_references: bool = False,
) -> dict[str, Any]:
    headers, rows = parse_v2_csv(content)
    schema = detect_v2_schema(headers, rows[0] if rows else None)
    if schema not in SUPPORTED_SCHEMAS:
        raise ValueError("This V2 file type is not enabled for import")
    _verify(preview_token, secret, tenant_id, user_id, schema, content)
    values, errors = _validated(schema, rows)
    if errors:
        raise ValueError("V2 validation failed; review all errors before confirming")
    if validate_references:
        reference_preview = await validate_tenant_references(
            db,
            tenant_id,
            {"schema": schema},
            content,
        )
        if reference_preview["errors"]:
            raise ValueError("V2 reference validation failed: " + "; ".join(error["message"] for error in reference_preview["errors"]))

    service = EventRegistryService()
    async with db.session(str(tenant_id)) as session:
        if schema == SCHEMA_SALES:
            stats = await service.post_sales_group(session, tenant_id, values)
            projected = 0
            for value in values:
                sale = (
                    await session.execute(
                        text("""
                            SELECT e.id, e.transaction_at, e.sku_code, e.location_code,
                                   e.channel_code, e.quantity_sold, e.gross_sales_ex_tax,
                                   e.net_sale_ex_tax, s.id AS sku_id
                            FROM v2_sales_events e
                            JOIN skus s ON s.tenant_id=e.tenant_id AND lower(s.sku_code)=lower(e.sku_code)
                            WHERE e.tenant_id=:tenant AND e.source_system=:source
                              AND e.transaction_id=:transaction AND e.order_line_id=:line
                            FOR UPDATE OF e
                        """),
                        {
                            "tenant": tenant_id,
                            "source": value.source_system,
                            "transaction": value.transaction_id,
                            "line": value.order_line_id,
                        },
                    )
                ).mappings().one()
                record_key = f"v2:sale:{sale['id']}"
                exists = await session.scalar(
                    text("SELECT 1 FROM historical_sales WHERE tenant_id=:tenant AND record_key=:key LIMIT 1"),
                    {"tenant": tenant_id, "key": record_key},
                )
                if exists:
                    continue
                await session.execute(
                    text("""
                        INSERT INTO historical_sales (
                            id, tenant_id, sku_id, industry, sale_time, channel, region,
                            units_sold, gross_revenue, net_revenue, returns, promo_flag,
                            markdown_pct, in_stock, record_key, location, metadata
                        ) VALUES (
                            gen_random_uuid(), :tenant, :sku_id, :industry, :sale_time, :channel, NULL,
                            :units, :gross, :net, 0, false, NULL, NULL, :record_key, :location,
                            CAST(:metadata AS jsonb)
                        )
                    """),
                    {
                        "tenant": tenant_id,
                        "sku_id": sale["sku_id"],
                        "industry": industry.value if hasattr(industry, "value") else industry,
                        "sale_time": sale["transaction_at"],
                        "channel": sale["channel_code"],
                        "units": sale["quantity_sold"],
                        "gross": sale["gross_sales_ex_tax"],
                        "net": sale["net_sale_ex_tax"],
                        "record_key": record_key,
                        "location": sale["location_code"],
                        "metadata": json.dumps({"source": "retail_v2", "event_kind": "sale", "event_id": str(sale["id"])}),
                    },
                )
                projected += 1
            stats["read_model_inserted"] = projected
        elif schema == SCHEMA_RETURNS:
            results = [await service.post_return_event(session, tenant_id, value) for value in values]
            stats = {"inserted": sum(result["status"] != "skipped" for result in results), "skipped": sum(result["status"] == "skipped" for result in results)}
            for value, result in zip(values, results):
                if result["status"] != "approved":
                    continue
                await session.execute(
                    text("""
                        INSERT INTO historical_sales (
                            id, tenant_id, sku_id, industry, sale_time, channel, region,
                            units_sold, gross_revenue, net_revenue, returns, promo_flag,
                            markdown_pct, in_stock, record_key, location, metadata
                        )
                        SELECT gen_random_uuid(), r.tenant_id, s.id, s.industry,
                               r.return_at, e.channel_code, NULL, 0, 0,
                               -r.return_value_ex_tax, r.returns, false, NULL, NULL,
                               'v2:return:' || r.id::text, r.location_code,
                               jsonb_build_object('source', 'retail_v2', 'event_kind', 'return',
                                                  'event_id', r.id::text, 'sale_event_id', e.id::text)
                        FROM v2_return_events r
                        JOIN v2_sales_events e ON e.tenant_id=r.tenant_id AND e.id=r.sale_event_id
                        JOIN skus s ON s.tenant_id=e.tenant_id AND lower(s.sku_code)=lower(e.sku_code)
                        WHERE r.tenant_id=:tenant AND r.id=:event AND r.status='approved'
                          AND NOT EXISTS (
                              SELECT 1 FROM historical_sales h WHERE h.tenant_id=r.tenant_id
                                AND h.record_key='v2:return:' || r.id::text
                          )
                    """),
                    {
                        "tenant": tenant_id,
                        "event": uuid.UUID(result["target_id"]),
                    },
                )
        else:
            inserted = 0
            skipped = 0
            for value in values:
                existing = (
                    await session.execute(
                        text("""
                            SELECT as_of, on_hand_qty, reserved_qty, damaged_qty, quarantine_qty,
                                   in_transit_qty, open_po_qty, source_system, count_reference,
                                   reported_stock_value_ex_tax, currency
                            FROM v2_inventory_snapshots
                            WHERE tenant_id=:tenant AND snapshot_id=:snapshot
                              AND sku_code=:sku AND location_code=:location
                        """),
                        {
                            "tenant": tenant_id,
                            "snapshot": value.snapshot_id,
                            "sku": value.sku_code,
                            "location": value.location_code,
                        },
                    )
                ).mappings().first()
                if existing is not None:
                    same = all(
                        existing[field] == expected
                        for field, expected in {
                            "as_of": value.as_of,
                            "on_hand_qty": value.on_hand_qty,
                            "reserved_qty": value.reserved_qty,
                            "damaged_qty": value.damaged_qty,
                            "quarantine_qty": value.quarantine_qty,
                            "in_transit_qty": value.in_transit_qty,
                            "open_po_qty": value.open_po_qty,
                            "source_system": value.source_system,
                            "count_reference": value.count_reference,
                            "reported_stock_value_ex_tax": value.reported_stock_value_ex_tax,
                            "currency": value.currency,
                        }.items()
                    )
                    if same:
                        skipped += 1
                        continue
                    raise ValueError("Inventory snapshot identity conflicts with an existing payload")
                latest = await session.scalar(
                    text("""
                        SELECT max(as_of) FROM v2_inventory_snapshots
                        WHERE tenant_id=:tenant AND sku_code=:sku AND location_code=:location
                    """),
                    {"tenant": tenant_id, "sku": value.sku_code, "location": value.location_code},
                )
                if latest is not None and value.as_of <= latest:
                    raise ValueError("Inventory snapshot is stale for this SKU and location")
                insert_result = await session.execute(
                    text("""
                        INSERT INTO v2_inventory_snapshots (
                            tenant_id, snapshot_id, as_of, sku_code, location_code, on_hand_qty,
                            reserved_qty, damaged_qty, quarantine_qty, in_transit_qty, open_po_qty,
                            source_system, count_reference, reported_stock_value_ex_tax, currency
                        ) VALUES (
                            :tenant, :snapshot, :as_of, :sku, :location, :on_hand,
                            :reserved, :damaged, :quarantine, :transit, :open_po,
                            :source, :reference, :value, :currency
                        )
                        ON CONFLICT (tenant_id, snapshot_id, sku_code, location_code) DO NOTHING
                    """),
                    {
                        "tenant": tenant_id,
                        "snapshot": value.snapshot_id,
                        "as_of": value.as_of,
                        "sku": value.sku_code,
                        "location": value.location_code,
                        "on_hand": value.on_hand_qty,
                        "reserved": value.reserved_qty,
                        "damaged": value.damaged_qty,
                        "quarantine": value.quarantine_qty,
                        "transit": value.in_transit_qty,
                        "open_po": value.open_po_qty,
                        "source": value.source_system,
                        "reference": value.count_reference,
                        "value": value.reported_stock_value_ex_tax,
                        "currency": value.currency,
                    },
                )
                if insert_result.rowcount == 0:
                    conflict = (
                        await session.execute(
                            text("""
                                SELECT as_of, on_hand_qty, reserved_qty, damaged_qty, quarantine_qty,
                                       in_transit_qty, open_po_qty, source_system, count_reference,
                                       reported_stock_value_ex_tax, currency
                                FROM v2_inventory_snapshots
                                WHERE tenant_id=:tenant AND snapshot_id=:snapshot
                                  AND sku_code=:sku AND location_code=:location
                            """),
                            {
                                "tenant": tenant_id,
                                "snapshot": value.snapshot_id,
                                "sku": value.sku_code,
                                "location": value.location_code,
                            },
                        )
                    ).mappings().one()
                    if any(
                        conflict[field] != expected
                        for field, expected in {
                            "as_of": value.as_of,
                            "on_hand_qty": value.on_hand_qty,
                            "reserved_qty": value.reserved_qty,
                            "damaged_qty": value.damaged_qty,
                            "quarantine_qty": value.quarantine_qty,
                            "in_transit_qty": value.in_transit_qty,
                            "open_po_qty": value.open_po_qty,
                            "source_system": value.source_system,
                            "count_reference": value.count_reference,
                            "reported_stock_value_ex_tax": value.reported_stock_value_ex_tax,
                            "currency": value.currency,
                        }.items()
                    ):
                        raise ValueError("Inventory snapshot identity conflicts with an existing payload")
                    skipped += 1
                    continue
                inserted += 1
            stats = {"inserted": inserted, "skipped": skipped}
        from app.services import audit

        await audit.record(
            session,
            tenant_id=tenant_id,
            user_id=user_id,
            industry=industry,
            action="retail_v2.import.confirmed",
            entity_type="retail_v2_import",
            entity_id=str(uuid.uuid4()),
            new_value={"schema": schema, "rows": len(values), **stats},
            strict=True,
        )
        await session.commit()
    return {"schema": schema, "rows": len(values), **stats}
