"""Independent reconciliation, held-out scoring, and negative-path checks."""
import asyncio,csv,json,uuid,sys,os,time
from pathlib import Path
from collections import Counter
import asyncpg,httpx

ROOT=Path(__file__).parent
async def reconcile(root):
    tenant=json.loads((root/'tenant.json').read_text())['tenant_id']
    conn=await asyncpg.connect('postgresql://sanket_app:changeme@localhost:55432/sanket')
    async with conn.transaction():
        await conn.execute("SELECT set_config('app.current_tenant_id',$1,true)",tenant)
        data=await conn.fetch("""SELECT s.sku_code,count(*) rows,sum(h.units_sold) units,count(DISTINCT (h.sale_time,h.metadata->>'order_id')) distinct_orders FROM historical_sales h JOIN skus s ON h.sku_id=s.id WHERE h.tenant_id=$1 GROUP BY s.sku_code ORDER BY s.sku_code""",uuid.UUID(tenant))
        result=[dict(x) for x in data]
        result.append({'other_tenant_products_visible':await conn.fetchval('SELECT count(*) FROM products WHERE tenant_id!=$1',uuid.UUID(tenant))})
        result.append({'partitions':await conn.fetchval("SELECT count(*) FROM pg_tables WHERE tablename LIKE 'trend_signals_2026_10%'")})
    await conn.close()
    (root/'database-reconciliation.json').write_text(json.dumps(result,indent=2,default=str))

def metrics(root):
    ev=json.loads((root/'api-evidence.json').read_text());m=json.loads((root/'sample-manifest.json').read_text())
    fc=next(x['body'] for x in ev if x['name']=='forecast_8week')
    result=[];total_actual=0;total_err=0;baseline_err=0;cover=0;count=0
    for s in m:
        rows=sorted([r for r in fc['rows'] if r['sku_id']==s['sku_id']],key=lambda x:x['forecast_date'])
        a=s['holdout'];p=[r['p50'] for r in rows];n=len(a)
        def wape(p):return 100*sum(abs(x-y) for x,y in zip(a,p))/sum(a) if sum(a) else None
        baselines={'last_value':[s['training'][-1]]*n,'last4_mean':[sum(s['training'][-4:])/4]*n}
        if len(s['training'])>=60:baselines['seasonal52']=s['training'][-52:-44]
        c=sum(r['p10']<=y<=r['p90'] for r,y in zip(rows,a))
        res=dict(sku=s['code'],pattern=s['pattern'],actual_units=sum(a),forecast_units=round(sum(p),2),wape=round(wape(p),2),bias_pct=round(100*(sum(p)-sum(a))/sum(a),2),interval_coverage_pct=100*c/n,baselines={k:round(wape(v),2) for k,v in baselines.items()},forecast_dates=[r['forecast_date'] for r in rows])
        result.append(res);total_actual+=sum(a);total_err+=sum(abs(x-y) for x,y in zip(a,p));baseline_err+=sum(abs(x-y) for x,y in zip(a,baselines['last_value']));cover+=c;count+=n
    summary=dict(dataset='DETERMINISTIC SYNTHETIC - NOT SWECHA SALES',scoring='Forecast steps paired with next 8 withheld Monday-labelled buckets; response dates separately fail alignment (Sunday vs Monday).',portfolio_wape=round(100*total_err/total_actual,2),last_value_wape=round(100*baseline_err/total_actual,2),interval_coverage_pct=round(100*cover/count,2),n_skus=len(m),n_heldout_points=count,rows=result)
    (root/'holdout-metrics.json').write_text(json.dumps(summary,indent=2))
    print(root.name,'WAPE',summary['portfolio_wape'],'baseline',summary['last_value_wape'],flush=True)

asyncio.run(reconcile(ROOT));asyncio.run(reconcile(ROOT/'clean-run'))
metrics(ROOT);metrics(ROOT/'clean-run')
os.environ['SANKET_AUDIT_VARIANT']='clean-run'
from run_audit import call,C,OUT,evidence
r,auth=call('deep_login','POST','/auth/dev-login',json=dict(email='fashion.audit-clean-run@example.com',password='AuditFashion2026!',tenant_slug='swecha-audit-clean-run'))
C.headers['Authorization']='Bearer '+auth['access_token']
m=json.loads((OUT/'sample-manifest.json').read_text())
for s in m: call('eoq_'+s['code'],'GET','/inventory/eoq',params={'sku_id':s['sku_id']})
call('decisions_refresh','POST','/decisions/refresh')
_,decisions=call('decisions_after_refresh','GET','/decisions')
# Poll the durable run only; do not infer success from 202 acceptance.
run=next(x['body']['run_id'] for x in evidence if x['name']=='hybrid_enqueue')
call('hybrid_final_status','GET','/forecast/hybrid/runs/'+run)
call('anonymous_products','GET','/products',headers={'Authorization':''})
call('wrong_industry_header','GET','/products',headers={'X-Industry-Code':'pharma'})
call('foreign_product','GET','/products/'+json.loads((ROOT/'sample-manifest.json').read_text())[0]['product_id'])
# Import previously withheld observations only after forecasts and independent metrics were frozen.
held=(OUT/'synthetic-heldout-sales.csv').read_bytes()
call('upload_heldout_after_prediction','POST','/integrations/upload',data={'kind':'sales'},files={'file':('heldout-sales.csv',held,'text/csv')})
call('accuracy_with_matching_actuals_available','GET','/forecast/accuracy')
call('revenue_reconciliation_after_holdout','GET','/analytics/sales/summary')
# Confirm cold-start claim using a completely unsold SKU.
r,cold=call('create_unsold_sku','POST',f"/skus/{m[0]['product_id']}/skus",json={'sku_code':'COLD-START-UNSOLD','unit_cost':600,'unit_price':1000,'currency':'INR','attributes':{'size':'5XL','sample_data':True}})
call('forecast_with_unsold_sku','POST','/forecasts/generate',json={'horizon':8})
# Empty tenant has a subscription, but no sales: must fail honestly.
call('deep_health','GET','http://127.0.0.1:8010/health')
