"""Follow-up acceptance probes. Uses disposable PostgreSQL via -p conftest."""
import csv
import io
from pathlib import Path
from dataclasses import replace
from decimal import Decimal
import pytest
from sqlalchemy import text
from test_import_confirmation import seed
from app.services.integrations.v2 import upload
from app.services.integrations.v2.event_registry import EventRegistryService
from app.services.integrations.v2.catalog import ValidationError
from app.services.integrations.v2.sales_returns import validate_sale_row,validate_return_row
from app.models.enums import IndustryCode

SAMPLES=Path(__file__).resolve().parent.parent/'2026-10-28-retail-v2/samples'
SECRET='review-only-secret-long-enough-123456789'
def sample(kind):
    return next(csv.DictReader(io.StringIO((SAMPLES/f'{kind}_v2_SAMPLE_ONLY.csv').read_text(encoding='utf-8'))))

@pytest.mark.asyncio
async def test_invalid_return_does_not_leave_registered_identity(app_role_db):
    ctx=await seed(app_role_db)
    ret=validate_return_row(sample('returns'))
    async with app_role_db.session(str(ctx.tenant_id)) as session:
        try:
            with pytest.raises(ValidationError):
                await EventRegistryService().post_return_event(session,ctx.tenant_id,ret)
            count=await session.scalar(text('SELECT count(*) FROM event_identity_registry WHERE tenant_id=:t'),{'t':ctx.tenant_id})
            assert count==0, 'Rejected return left a registry entry in the caller transaction'
        finally:
            await session.rollback()

@pytest.mark.asyncio
async def test_draft_return_can_be_approved_under_same_identity(app_role_db):
    ctx=await seed(app_role_db); service=EventRegistryService()
    sale=validate_sale_row(sample('sales')); ret=validate_return_row(sample('returns'))
    async with app_role_db.session(str(ctx.tenant_id)) as session:
        await service.post_sales_group(session,ctx.tenant_id,[sale])
        await service.post_return_event(session,ctx.tenant_id,replace(ret,status='draft'))
        await session.commit()
    async with app_role_db.session(str(ctx.tenant_id)) as session:
        try:
            result=await service.post_return_event(session,ctx.tenant_id,ret)
            assert result['status']=='approved'
        finally:
            await session.rollback()

@pytest.mark.asyncio
async def test_zero_value_sale_has_valid_zero_value_return(app_role_db):
    ctx=await seed(app_role_db); service=EventRegistryService()
    sale_row=sample('sales'); sale_row.update(discount_ex_tax='2000.00',tax_amount='0.00',payment_amount='0.00')
    sale=validate_sale_row(sale_row)
    ret_row=sample('returns'); ret_row.update(return_value_ex_tax='0.00',tax_amount='0.00',refund_reference='',refund_amount='',refund_method='',refund_at='')
    ret=validate_return_row(ret_row)
    async with app_role_db.session(str(ctx.tenant_id)) as session:
        try:
            await service.post_sales_group(session,ctx.tenant_id,[sale])
            assert (await service.post_return_event(session,ctx.tenant_id,ret))['status']=='approved'
        finally:
            await session.rollback()

@pytest.mark.asyncio
async def test_inventory_exact_retry_is_idempotent(app_role_db):
    ctx=await seed(app_role_db)
    content=(SAMPLES/'inventory_v2_SAMPLE_ONLY.csv').read_bytes()
    preview=upload.preview(content,ctx.tenant_id,ctx.user_id,SECRET)
    first=await upload.confirm(app_role_db,content,preview['preview_token'],ctx.tenant_id,ctx.user_id,IndustryCode.fashion,SECRET)
    assert first['inserted']==2
    again=await upload.confirm(app_role_db,content,preview['preview_token'],ctx.tenant_id,ctx.user_id,IndustryCode.fashion,SECRET)
    assert again['inserted']==0 and again['skipped']==2

@pytest.mark.asyncio
async def test_v2_http_rejects_unknown_sku_and_location(client,signed_in_workspace):
    _,headers=await signed_in_workspace('fashion')
    content=(SAMPLES/'sales_v2_SAMPLE_ONLY.csv').read_bytes()
    preview=await client.post('/api/v1/integrations/v2/preview',headers=headers,files={'file':('sale.csv',content,'text/csv')})
    assert preview.status_code==200,preview.text
    result=preview.json()
    assert result['can_confirm'] is False, 'Empty tenant catalog was accepted without resolving the sample SKU/location'

@pytest.mark.asyncio
async def test_v2_sales_appear_in_existing_analytics_history(client,signed_in_workspace,db_session):
    tenant_id,headers=await signed_in_workspace('fashion')
    content=(SAMPLES/'sales_v2_SAMPLE_ONLY.csv').read_bytes()
    preview=await client.post('/api/v1/integrations/v2/preview',headers=headers,files={'file':('sale.csv',content,'text/csv')})
    result=preview.json()
    confirmed=await client.post('/api/v1/integrations/v2/confirm',headers=headers,data={'preview_token':result['preview_token']},files={'file':('sale.csv',content,'text/csv')})
    assert confirmed.status_code==200,confirmed.text
    count=await db_session.scalar(text('SELECT count(*) FROM historical_sales WHERE tenant_id=:t'),{'t':tenant_id})
    assert count>0, 'Successful V2 sale import did not reach the existing analytics history'

@pytest.mark.asyncio
async def test_final_partial_return_gets_original_rounding_remainder(app_role_db):
    ctx=await seed(app_role_db); service=EventRegistryService()
    row=sample('sales')
    row.update(quantity_sold='3',unit_price_ex_tax='3.3333',discount_ex_tax='0.00',tax_amount='0.50',payment_amount='10.50')
    sale=validate_sale_row(row)
    ret=validate_return_row(sample('returns'))
    async with app_role_db.session(str(ctx.tenant_id)) as session:
        try:
            await service.post_sales_group(session,ctx.tenant_id,[sale])
            for i,(value,tax) in enumerate([('3.33','0.17'),('3.33','0.17'),('3.34','0.16')],1):
                result=await service.post_return_event(session,ctx.tenant_id,replace(ret,return_id=f'ROUND-{i}',return_value_ex_tax=Decimal(value),tax_amount=Decimal(tax),refund_reference=None,refund_amount=None,refund_method=None,refund_at=None))
                assert result['status']=='approved'
        finally:
            await session.rollback()
