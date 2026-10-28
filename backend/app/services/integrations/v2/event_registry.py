"""Event Identity Registry, Deduplication, and Posting Groups (P0-06).

Enforces:
- Unpartitioned unique event identity registry: (tenant_id, source_system, entity_kind, external_event_id, event_line_id).
- Exact payload replay -> idempotent return of previous outcome (0 new facts).
- Conflicting payload under same event ID -> raises EVENT_PAYLOAD_CONFLICT.
- Atomic posting groups.
- Linked return concurrency locks and cumulative sold quantity limits.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import replace
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.integrations.v2.catalog import ValidationError
from app.services.integrations.v2.sales_returns import ValidatedReturn, ValidatedSale


def _json_serial(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        return str(obj)
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if isinstance(obj, uuid.UUID):
        return str(obj)
    return str(obj)


def compute_payload_hash(payload: Any) -> str:
    """Compute SHA-256 over deterministic sorted JSON."""
    if hasattr(payload, "__dict__"):
        data = payload.__dict__
    elif isinstance(payload, dict):
        data = payload
    else:
        data = {"value": payload}
    canonical_json = json.dumps(data, sort_keys=True, default=_json_serial)
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


class EventRegistryService:
    async def check_and_register(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        source_system: str,
        entity_kind: str,
        external_event_id: str,
        event_line_id: str,
        payload: Any,
    ) -> tuple[bool, uuid.UUID]:
        """Check if event identity exists.

        Returns (is_duplicate, target_id).
        If exact duplicate, returns (True, existing_target_id).
        If conflicting duplicate, raises ValidationError(EVENT_PAYLOAD_CONFLICT).
        If new, inserts registry row and returns (False, new_target_id).
        """
        payload_hash = compute_payload_hash(payload)
        line_id = event_line_id or ""

        new_target_id = uuid.uuid4()
        insert_query = text("""
            INSERT INTO event_identity_registry (
                tenant_id, source_system, entity_kind, external_event_id, event_line_id, payload_hash, target_id, status
            ) VALUES (
                :t, :s, :k, :ev, :line, :hash, :target, 'committed'
            ) ON CONFLICT (tenant_id, source_system, entity_kind, external_event_id, event_line_id)
              DO NOTHING
        """)
        result = await session.execute(
            insert_query,
            {
                "t": tenant_id,
                "s": source_system,
                "k": entity_kind,
                "ev": external_event_id,
                "line": line_id,
                "hash": payload_hash,
                "target": new_target_id,
            },
        )
        if result.rowcount == 1:
            return False, new_target_id

        row = (
            await session.execute(
                text("""
                    SELECT payload_hash, target_id
                    FROM event_identity_registry
                    WHERE tenant_id = :t AND source_system = :s AND entity_kind = :k
                      AND external_event_id = :ev AND event_line_id = :line
                """),
                {"t": tenant_id, "s": source_system, "k": entity_kind, "ev": external_event_id, "line": line_id},
            )
        ).mappings().one()
        if row["payload_hash"] == payload_hash:
            return True, row["target_id"]
        raise ValidationError(
            f"Conflicting payload under event identity {source_system}/{entity_kind}/{external_event_id}/{line_id}",
            code="EVENT_PAYLOAD_CONFLICT",
        )

    async def post_sales_group(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        sales: list[ValidatedSale],
    ) -> dict[str, int]:
        """Post a group of validated sales atomically, registering each in the event identity registry."""
        inserted = 0
        skipped = 0

        async with session.begin_nested():
            for s in sales:
                is_dup, target_id = await self.check_and_register(
                    session=session,
                    tenant_id=tenant_id,
                    source_system=s.source_system,
                    entity_kind="sale",
                    external_event_id=s.transaction_id,
                    event_line_id=s.order_line_id,
                    payload=s,
                )
                if is_dup:
                    skipped += 1
                    continue

                insert_sale = text("""
                    INSERT INTO v2_sales_events (
                        id, tenant_id, source_system, transaction_id, order_id, order_line_id,
                        transaction_at, sku_code, location_code, fulfillment_location_code, channel_code,
                        quantity_sold, unit_price_ex_tax, mrp_incl_tax, discount_ex_tax, gross_sales_ex_tax,
                        net_sale_ex_tax, tax_code, tax_rate_pct, tax_amount, currency, order_status,
                        invoice_number, place_of_supply_state_code, payment_method, payment_reference, payment_amount
                    ) VALUES (
                        :id, :t, :s, :txn, :ord, :line,
                        :txn_at, :sku, :loc, :fulfill_loc, :chan,
                        :qty, :unit_price, :mrp, :disc, :gross,
                        :net, :tax_code, :tax_rate, :tax_amt, :curr, :status,
                        :inv, :pos_state, :pay_method, :pay_ref, :pay_amt
                    )
                """)
                await session.execute(
                    insert_sale,
                    {
                        "id": target_id,
                        "t": tenant_id,
                        "s": s.source_system,
                        "txn": s.transaction_id,
                        "ord": s.order_id,
                        "line": s.order_line_id,
                        "txn_at": s.transaction_at,
                        "sku": s.sku_code,
                        "loc": s.location_code,
                        "fulfill_loc": s.fulfillment_location_code,
                        "chan": s.channel_code,
                        "qty": s.quantity_sold,
                        "unit_price": s.unit_price_ex_tax,
                        "mrp": s.mrp_incl_tax,
                        "disc": s.discount_ex_tax,
                        "gross": s.gross_sales_ex_tax,
                        "net": s.net_sale_ex_tax,
                        "tax_code": s.tax_code,
                        "tax_rate": s.tax_rate_pct,
                        "tax_amt": s.tax_amount,
                        "curr": s.currency,
                        "status": s.order_status,
                        "inv": s.invoice_number,
                        "pos_state": s.place_of_supply_state_code,
                        "pay_method": s.payment_method,
                        "pay_ref": s.payment_reference,
                        "pay_amt": s.payment_amount,
                    },
                )
                inserted += 1

        return {"inserted": inserted, "skipped": skipped}

    async def post_return_event(
        self,
        session: AsyncSession,
        tenant_id: uuid.UUID,
        ret: ValidatedReturn,
    ) -> dict[str, Any]:
        """Post a return event with concurrency lock on original sale and cumulative returns cap."""
        async with session.begin_nested():
            registry = (
                await session.execute(
                    text("""
                        SELECT payload_hash, target_id
                        FROM event_identity_registry
                        WHERE tenant_id=:t AND source_system=:s AND entity_kind='return'
                          AND external_event_id=:event AND event_line_id=:line
                        FOR UPDATE
                    """),
                    {
                        "t": tenant_id,
                        "s": ret.source_system,
                        "event": ret.return_id,
                        "line": ret.return_line_id,
                    },
                )
            ).mappings().first()
            existing_return = None
            lifecycle_transition = False
            if registry is not None:
                existing_return = (
                    await session.execute(
                        text("SELECT status FROM v2_return_events WHERE id=:id AND tenant_id=:t"),
                        {"id": registry["target_id"], "t": tenant_id},
                    )
                ).mappings().first()
                incoming_hash = compute_payload_hash(ret)
                if registry["payload_hash"] == incoming_hash:
                    if existing_return and existing_return["status"] == "approved":
                        return {"status": "skipped", "target_id": str(registry["target_id"])}
                    lifecycle_transition = bool(
                        existing_return
                        and existing_return["status"] == "draft"
                        and ret.status == "approved"
                    )
                    if not lifecycle_transition:
                        return {"status": "skipped", "target_id": str(registry["target_id"])}
                elif existing_return and existing_return["status"] == "draft" and ret.status == "approved":
                    if compute_payload_hash(replace(ret, status="draft")) != registry["payload_hash"]:
                        raise ValidationError(
                            f"Conflicting payload under event identity {ret.source_system}/return/{ret.return_id}/{ret.return_line_id}",
                            code="EVENT_PAYLOAD_CONFLICT",
                        )
                    lifecycle_transition = True
                else:
                    raise ValidationError(
                        f"Conflicting payload under event identity {ret.source_system}/return/{ret.return_id}/{ret.return_line_id}",
                        code="EVENT_PAYLOAD_CONFLICT",
                    )
                target_id = registry["target_id"]
            else:
                is_duplicate, target_id = await self.check_and_register(
                    session=session,
                    tenant_id=tenant_id,
                    source_system=ret.source_system,
                    entity_kind="return",
                    external_event_id=ret.return_id,
                    event_line_id=ret.return_line_id,
                    payload=ret,
                )
                if is_duplicate:
                    return {"status": "skipped", "target_id": str(target_id)}

            # Lock the original sale event FOR UPDATE.
            orig_query = text("""
            SELECT id, quantity_sold, cumulative_returned_qty, sku_code, currency,
                   net_sale_ex_tax, tax_amount, transaction_at
            FROM v2_sales_events
            WHERE tenant_id = :t
              AND source_system = :s
              AND transaction_id = :tx
              AND order_line_id = :line
            FOR UPDATE
            """)
            orig_row = (
                await session.execute(
                    orig_query,
                    {
                        "t": tenant_id,
                        "s": ret.original_source_system,
                        "tx": ret.original_transaction_id,
                        "line": ret.original_order_line_id,
                    },
                )
            ).mappings().first()

            if orig_row is None:
                raise ValidationError(
                    f"Original transaction '{ret.original_transaction_id}' line '{ret.original_order_line_id}' not found",
                    code="ORIGINAL_NOT_FOUND",
                )
            if ret.sku_code != orig_row["sku_code"]:
                raise ValidationError("Return SKU does not match the original sale", code="RETURN_SKU_MISMATCH")
            if ret.currency != orig_row["currency"]:
                raise ValidationError("Return currency does not match the original sale", code="RETURN_CURRENCY_MISMATCH")
            if ret.return_at < orig_row["transaction_at"]:
                raise ValidationError("Return cannot precede the original sale", code="RETURN_DATE_INVALID")

            totals = (
                await session.execute(
                    text("""
                    SELECT COALESCE(SUM(returns), 0) AS qty,
                           COALESCE(SUM(return_value_ex_tax), 0) AS value,
                           COALESCE(SUM(tax_amount), 0) AS tax
                    FROM v2_return_events
                    WHERE tenant_id = :t AND sale_event_id = :sale_id AND status = 'approved'
                """),
                    {"t": tenant_id, "sale_id": orig_row["id"]},
                )
            ).mappings().one()

            sold_qty = orig_row["quantity_sold"]
            already_returned = int(totals["qty"])
            remaining_sold = sold_qty - already_returned

            if already_returned + ret.returns > sold_qty:
                raise ValidationError(
                    f"Return quantity {ret.returns} exceeds remaining sold quantity {remaining_sold} (sold={sold_qty}, returned={already_returned})",
                    code="RETURN_EXCEEDS_SOLD",
                )
            prior_value = Decimal(str(totals["value"]))
            prior_tax = Decimal(str(totals["tax"]))
            remaining_value = Decimal(str(orig_row["net_sale_ex_tax"])) - prior_value
            remaining_tax = Decimal(str(orig_row["tax_amount"])) - prior_tax
            if ret.return_value_ex_tax > remaining_value:
                raise ValidationError("Cumulative return value exceeds original sale", code="RETURN_VALUE_EXCEEDS_SOLD")
            if ret.tax_amount > remaining_tax:
                raise ValidationError("Cumulative return tax exceeds original sale", code="RETURN_TAX_EXCEEDS_SOLD")
            if ret.returns == remaining_sold:
                if ret.return_value_ex_tax != remaining_value or ret.tax_amount != remaining_tax:
                    raise ValidationError("Final return must receive the original allocation remainder", code="RETURN_VALUE_MISMATCH")
            else:
                expected_value = (
                    Decimal(str(orig_row["net_sale_ex_tax"])) * ret.returns / sold_qty
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                expected_tax = (
                    Decimal(str(orig_row["tax_amount"])) * ret.returns / sold_qty
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                if ret.return_value_ex_tax != expected_value:
                    raise ValidationError("Return value does not match the original quantity allocation", code="RETURN_VALUE_MISMATCH")
                if ret.tax_amount != expected_tax:
                    raise ValidationError("Return tax does not match the original discounted allocation", code="RETURN_TAX_MISMATCH")

            new_returned_qty = already_returned + ret.returns
            if ret.status == "approved":
                await session.execute(
                    text("""
                    UPDATE v2_sales_events
                    SET cumulative_returned_qty = :new_ret
                    WHERE id = :id
                """),
                    {"id": orig_row["id"], "new_ret": new_returned_qty},
                )

            if lifecycle_transition:
                await session.execute(
                    text("""
                        UPDATE v2_return_events
                        SET status='approved', return_value_ex_tax=:value, tax_amount=:tax,
                            refund_reference=:ref, refund_amount=:refund_amount,
                            refund_method=:refund_method, refund_at=:refund_at
                        WHERE id=:id AND tenant_id=:t
                    """),
                    {
                        "id": target_id,
                        "t": tenant_id,
                        "value": ret.return_value_ex_tax,
                        "tax": ret.tax_amount,
                        "ref": ret.refund_reference,
                        "refund_amount": ret.refund_amount,
                        "refund_method": ret.refund_method,
                        "refund_at": ret.refund_at,
                    },
                )
                await session.execute(
                    text("""
                        UPDATE event_identity_registry
                        SET payload_hash=:hash, updated_at=clock_timestamp()
                        WHERE tenant_id=:t AND source_system=:s AND entity_kind='return'
                          AND external_event_id=:event AND event_line_id=:line
                    """),
                    {
                        "hash": compute_payload_hash(ret),
                        "t": tenant_id,
                        "s": ret.source_system,
                        "event": ret.return_id,
                        "line": ret.return_line_id,
                    },
                )
            else:
                insert_return = text("""
            INSERT INTO v2_return_events (
                id, tenant_id, source_system, return_id, return_line_id, return_at,
                original_source_system, original_transaction_id, original_order_line_id,
                sale_event_id, sku_code, location_code, returns, return_value_ex_tax,
                tax_code, tax_amount, currency, reason_code, disposition, status,
                credit_note_number, refund_reference, refund_amount, refund_method,
                refund_at, exchange_order_id
            ) VALUES (
                :id, :t, :s, :ret_id, :ret_line, :ret_at,
                :orig_src, :orig_tx, :orig_line,
                :sale_id, :sku, :loc, :returns, :val,
                :tax_code, :tax_amt, :curr, :reason, :disp, :status,
                :cn, :ref_ref, :ref_amt, :ref_method,
                :ref_at, :exch_id
            )
                """)
                await session.execute(
                    insert_return,
                    {
                "id": target_id,
                "t": tenant_id,
                "s": ret.source_system,
                "ret_id": ret.return_id,
                "ret_line": ret.return_line_id,
                "ret_at": ret.return_at,
                "orig_src": ret.original_source_system,
                "orig_tx": ret.original_transaction_id,
                "orig_line": ret.original_order_line_id,
                "sale_id": orig_row["id"],
                "sku": ret.sku_code,
                "loc": ret.location_code,
                "returns": ret.returns,
                "val": ret.return_value_ex_tax,
                "tax_code": ret.tax_code,
                "tax_amt": ret.tax_amount,
                "curr": ret.currency,
                "reason": ret.reason_code,
                "disp": ret.disposition,
                "status": ret.status,
                "cn": ret.credit_note_number,
                "ref_ref": ret.refund_reference,
                "ref_amt": ret.refund_amount,
                "ref_method": ret.refund_method,
                "ref_at": ret.refund_at,
                "exch_id": ret.exchange_order_id,
                    },
                )

            return {
                "status": ret.status,
                "target_id": str(target_id),
                "remaining_sold_qty": sold_qty - new_returned_qty if ret.status == "approved" else remaining_sold,
            }
