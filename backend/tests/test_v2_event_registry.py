"""Tests for Event Identity Registry, Deduplication, and Atomic Posting Groups (P0-06)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
import pytest
from sqlalchemy import text
from test_import_confirmation import seed

from app.services.integrations.v2.catalog import ValidationError
from app.services.integrations.v2.event_registry import EventRegistryService
from app.services.integrations.v2.sales_returns import ValidatedSale, ValidatedReturn


@pytest.mark.parametrize('net,tax,allocations', [
    ('10.00', '0.50', [('3.33', '0.17'), ('3.33', '0.17'), ('3.34', '0.16')]),
    ('0.00', '0.00', [('0.00', '0.00')] * 3),
])
async def test_quantity_allocation_and_final_remainder(app_role_db, net, tax, allocations):
    from dataclasses import replace
    from pathlib import Path
    from app.services.integrations.v2.contracts import parse_v2_csv
    from app.services.integrations.v2.sales_returns import validate_sale_row, validate_return_row

    samples = Path(__file__).resolve().parents[2] / 'docs/audit/2026-10-28-retail-v2/samples'
    sale_row = parse_v2_csv((samples / 'sales_v2_SAMPLE_ONLY.csv').read_bytes())[1][0]
    sale_row.update(quantity_sold='3', unit_price_ex_tax='3.3333', discount_ex_tax=str(Decimal('10') - Decimal(net)), tax_amount=tax, payment_amount=str(Decimal(net) + Decimal(tax)))
    sale = validate_sale_row(sale_row)
    ret = validate_return_row(parse_v2_csv((samples / 'returns_v2_SAMPLE_ONLY.csv').read_bytes())[1][0])
    ctx = await seed(app_role_db)
    service = EventRegistryService()
    async with app_role_db.session(str(ctx.tenant_id)) as session:
        await service.post_sales_group(session, ctx.tenant_id, [sale])
        for i, (value, credit_tax) in enumerate(allocations):
            result = await service.post_return_event(session, ctx.tenant_id, replace(
                ret, return_id=f'ROUND-{i}', return_value_ex_tax=Decimal(value), tax_amount=Decimal(credit_tax),
                refund_reference=None, refund_amount=None, refund_method=None, refund_at=None,
            ))
            assert result['remaining_sold_qty'] == 2 - i


@pytest.mark.asyncio
async def test_event_registry_idempotent_replay_and_conflict(app_role_db):
    """Exact duplicate payload skips idempotently; conflicting payload raises EVENT_PAYLOAD_CONFLICT."""
    ctx = await seed(app_role_db)
    tenant_id = ctx.tenant_id
    service = EventRegistryService()

    payload_a = {"sku": "KUR-01", "qty": 2, "price": "1000.00"}
    payload_b = {"sku": "KUR-01", "qty": 3, "price": "1000.00"}  # Changed qty

    async with app_role_db.session(str(tenant_id)) as session:
        # First registration
        is_dup, target_id = await service.check_and_register(
            session=session,
            tenant_id=tenant_id,
            source_system="DEMO-POS",
            entity_kind="sale",
            external_event_id="TXN-101",
            event_line_id="LINE-1",
            payload=payload_a,
        )
        assert is_dup is False
        assert target_id is not None
        await session.commit()

    async with app_role_db.session(str(tenant_id)) as session:
        # Exact duplicate replay -> idempotent skip
        is_dup, target_id_2 = await service.check_and_register(
            session=session,
            tenant_id=tenant_id,
            source_system="DEMO-POS",
            entity_kind="sale",
            external_event_id="TXN-101",
            event_line_id="LINE-1",
            payload=payload_a,
        )
        assert is_dup is True
        assert target_id_2 == target_id
        await session.commit()

    async with app_role_db.session(str(tenant_id)) as session:
        # Conflicting duplicate -> must raise EVENT_PAYLOAD_CONFLICT
        with pytest.raises(ValidationError) as exc_info:
            await service.check_and_register(
                session=session,
                tenant_id=tenant_id,
                source_system="DEMO-POS",
                entity_kind="sale",
                external_event_id="TXN-101",
                event_line_id="LINE-1",
                payload=payload_b,
            )
        assert exc_info.value.code == "EVENT_PAYLOAD_CONFLICT"


@pytest.mark.asyncio
async def test_sale_posting_and_linked_return_caps(app_role_db):
    """Test posting a sale group, then posting returns up to sold quantity, rejecting over-return."""
    ctx = await seed(app_role_db)
    tenant_id = ctx.tenant_id
    service = EventRegistryService()

    sale = ValidatedSale(
        source_system="DEMO-POS",
        transaction_id="TXN-200",
        order_id="ORD-200",
        order_line_id="LINE-1",
        transaction_at=datetime(2026, 10, 2, 12, 0, tzinfo=UTC),
        sku_code="DEMO-KUR-001",
        location_code="demo-hyd-store",
        fulfillment_location_code="demo-hyd-store",
        channel_code="pos",
        quantity_sold=2,
        returns=0,
        unit_price_ex_tax=Decimal("1000.0000"),
        mrp_incl_tax=Decimal("1575.00"),
        discount_ex_tax=Decimal("200.00"),
        gross_sales_ex_tax=Decimal("2000.00"),
        net_sale_ex_tax=Decimal("1800.00"),
        tax_code="DEMO-TAX-5",
        tax_rate_pct=Decimal("5.0000"),
        tax_amount=Decimal("90.00"),
        currency="INR",
        order_status="completed",
    )

    async with app_role_db.session(str(tenant_id)) as session:
        result = await service.post_sales_group(session, tenant_id, [sale])
        assert result["inserted"] == 1
        assert result["skipped"] == 0
        await session.commit()

    # First return: 1 unit returned -> OK (sold=2, remaining returnable=1)
    ret1 = ValidatedReturn(
        source_system="DEMO-POS",
        return_id="RET-001",
        return_line_id="RLINE-1",
        return_at=datetime(2026, 10, 3, 13, 0, tzinfo=UTC),
        original_source_system="DEMO-POS",
        original_transaction_id="TXN-200",
        original_order_line_id="LINE-1",
        sku_code="DEMO-KUR-001",
        location_code="demo-hyd-store",
        returns=1,
        return_value_ex_tax=Decimal("900.00"),
        tax_code="DEMO-TAX-5",
        tax_amount=Decimal("45.00"),
        currency="INR",
        reason_code="size_issue",
        disposition="restock",
        status="approved",
    )

    async with app_role_db.session(str(tenant_id)) as session:
        res_ret1 = await service.post_return_event(session, tenant_id, ret1)
        assert res_ret1["status"] == "approved"
        assert res_ret1["remaining_sold_qty"] == 1
        await session.commit()

    # Second return: attempting to return 2 units -> should FAIL because only 1 remains returnable!
    ret2 = ValidatedReturn(
        source_system="DEMO-POS",
        return_id="RET-002",
        return_line_id="RLINE-1",
        return_at=datetime(2026, 10, 3, 14, 0, tzinfo=UTC),
        original_source_system="DEMO-POS",
        original_transaction_id="TXN-200",
        original_order_line_id="LINE-1",
        sku_code="DEMO-KUR-001",
        location_code="demo-hyd-store",
        returns=2,  # Over-return!
        return_value_ex_tax=Decimal("1800.00"),
        tax_code="DEMO-TAX-5",
        tax_amount=Decimal("90.00"),
        currency="INR",
        reason_code="damaged",
        disposition="damaged",
        status="approved",
    )

    async with app_role_db.session(str(tenant_id)) as session:
        with pytest.raises(ValidationError) as exc_info:
            await service.post_return_event(session, tenant_id, ret2)
        assert exc_info.value.code == "RETURN_EXCEEDS_SOLD"
