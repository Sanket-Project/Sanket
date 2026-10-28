import asyncio,json
from pathlib import Path
import httpx,websockets
async def main():
    a=httpx.post('http://127.0.0.1:8010/api/v1/auth/dev-login',json={'email':'fashion.audit-clean-run@example.com','password':'AuditFashion2026!','tenant_slug':'swecha-audit-clean-run'}).json()
    async with websockets.connect('ws://127.0.0.1:8010/ws?token='+a['access_token']) as ws:
        hello=json.loads(await asyncio.wait_for(ws.recv(),10))
        assert hello['type']=='connection.ready' and hello['tenant_id']==a['tenant_id']
        await ws.send('ping');pong=await asyncio.wait_for(ws.recv(),10);assert pong=='pong'
    result={'connection_ready':True,'correct_tenant':True,'ping_pong':True,'scope':'Local authenticated handshake and keepalive only; no sales event fan-out assertion.'}
    Path(__file__).with_name('websocket-check.json').write_text(json.dumps(result,indent=2))
    print(result)
asyncio.run(main())
