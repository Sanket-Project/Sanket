"""Reproducible local audit. All sales are synthetic fixtures, never client data."""
import csv, io, json, math, random, time, os
from pathlib import Path
from datetime import date, timedelta
import httpx

OUT = Path(__file__).resolve().parent
VARIANT=os.getenv('SANKET_AUDIT_VARIANT','initial')
if VARIANT!='initial':
    OUT=OUT/VARIANT
    OUT.mkdir(exist_ok=True)
C = httpx.Client(base_url='http://127.0.0.1:8010/api/v1', timeout=180)
evidence = json.loads((OUT/'api-evidence.json').read_text()) if (OUT/'api-evidence.json').exists() else []
def call(name, method, path, **kw):
    start = time.monotonic()
    try:
        r = C.request(method, path, **kw)
        try: body = r.json()
        except Exception:
            body = {'bytes': len(r.content), 'content_type': r.headers.get('content-type'), 'preview': r.text[:300] if 'csv' in path else ''}
            if r.is_success: (OUT / path.split('/')[-1]).write_bytes(r.content)
        safe = {k:v for k,v in body.items() if 'token' not in k} if isinstance(body,dict) else body
        evidence.append(dict(name=name, method=method, path=path, status=r.status_code, seconds=round(time.monotonic()-start,3), body=safe))
        print(name, r.status_code, round(time.monotonic()-start,2), flush=True)
        (OUT/'api-evidence.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
        return r, body
    except Exception as ex:
        evidence.append(dict(name=name, method=method,path=path,error=str(ex),seconds=round(time.monotonic()-start,3)))
        (OUT/'api-evidence.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
        print(name, type(ex).__name__, flush=True)
        return None, {}

if __name__ == '__main__':
    suffix='' if VARIANT=='initial' else '-'+VARIANT
    call('signup_fashion','POST','/auth/signup',json=dict(name='Fashion Audit',email=f'fashion.audit{suffix}@example.com',password='AuditFashion2026!',tenant_slug='swecha-audit'+suffix,industry='fashion'))
    r, auth=call('login','POST','/auth/dev-login',json=dict(email=f'fashion.audit{suffix}@example.com',password='AuditFashion2026!',tenant_slug='swecha-audit'+suffix))
    if not r or not r.is_success: raise SystemExit('Login failed')
    C.headers['Authorization']='Bearer '+auth['access_token']
    call('plans','GET','/billing/plans')
    call('subscription','GET','/billing/subscription')
    call('initial_products','GET','/products')
    # Resume after entitlement is tested/provisioned in the isolated fixture database.
    (OUT/'tenant.json').write_text(json.dumps({k:auth[k] for k in ['tenant_id','user_id','role','active_industry']}),encoding='utf-8')
    if r := next((x for x in reversed(evidence) if x['name']=='initial_products'),None):
        if r.get('status')==402: raise SystemExit('Subscription required; test fixture must explicitly grant entitlement')
    rng=random.Random(25102026)
    specs=[('KURTI-M','Straight cut kurti','Kurtis','M',104,40,1000,600,'stable'),('KURTI-XL','Straight cut kurti','Kurtis','XL',104,28,1050,630,'trend'),('GOWN-M','Festive gown','Gowns','M',104,18,2200,1250,'seasonal'),('GOWN-XL','Festive gown','Gowns','XL',104,15,2300,1350,'intermittent'),('LEGGING-M','Cotton leggings','Leggings','M',104,55,499,260,'stockout'),('PALAZZO-XL','Printed palazzo','Palazzo','XL',12,22,799,430,'new')]
    rows=[]; hold=[]; manifest=[]; product_ids={}
    for code,name,cat,size,n,base,price,cost,pattern in specs:
        if name not in product_ids:
            r,p=call('create_product_'+cat,'POST','/products',json=dict(name=name,category=cat,brand='Synthetic fashion audit',external_id='audit-'+cat.lower(),attributes={'sample_data':True}))
            product_ids[name]=p['id']
        r,s=call('create_sku_'+code,'POST',f'/skus/{product_ids[name]}/skus',json=dict(sku_code=code,unit_price=price,unit_cost=cost,currency='INR',lead_time_days=14,moq=6,attributes={'size':size,'sample_data':True}))
        values=[]
        for t in range(112):
            v=base+rng.gauss(0,base*.08)
            if pattern=='trend': v+=.35*t
            if pattern=='seasonal': v*=1+.65*math.sin(2*math.pi*(t-6)/52)
            if pattern=='intermittent': v=0 if rng.random()<.68 else base*rng.uniform(1,3)
            if pattern=='stockout' and t in range(98,102): v=0
            v=max(0,round(v)); values.append(v)
            if t<104-n: continue
            dt=date(2024,9,2)+timedelta(weeks=t)
            row=dict(sku=code,product_name=name,date=dt.isoformat(),quantity=v,price=price,revenue=v*price,cogs=v*cost,channel='Boduppal',order_id=f'AUD-{code}-{t}')
            (rows if t<104 else hold).append(row)
        manifest.append(dict(code=code,sku_id=s['id'],product_id=product_ids[name],pattern=pattern,training_weeks=n,training=values[104-n:104],holdout=values[104:],unit_price=price,unit_cost=cost))
    for filename,items in [('synthetic-training-sales.csv',rows),('synthetic-heldout-sales.csv',hold)]:
        with (OUT/filename).open('w',newline='',encoding='utf-8') as f:
            w=csv.DictWriter(f,fieldnames=list(items[0]));w.writeheader();w.writerows(items)
    (OUT/'sample-manifest.json').write_text(json.dumps(manifest,indent=2))
    data=(OUT/'synthetic-training-sales.csv').read_bytes()
    for label,path in [('analyze_csv','/integrations/upload/analyze'),('upload_training','/integrations/upload'),('reupload_idempotency','/integrations/upload')]:
        if label=='reupload_idempotency' and VARIANT!='initial': continue
        call(label,'POST',path,data={'kind':'sales'},files={'file':('synthetic-training-sales.csv',data,'text/csv')})
    call('invalid_upload','POST','/integrations/upload',data={'kind':'sales'},files={'file':('bad.csv',b'sku,date,quantity\nBAD,not-a-date,-10\n','text/csv')})
    call('inventory_multi_location','PUT','/inventory/levels',json={'items':[dict(sku_id=s['sku_id'],on_hand_units=([30,240,80,190,35,70][i] if loc=='Boduppal' else 12),location=loc,source='synthetic_audit') for i,s in enumerate(manifest) for loc in ['Boduppal','Alwal']]})
    checks=['industry/context','industry/profile','onboarding/readiness','planning/config','products','skus','inventory/levels','inventory/eoq','inventory/cost-analysis','fashion/overview',f"fashion/size-curve/{manifest[0]['product_id']}",'analytics/sales/summary','analytics/sales/timeseries','analytics/sales/top-products','signals','trends/live','trends/score','trends/economic','trends/social','trends/supply-chain','trends/regional','alerts','alerts/rules','anomaly/skus','financial/impact','forecast/accuracy','forecasts/confidence','decisions','decisions/policy','scenarios/presets','roi/summary','data-quality/report','integrations/catalog','integrations/shopify','billing/usage','notifications/whatsapp','notifications/whatsapp/preview','export/products.csv','export/skus.csv','export/inventory.csv','export/signals.csv','export/alerts.csv']
    for p in checks: call('feature_'+p,'GET','/'+p)
    call('wrong_industry_denied','GET','/pharma/overview')
    call('invalid_forecast_horizon','POST','/forecasts/generate',json={'horizon':0})
    call('forecast_8week','POST','/forecasts/generate',json={'horizon':8})
    for p in ['forecasts/confidence','forecast/accuracy','inventory/eoq','financial/impact','decisions','export/forecast.xlsx']:
        call('after_forecast_'+p,'GET','/'+p)
    for name,params in [('baseline',{}),('demand_up',{'demand_shock_pct':30}),('supplier_outage',{'supplier_outage_weeks':4}),('markdown',{'price_change_pct':-20})]:
        call('scenario_'+name,'POST','/scenarios/simulate',json={'name':name,'horizon_weeks':8,**params})
    call('hybrid_enqueue','POST','/forecast/hybrid/runs',json={'horizon_weeks':8})
