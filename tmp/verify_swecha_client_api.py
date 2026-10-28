import httpx,json,re,time
from pathlib import Path
root=Path(r'C:/Users/admin/Desktop/Prisma')
p=json.loads((root/'_to_delete/tmp/demo-session.json').read_text())
credentials={'tenant_slug':p.get('slug','swecha-demo'),'email':p['email'],'password':p['password']}
results={}
with httpx.Client(base_url='http://127.0.0.1:8010/api/v1',timeout=120) as c:
 r=c.post('/auth/dev-login',json=credentials);r.raise_for_status();c.headers['Authorization']='Bearer '+r.json()['access_token']
 for name,url in {'reports':'/analytics/sales/client-reports','inventory':'/inventory/overview?limit=25','stock_search':'/inventory/overview?limit=25&search=Kin29178929','locations':'/locations','products':'/products?limit=25','skus':'/skus?limit=25','company_trends':'/trends/company','quality':'/data-quality/report','decisions':'/decisions','forecasts':'/forecasts/latest'}.items():
  start=time.monotonic();res=c.get(url);results[name]={'status':res.status_code,'seconds':round(time.monotonic()-start,3),'body':res.json()};print(name,res.status_code,round(time.monotonic()-start,3))
 assert results['reports']['body']['report']['sales']['net_amount']==2581934
 assert results['inventory']['body']['total_skus']==13783
 assert results['inventory']['body']['total_positions']==16519
 assert results['inventory']['body']['totals']['available_units']==38419
 assert results['stock_search']['body']['total_skus']==1
(root/'docs/audit/2026-10-27-swecha-client-data/api-verification.json').write_text(json.dumps(results,indent=2),encoding='utf-8')

