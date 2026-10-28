import httpx,json,csv,io,time
from pathlib import Path
from decimal import Decimal as D
root=Path(r'C:/Users/admin/Desktop/Prisma');account=json.loads((root/'_to_delete/tmp/demo-session.json').read_text());report={}
with httpx.Client(base_url='http://127.0.0.1:8010/api/v1',timeout=120) as c:
 login=c.post('/auth/dev-login',json={'tenant_slug':account['slug'],'email':account['email'],'password':account['password']});login.raise_for_status();c.headers['Authorization']='Bearer '+login.json()['access_token']
 for name,path in {'average':'/forecasts/average-sales?horizon_weeks=12&limit=25','average_next':'/forecasts/average-sales?horizon_weeks=12&limit=25&offset=25','average_search':'/forecasts/average-sales?horizon_weeks=4&search=77SHADP0L49996','inventory':'/inventory/overview?limit=25','inventory_branch':'/inventory/overview?limit=25&location=sai%20balaji%20fashions%20-%20alwal','inventory_search':'/inventory/overview?search=77SHADP0L49996','industry':'/industry/context','overview':'/fashion/overview','profile':'/industry/profile','roi':'/roi/summary','financial':'/financial/impact','stock_costs':'/inventory/cost-analysis','alerts':'/alerts','alert_rules':'/alerts/rules','accuracy':'/forecast/accuracy','anomalies':'/anomaly/skus','scenarios':'/scenarios/presets','digest_config':'/notifications/whatsapp','digest_preview':'/notifications/whatsapp/preview','signals':'/signals','integrations':'/integrations/catalog','subscription':'/billing/subscription','usage':'/billing/usage','billing_config':'/billing/config','ml':'/forecasts/ml-health'}.items():
  began=time.monotonic();r=c.get(path);report[name]={'status':r.status_code,'seconds':round(time.monotonic()-began,3),'body':r.json()};print(name,r.status_code,round(time.monotonic()-began,3),flush=True)
 for name,expected in [('inventory',16519),('skus',13783),('products',12148)]:
  r=c.get('/export/'+name+'.csv');r.raise_for_status();rows=list(csv.DictReader(io.StringIO(r.text.lstrip('\ufeff'))));assert len(rows)==expected,(name,len(rows));report[name+'_export']={'status':r.status_code,'rows':len(rows)};print(name+'_export',len(rows),flush=True)
  if name=='inventory':
   print('export columns',list(rows[0]))
   quantity=next(k for k in rows[0] if k in ('on_hand_units','on_hand'))
   assert sum(D(row[quantity]) for row in rows)==D('38419')
 a=report['average']['body'];assert a['eligible_skus']==4014 and a['missing_skus']==9658 and a['unsupported_skus']==111
 assert a['source_periods'][0]['days']==298 and a['model_run_id'] is None and a['uncertainty'] is None
 assert report['average_next']['body']['rows'][0]['sku_id']!=a['rows'][0]['sku_id']
 search=report['average_search']['body'];assert search['filtered_skus']==1
 row=search['rows'][0];assert abs(row['projected_units']-row['reported_units']/298*28)<1e-8
 assert report['inventory_search']['body']['coverage']['skus'][0]['demand']['basis']=='period_average'
 local=next(r for r in report['inventory_search']['body']['coverage']['skus'][0]['locations'] if r['location'].endswith('alwal'))
 assert '22 reported units / 298 days' in local['reason'] and '0 week(s)' not in local['reason']
 assert 'no stockout risks' not in report['digest_preview']['body']['body']
 (root/'docs/audit/2026-10-27-swecha-client-data/feature-verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 print('Client projection, inventory, paging, exact source formula and complete CSV exports verified.',flush=True)

