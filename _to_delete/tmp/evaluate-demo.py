import httpx,json,csv,collections,math,time
from pathlib import Path
root=Path('..'); pack=root/'data/demo-swecha'; f=json.loads((root/'tmp/demo-session.json').read_text()); e=json.loads((root/'tmp/demo-journey.json').read_text())
with httpx.Client(base_url='http://127.0.0.1:8010/api/v1',timeout=300) as c:
    r=c.post('/auth/dev-login',json={'tenant_slug':f['slug'],'email':f['email'],'password':f['password']});r.raise_for_status(); c.headers['Authorization']='Bearer '+r.json()['access_token']
    def upload(name):
        r=c.post('/integrations/upload',data={'kind':'sales','identity':'period','currency':'INR'},files={'file':(name,(pack/name).read_bytes(),'text/csv')});r.raise_for_status(); return r.json()
    e['heldout_import']=upload('04-heldout-8-weeks.csv'); assert e['heldout_import']['rows_inserted']==192
    r=c.get('/skus',params={'limit':100});r.raise_for_status(); raw=r.json(); skus=raw if isinstance(raw,list) else raw.get('items',raw.get('skus',[])); codes={s['id']:s['sku_code'] for s in skus}
    actual=collections.defaultdict(int); history=collections.defaultdict(lambda:collections.defaultdict(int))
    for row in csv.DictReader((pack/'04-heldout-8-weeks.csv').open()): actual[(row['sku'],row['date'])]+=int(row['quantity'])
    groups={}
    for group in ['steady','seasonal','intermittent']:
        filename={'steady':'01','seasonal':'02','intermittent':'03'}[group]+f'-{group}-training.csv'
        for row in csv.DictReader((pack/filename).open()): history[row['sku']][row['date']]+=int(row['quantity']); groups[row['sku']]=group
    r=c.post('/forecasts/backtest',json={'cutoff':'2026-08-31','horizon':8});print('BACKTEST',r.status_code,flush=True);r.raise_for_status(); e['backtest']=r.json()
    scores=collections.defaultdict(lambda:dict(absolute=0,actual=0,last=0,mean4=0,points=0))
    for row in r.json()['rows']:
        sku=codes[row['sku_id']]; y=actual[(sku,row['forecast_date'][:10])]; train=[history[sku][k] for k in sorted(history[sku])]
        for group in ['all',groups[sku]]:
            t=scores[group]; t['absolute']+=abs(row['p50']-y);t['actual']+=y;t['last']+=abs(train[-1]-y);t['mean4']+=abs(sum(train[-4:])/4-y);t['points']+=1
    e['evaluation']={g:{'points':v['points'],'chronos_wape':round(v['absolute']/v['actual']*100,2),'repeat_last_wape':round(v['last']/v['actual']*100,2),'mean4_wape':round(v['mean4']/v['actual']*100,2)} for g,v in scores.items()}
    e['invalid_upload']=upload('06-invalid-example.csv');assert e['invalid_upload']['rows_inserted']==0 and e['invalid_upload']['errors']
    r=c.post('/forecasts/generate',json={'horizon':12,'force_zero_shot':True});r.raise_for_status();e['latest_forecast']=r.json();assert all(x['forecast_date']>='2026-10-26' for x in r.json()['rows'])
    for path in ['/inventory/coverage','/data-quality','/dashboard/summary']:
        r=c.get(path);e[path]={'status':r.status_code,'body':r.json() if r.status_code==200 else r.text[:300]};print(path,r.status_code,flush=True)
(root/'tmp/demo-journey.json').write_text(json.dumps(e,indent=2))
print(json.dumps(e['evaluation'],indent=2));print('Latest forecast',e['latest_forecast']['n_series'],len(e['latest_forecast']['rows']))
