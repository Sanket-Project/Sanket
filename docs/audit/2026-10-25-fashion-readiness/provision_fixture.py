"""Grant a test subscription using the unprivileged application role and tenant RLS."""
import asyncio, json, uuid, os
from pathlib import Path
import asyncpg

async def main():
    root=Path(__file__).parent
    if os.getenv('SANKET_AUDIT_VARIANT'): root=root/os.environ['SANKET_AUDIT_VARIANT']
    tenant=json.loads((root/'tenant.json').read_text())['tenant_id']
    conn=await asyncpg.connect('postgresql://sanket_app:changeme@localhost:55432/sanket')
    async with conn.transaction():
        await conn.execute("SELECT set_config('app.current_tenant_id',$1,true)",tenant)
        role=await conn.fetchrow('SELECT current_user,rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user')
        print(dict(role))
        assert not role['rolsuper'] and not role['rolbypassrls']
        await conn.execute("""INSERT INTO subscriptions(id,tenant_id,plan_id,status,current_period_start,current_period_end,cancel_at_period_end,metadata)
        VALUES($1,$2,'growth_monthly','active',now(),now()+interval '30 days',false,'{"audit_fixture":true}')""",uuid.uuid4(),uuid.UUID(tenant))
    await conn.close()
asyncio.run(main())
