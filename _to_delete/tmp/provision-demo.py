import asyncio, json, uuid
from types import SimpleNamespace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from sqlalchemy import text, select
from starlette.requests import Request
from app.config import get_settings
from app.core.database import Database
from app.models.tenant import Tenant, User
from app.models.billing import Subscription, SubscriptionStatus
from app.models.enums import TenantStatus
from app.routers.auth import signup
from app.schemas.auth import SignUpRequest

async def main():
    s=get_settings()
    assert s.app_env=='development' and not s.firebase_enabled
    assert 'sanket_recovered_20261026' in s.database_url
    db=Database(s)
    await db.assert_tenant_isolation_enforced(strict=True)
    slug='swecha-demo'
    email='demo@sanket.example.com'
    password='SanketDemo2026!'
    async with db.session_no_rls() as session:
        tenant=await session.scalar(select(Tenant).where(Tenant.slug==slug))
    if tenant is None:
        request=Request({'type':'http','app':SimpleNamespace(state=SimpleNamespace(db=db))})
        await signup(SignUpRequest(name='SYNTHETIC Swecha Demo',email=email,password=password,tenant_slug=slug,industry='fashion'),request,s.model_copy(update={'public_signup_enabled':True}))
    async with db.session_no_rls() as session:
        tenant=await session.scalar(select(Tenant).where(Tenant.slug==slug))
        tenant.status=TenantStatus.active
        tenant.display_name='SYNTHETIC Swecha Demo'
        tenant.settings={**(tenant.settings or {}),'currency':'INR','synthetic_fixture':True,'onboarding':{'status':'complete','current_step':'done','steps':{}}}
        sub=await session.scalar(select(Subscription).where(Subscription.tenant_id==tenant.id))
        if sub is None:
            now=datetime.now(UTC)
            session.add(Subscription(tenant_id=tenant.id,plan_id='growth_monthly',status=SubscriptionStatus.trialing,current_period_start=now,current_period_end=now+timedelta(days=14),subscription_metadata={'local_test_only':True,'synthetic_fixture':True}))
        tid=str(tenant.id)
    await db.close()
    Path('../tmp/demo-session.json').write_text(json.dumps({'slug':slug,'email':email,'password':password,'tenant_id':tid}))
    print('Isolated local demo account provisioned; 14-day local test entitlement, no payment activity.')
asyncio.run(main())
