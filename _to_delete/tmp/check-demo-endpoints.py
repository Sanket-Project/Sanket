import httpx,json,asyncio
from pathlib import Path
from sqlalchemy import text
from app.config import get_settings
from app.core.database import Database
root=Path('..'); f=json.loads((root/'tmp/demo-session.json').read_text()); evidence=json.loads((root/'tmp/demo-journey.json').read_text())
with httpx.Client(base_url='http://127.0.0.1:8010',timeout=120) as c:
    r=c.post('/api/v1/auth/dev-login',json={'tenant_slug':f['slug'],'email':f['email'],'password':f['password']});r.raise_for_status();c.headers['Authorization']='Bearer '+r.json()['access_token']
    checks=['/health','/api/v1/health','/api/v1/data-quality/report','/api/v1/decisions','/api/v1/forecasts/confidence','/api/v1/analytics/sales/timeseries?granularity=day&lookback_days=30','/api/v1/integrations/catalog','/api/v1/onboarding/state','/api/v1/inventory/coverage']
    evidence['dashboard_endpoints']={}
    for url in checks:
        r=c.get(url);r.raise_for_status(); evidence['dashboard_endpoints'][url]={'status':r.status_code,'body':r.json()};print(url,r.status_code)
    evidence.pop('/data-quality',None);evidence.pop('/dashboard/summary',None)
    for url in ['/api/v1/auth/signup','/api/v1/auth/google-signup','/api/v1/auth/sandbox-session']:
        payload={'name':'Blocked','email':'blocked@example.com','password':'Blocked2026!','tenant_slug':'blocked','workspace_slug':'blocked','industry':'fashion','id_token':'invalid'}
        if url.endswith('signup') and not url.endswith('google-signup'): payload={k:payload[k] for k in ['name','email','password','tenant_slug','industry']}
        elif url.endswith('google-signup'): payload={k:payload[k] for k in ['name','workspace_slug','industry','id_token']}
        else: payload=None
        r=c.post(url,json=payload); print('PRIVATE',url,r.status_code); assert r.status_code in (403,404)
    r=c.post('/api/v1/auth/logout');r.raise_for_status(); evidence['logout_status']=r.status_code
async def isolation():
    db=Database(get_settings())
    try:
        async with db.session(f['tenant_id']) as s:
            own=await s.scalar(text('SELECT count(*) FROM historical_sales'))
            foreign=await s.scalar(text('SELECT count(*) FROM historical_sales WHERE tenant_id != :t'),{'t':f['tenant_id']})
        async with db.session() as s: unscoped=await s.scalar(text('SELECT count(*) FROM historical_sales'))
        assert own==2688 and foreign==0 and unscoped==0
        return {'own_sales':own,'foreign_sales':foreign,'without_context':unscoped}
    finally: await db.close()
evidence['rls']=asyncio.run(isolation())
(root/'tmp/demo-journey.json').write_text(json.dumps(evidence,indent=2))
