"""Review-only regression probes for the claimed V2 baseline.

Run from backend with PYTHONPATH including backend and backend/tests:
uv run pytest -p conftest ../docs/audit/2026-10-28-retail-v2-verification/test_review_repros.py
DB fixtures create a disposable PostgreSQL container. No client database is used.
Tests state the required behavior and are expected to fail on the reviewed code.
"""
import csv
import asyncio
import dataclasses
import io
from pathlib import Path
from decimal import Decimal
import pytest
from sqlalchemy import text
from test_import_confirmation import seed
from app.services.integrations.v2.catalog import ValidationError, validate_sku_row, validate_sku_batch
from app.services.integrations.v2.contracts import parse_v2_csv
from app.services.integrations.v2.inventory import validate_inventory_row
from app.services.integrations.v2.sales_returns import validate_sale_row, validate_return_row
from app.services.integrations.v2.event_registry import EventRegistryService
from app.services.integrations.v2.valuation import calculate_period_profitability, ReturnProfitabilityInput

SAMPLES = Path(__file__).resolve().parent.parent / '2026-10-28-retail-v2/samples'

def sample(kind):
    return next(csv.DictReader(io.StringIO((SAMPLES/f'{kind}_v2_SAMPLE_ONLY.csv').read_text(encoding='utf-8'))))

def test_duplicate_csv_headers_are_rejected():
    with pytest.raises(ValueError):
        parse_v2_csv(b'sku_code,sku_code\nFIRST,SECOND\n')

def test_extra_csv_cells_are_rejected():
    with pytest.raises(ValueError):
        parse_v2_csv(b'sku_code\nSKU-1,LOST-CELL\n')

def test_naive_inventory_timestamp_is_rejected():
    row=sample('inventory'); row['as_of']='2026-10-01T09:00:00'
    with pytest.raises(ValidationError):
        validate_inventory_row(row)

def test_negative_incoming_stock_is_rejected():
    row=sample('inventory'); row['in_transit_qty']='-5'; row['open_po_qty']='-7'
    with pytest.raises(ValidationError):
        validate_inventory_row(row)

def test_duplicate_default_variants_are_rejected():
    row=sample('skus'); row.update(color_code='',size_code='',size_system='')
    a=validate_sku_row(row)
    row['sku_code']='ANOTHER-DEFAULT'
    b=validate_sku_row(row)
    with pytest.raises(ValidationError):
        validate_sku_batch([a,b])

def test_sale_tax_mismatch_is_rejected():
    row=sample('sales'); row['tax_amount']='999999.00'
    with pytest.raises(ValidationError):
        validate_sale_row(row)

def test_cancelled_zero_quantity_is_validated_correctly():
    row=sample('sales'); row.update(quantity_sold=0,unit_price_ex_tax=0,discount_ex_tax=0,tax_rate_pct=0,tax_amount=0,payment_amount=0,order_status='cancelled')
    assert validate_sale_row(row).quantity_sold==0

def test_returns_only_period_does_not_crash():
    result=calculate_period_profitability([], [ReturnProfitabilityInput(Decimal('900'),1,Decimal('600'))])
    assert result.net_revenue_ex_tax==Decimal('-900.00')
    assert result.gross_margin_pct is None

@pytest.mark.asyncio
@pytest.mark.parametrize('mutation', ['wrong_sku_currency_value','draft','rejected'])
async def test_return_posting_enforces_original_and_status(app_role_db,mutation):
    ctx=await seed(app_role_db)
    service=EventRegistryService()
    sale=validate_sale_row(sample('sales'))
    ret=validate_return_row(sample('returns'))
    if mutation=='wrong_sku_currency_value':
        ret=dataclasses.replace(ret,sku_code='NOT-THE-SOLD-SKU',currency='USD',return_value_ex_tax=Decimal('999999'),tax_amount=Decimal('9999'))
    else:
        ret=dataclasses.replace(ret,status=mutation)
    async with app_role_db.session(str(ctx.tenant_id)) as session:
        try:
            await service.post_sales_group(session,ctx.tenant_id,[sale])
            if mutation=='wrong_sku_currency_value':
                with pytest.raises(ValidationError):
                    await service.post_return_event(session,ctx.tenant_id,ret)
            else:
                await service.post_return_event(session,ctx.tenant_id,ret)
                count=(await session.execute(text('SELECT cumulative_returned_qty FROM v2_sales_events WHERE tenant_id=:t AND transaction_id=:x'),{'t':ctx.tenant_id,'x':sale.transaction_id})).scalar_one()
                assert count==0, f'{mutation} return consumed {count} sold unit(s)'
        finally:
            await session.rollback()

@pytest.mark.asyncio
async def test_cross_tenant_return_fk_is_rejected(app_role_db):
    owner=await seed(app_role_db)
    other=await seed(app_role_db)
    service=EventRegistryService()
    sale=validate_sale_row(sample('sales'))
    async with app_role_db.session(str(owner.tenant_id)) as session:
        await service.post_sales_group(session,owner.tenant_id,[sale])
        sale_id=(await session.execute(text('SELECT id FROM v2_sales_events WHERE tenant_id=:t'),{'t':owner.tenant_id})).scalar_one()
        await session.commit()
    async with app_role_db.session(str(other.tenant_id)) as session:
        try:
            with pytest.raises(Exception):
                await session.execute(text('''INSERT INTO v2_return_events
                    (tenant_id,source_system,return_id,return_line_id,return_at,
                     original_source_system,original_transaction_id,original_order_line_id,
                     sale_event_id,sku_code,location_code,returns,return_value_ex_tax,
                     tax_code,tax_amount,currency,reason_code,disposition,status)
                    VALUES (:t,'REVIEW','R','RL',now(),'REVIEW','S','SL',:s,
                     'WRONG','WRONG',1,1,'REVIEW',0,'INR','REVIEW','restock','approved')'''),{'t':other.tenant_id,'s':sale_id})
        finally:
            await session.rollback()

@pytest.mark.asyncio
async def test_failed_posting_group_leaves_no_partial_sale(app_role_db):
    ctx=await seed(app_role_db)
    service=EventRegistryService()
    sale=validate_sale_row(sample('sales'))
    conflicting=dataclasses.replace(sale,order_id='DIFFERENT-ORDER')
    async with app_role_db.session(str(ctx.tenant_id)) as session:
        try:
            with pytest.raises(ValidationError):
                await service.post_sales_group(session,ctx.tenant_id,[sale,conflicting])
            count=(await session.execute(text('SELECT count(*) FROM v2_sales_events WHERE tenant_id=:t'),{'t':ctx.tenant_id})).scalar_one()
            assert count==0, 'failed group left a partial sale in the caller transaction'
        finally:
            await session.rollback()

@pytest.mark.asyncio
async def test_concurrent_identical_registry_events_are_idempotent(app_role_db):
    ctx=await seed(app_role_db)
    service=EventRegistryService()
    args=dict(tenant_id=ctx.tenant_id,source_system='REVIEW',entity_kind='sale',external_event_id='SAME',event_line_id='L',payload={'qty':1})
    reached_insert=asyncio.Event()
    async with app_role_db.session(str(ctx.tenant_id)) as first:
        async with app_role_db.session(str(ctx.tenant_id)) as second:
            try:
                initial=await service.check_and_register(session=first,**args)
                original_execute=second.execute
                async def observed_execute(statement,*a,**kw):
                    if 'INSERT INTO event_identity_registry' in str(statement):
                        reached_insert.set()
                    return await original_execute(statement,*a,**kw)
                second.execute=observed_execute
                concurrent=asyncio.create_task(service.check_and_register(session=second,**args))
                await asyncio.wait_for(reached_insert.wait(),10)
                await first.commit()
                replay=await asyncio.wait_for(concurrent,10)
                assert replay==(True,initial[1])
            finally:
                await second.rollback()
