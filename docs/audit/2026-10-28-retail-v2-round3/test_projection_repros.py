"""Review-only probes with valid tenant catalog fixtures, disposable PostgreSQL."""
import csv
import io
from pathlib import Path
from decimal import Decimal
import pytest
from sqlalchemy import text

SAMPLES=Path(__file__).resolve().parent.parent/'2026-10-28-retail-v2/samples'

async def seed_catalog(db,tenant):
    product=await db.scalar(text("INSERT INTO products (id,tenant_id,industry,external_id,name,category,status,attributes) VALUES (gen_random_uuid(),:t,'fashion','DEMO-KUR-001','Demo Kurti','apparel','active','{}'::jsonb) RETURNING id"),{'t':tenant})
    await db.execute(text("INSERT INTO skus (id,tenant_id,product_id,industry,sku_code,currency,attributes) VALUES (gen_random_uuid(),:t,:p,'fashion','DEMO-KUR-001-BLU-M','INR','{}'::jsonb)"),{'t':tenant,'p':product})
    await db.execute(text("INSERT INTO locations (id,tenant_id,code,name,kind,is_active,attributes) VALUES (gen_random_uuid(),:t,'demo-hyd-store','Demo','store',true,'{}'::jsonb)"),{'t':tenant})
    await db.commit()

def content(kind,**changes):
    if not changes:return (SAMPLES/f'{kind}_v2_SAMPLE_ONLY.csv').read_bytes()
    reader=csv.DictReader(io.StringIO((SAMPLES/f'{kind}_v2_SAMPLE_ONLY.csv').read_text()))
    rows=list(reader);rows[0].update(changes)
    out=io.StringIO();writer=csv.DictWriter(out,fieldnames=reader.fieldnames);writer.writeheader();writer.writerows(rows)
    return out.getvalue().encode()

async def post(client,headers,data):
    preview=await client.post('/api/v1/integrations/v2/preview',headers=headers,files={'file':('review.csv',data,'text/csv')})
    assert preview.status_code==200,preview.text
    assert preview.json()['can_confirm'],preview.text
    result=await client.post('/api/v1/integrations/v2/confirm',headers=headers,data={'preview_token':preview.json()['preview_token']},files={'file':('review.csv',data,'text/csv')})
    assert result.status_code==200,result.text
    return result.json()

@pytest.mark.asyncio
async def test_seeded_sale_projects_and_replay_does_not_duplicate(client,signed_in_workspace,db_session):
    tenant,headers=await signed_in_workspace('fashion');await seed_catalog(db_session,tenant)
    first=await post(client,headers,content('sales'));assert first['inserted']==1
    second=await post(client,headers,content('sales'));assert second['skipped']==1
    count=await db_session.scalar(text('SELECT count(*) FROM historical_sales WHERE tenant_id=:t'),{'t':tenant})
    assert count==1

@pytest.mark.asyncio
async def test_return_does_not_restate_the_previous_days_sale(client,signed_in_workspace,db_session):
    tenant,headers=await signed_in_workspace('fashion');await seed_catalog(db_session,tenant)
    await post(client,headers,content('sales'));await post(client,headers,content('returns'))
    original=await db_session.scalar(text("SELECT sum(net_revenue) FROM historical_sales WHERE tenant_id=:t AND sale_time::date='2026-10-02'"),{'t':tenant})
    assert original==Decimal('1800.00'), 'Oct 3 return retroactively reduced the Oct 2 sale'

@pytest.mark.asyncio
async def test_distinct_external_identities_do_not_collide_in_projection(client,signed_in_workspace,db_session):
    tenant,headers=await signed_in_workspace('fashion');await seed_catalog(db_session,tenant)
    await post(client,headers,content('sales',source_system='REVIEW:A',transaction_id='B'))
    await post(client,headers,content('sales',source_system='REVIEW',transaction_id='A:B'))
    count=await db_session.scalar(text('SELECT count(*) FROM historical_sales WHERE tenant_id=:t'),{'t':tenant})
    assert count==2,'Distinct source/transaction tuples collided in the colon-concatenated projection key'

@pytest.mark.asyncio
async def test_partial_quantity_return_cannot_claim_almost_all_sale_value(client,signed_in_workspace,db_session):
    tenant,headers=await signed_in_workspace('fashion');await seed_catalog(db_session,tenant)
    await post(client,headers,content('sales'))
    data=content('returns',return_value_ex_tax='1700.00',tax_amount='85.00',refund_amount='1785.00')
    preview=await client.post('/api/v1/integrations/v2/preview',headers=headers,files={'file':('review.csv',data,'text/csv')})
    result=await client.post('/api/v1/integrations/v2/confirm',headers=headers,data={'preview_token':preview.json()['preview_token']},files={'file':('review.csv',data,'text/csv')})
    assert result.status_code==400,'One of two equally priced units was allowed to claim 1700 of 1800 net value'
