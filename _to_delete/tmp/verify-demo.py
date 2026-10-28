import httpx,json,time
from pathlib import Path
root=Path('..'); pack=root/'data/demo-swecha'; evidence={'synthetic':True,'uploads':{}}
f=json.loads((root/'tmp/demo-session.json').read_text())
with httpx.Client(base_url='http://127.0.0.1:8010/api/v1',timeout=300) as c:
    r=c.post('/auth/dev-login',json={'tenant_slug':f['slug'],'email':f['email'],'password':f['password']});r.raise_for_status(); session=r.json()
    c.headers['Authorization']='Bearer '+session['access_token']
    evidence['login']={'status':r.status_code,'tenant':session['tenant_id'],'industry':session['active_industry']}
    for name,kind in [('00-products.csv','products'),('01-steady-training.csv','sales'),('02-seasonal-training.csv','sales'),('03-intermittent-training.csv','sales'),('05-inventory.csv','inventory')]:
        r=c.post('/integrations/upload',data={'kind':kind,'identity':'period','currency':'INR'},files={'file':(name,(pack/name).read_bytes(),'text/csv')})
        print(name,r.status_code,r.text[:500],flush=True);r.raise_for_status(); evidence['uploads'][name]=r.json()
        assert not r.json().get('errors')
    r=c.post('/integrations/upload',data={'kind':'sales','identity':'period','currency':'INR'},files={'file':('01-steady-training.csv',(pack/'01-steady-training.csv').read_bytes(),'text/csv')});r.raise_for_status(); evidence['replay']=r.json(); assert r.json()['rows_inserted']==0
    start=time.monotonic(); r=c.post('/forecasts/generate',json={'horizon':12,'force_zero_shot':True}); print('FORECAST',r.status_code,r.text[:400],flush=True);r.raise_for_status()
    evidence['forecast']=r.json(); evidence['forecast_seconds']=round(time.monotonic()-start,2)
(root/'tmp/demo-journey.json').write_text(json.dumps(evidence,indent=2))
print('Forecast journey verified',evidence['forecast'].get('n_series'),len(evidence['forecast'].get('rows',[])),evidence['forecast_seconds'])
