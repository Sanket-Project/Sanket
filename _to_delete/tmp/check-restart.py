import httpx,json
from pathlib import Path
r=Path('..'); out={}
with httpx.Client(timeout=30) as c:
    for name in ['demo','client']:
        f=json.loads((r/f'tmp/{name}-session.json').read_text());a=c.post('http://127.0.0.1:5173/api/v1/auth/dev-login',json={'tenant_slug':f['slug'],'email':f['email'],'password':f['password']});a.raise_for_status();headers={'Authorization':'Bearer '+a.json()['access_token']}
        out[name]={'login_via_frontend_proxy':a.status_code}
        for path in ['/api/v1/health','/api/v1/onboarding/state','/api/v1/skus']:
            response=c.get('http://127.0.0.1:5173'+path,headers=headers);response.raise_for_status();out[name][path]=response.json()
        if name=='client':
            payload=out[name]['/api/v1/skus']; skus=payload if isinstance(payload,list) else payload.get('items',payload.get('skus',[]));assert len(skus)==0
    anon=c.post('http://127.0.0.1:8001/forecast',json={'tenant_id':f['tenant_id'],'industry':'fashion','horizon':1}); assert anon.status_code==401;out['ml_anonymous_status']=anon.status_code
(r/'docs/audit/2026-10-26-demo-readiness/restart-check.json').write_text(json.dumps(out,indent=2))
print('Final restart verified: both accounts sign in via frontend proxy; API+ML health OK; client workspace empty; anonymous ML returns 401.')
