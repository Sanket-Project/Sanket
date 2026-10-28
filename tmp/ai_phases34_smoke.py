"""Disposable Phase3/4 browser fixture. Synthetic data and mocked model only."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from testcontainers.postgres import PostgresContainer
from testcontainers.core.container import DockerContainer

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
API_PORT = 50409
WEB_PORT = 5181


async def main(url):
    from sqlalchemy import text
    from sqlalchemy.engine import make_url
    from app.config import get_settings
    from app.core.database import Database
    from app.core.security import hash_password
    from app.core.calendar import current_week_start
    from app.models.product import Product, Sku
    from app.models.inventory import InventoryLevel
    from app.models.recommendation import Recommendation
    from app.models.enums import IndustryCode, ProductStatus, DecisionKind, DecisionStatus, DecisionUrgency
    from app.services.llm.policy import AIContext, PolicyStore
    from app.services.llm.tasks import TASK_NAMES
    import httpx
    import uvicorn
    import app.services.llm.client as provider_module

    os.environ["DATABASE_URL"] = make_url(url).set(username="sanket_app", password="changeme").render_as_string(hide_password=False)
    get_settings.cache_clear()
    config = get_settings()
    db = Database(config)
    await db.assert_tenant_isolation_enforced(strict=True)
    tid, uid, run_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    now = datetime.now(UTC)
    async with db.session(str(tid)) as session:
        await session.execute(text("""INSERT INTO tenants(id,slug,display_name,industry,status,settings)
            VALUES(:tid,'ai-phases34-smoke','Synthetic AI phases 3 and 4','fashion','active',
            '{"onboarding":{"status":"complete"},"currency":"INR"}'::jsonb)"""), {"tid": tid})
        await session.execute(text("""INSERT INTO users(id,tenant_id,email,full_name,password_hash,role,active_industry)
            VALUES(:uid,:tid,'ai-phases34@example.com','Synthetic smoke reviewer',:password,'owner','fashion')"""),
            {"uid": uid, "tid": tid, "password": hash_password("SmokeOnly2026!", config)})
        await session.execute(text("""INSERT INTO subscriptions(id,tenant_id,plan_id,status,current_period_start,current_period_end)
            VALUES(:id,:tid,'enterprise_monthly','active',now()-interval '1 day',now()+interval '1 day')"""), {"id": uuid.uuid4(), "tid": tid})
        product = Product(tenant_id=tid, industry=IndustryCode.fashion, name="Synthetic shirt", category="Shirts", status=ProductStatus.active)
        session.add(product)
        await session.flush()
        sku = Sku(tenant_id=tid, product_id=product.id, industry=IndustryCode.fashion,
                  sku_code="SYNTHETIC-SHIRT-M", currency="INR", unit_cost=Decimal("40"), unit_price=Decimal("100"), lead_time_days=14, moq=1)
        session.add(sku)
        await session.flush()
        session.add(InventoryLevel(tenant_id=tid, sku_id=sku.id, industry=IndustryCode.fashion,
                                  location="WH", on_hand_units=Decimal("500"), source="synthetic_fixture", as_of=now))
        for i in range(28):
            await session.execute(text("""INSERT INTO historical_sales(tenant_id,sku_id,industry,sale_time,channel,units_sold,gross_revenue,net_revenue)
                VALUES(:tid,:sid,'fashion',:day,'pos',5,500,500)"""), {"tid": tid, "sid": sku.id, "day": now-timedelta(days=i+1)})
        await session.execute(text("""INSERT INTO forecast_runs(id,tenant_id,industry,model_stack,horizon_weeks,granularity,status,completed_at,metrics)
            VALUES(:run,:tid,'fashion',ARRAY['synthetic_fixture'],12,'weekly','completed',:now,'{"mode":"zero_shot","calendar":"W-MON-UTC"}'::jsonb)"""),
            {"run": run_id, "tid": tid, "now": datetime.now(UTC)})
        for i in range(12):
            await session.execute(text("""INSERT INTO forecast_results(tenant_id,run_id,sku_id,forecast_date,p10,p50,p90,model_name)
                VALUES(:tid,:run,:sid,:day,8,10,12,'synthetic_fixture')"""),
                {"tid": tid, "run": run_id, "sid": sku.id, "day": current_week_start(now)+timedelta(weeks=i)})
        rec = Recommendation(tenant_id=tid, industry=IndustryCode.fashion, sku_id=sku.id, run_id=run_id,
            kind=DecisionKind.purchase_order, status=DecisionStatus.accepted, urgency=DecisionUrgency.high,
            headline="Synthetic accepted order: 60 units", recommended_units=60, accepted_units=60, baseline_units=100,
            confidence=72, unit_cost=Decimal("40"), unit_price=Decimal("100"), currency="INR",
            decided_at=now, expires_at=now+timedelta(days=1),
            inputs={"unit_cost":40,"unit_price":100,"holding_cost_pct":0.25,"protection_days":42,"days_of_cover":50,"lead_time_days":14},
            economics={"capital_committed":2400,"revenue_protected":6000})
        session.add(rec)
        await session.flush()
        decision_id = rec.id
    await PolicyStore(db).configure(AIContext(tid,uid,IndustryCode.fashion), enabled=True,
        tasks={name:True for name in TASK_NAMES}, sharing="headers_only", aggregate_context=True, product_names=False)
    await db.close()

    original = provider_module.ProviderClient
    def handler(request):
        payload = json.loads(json.loads(request.content)["messages"][1]["content"])
        if "candidates" in payload:
            output = {"candidate_ids": [c["id"] for c in payload["candidates"]]}
        elif "question" in payload and "facts" not in payload:
            question = payload["question"].casefold()
            op = "inventory" if any(word in question for word in ("stock","inventory","available")) else "analytics" if "sale" in question else "saved_forecast" if "forecast" in question else "trends" if "trend" in question else "sku"
            output = {"steps":[{"operation":op}]}
        else:
            output = {"blocks":[{"proposition":f["kind"] if f["kind"] in {"advice","hypothesis","data_gap"} else "missing" if f["value"] is None else "fact", "fact_ids":[f["id"]]} for f in payload.get("facts",[])[:8]]}
        return httpx.Response(200,json={"choices":[{"finish_reason":"stop","message":{"content":json.dumps(output)}}],"usage":{"prompt_tokens":20,"completion_tokens":10}})
    provider_module.ProviderClient = lambda settings: original(settings, transport=httpx.MockTransport(handler))
    from app.main import create_app
    from app.routers.industry_router import get_tenant_id
    from fastapi import Request, HTTPException
    app = create_app()
    server = uvicorn.Server(uvicorn.Config(app,host="127.0.0.1",port=API_PORT,log_level="warning"))
    async def stop_fixture(request: Request):
        if get_tenant_id(request) != tid:
            raise HTTPException(403,"Fixture owner required")
        server.should_exit = True
        return {"stopping":True}
    app.add_api_route("/api/v1/_fixture/stop",stop_fixture,methods=["POST"],include_in_schema=False)
    (ROOT/"tmp/ai-phases34-context.json").write_text(json.dumps({"port":API_PORT,"web_port":WEB_PORT,"tenant":str(tid),"user":str(uid),"decision":str(decision_id),"isolated":True,"mocked_ai":True}),encoding="utf-8")
    print(f"ISOLATED_PHASE34_API_READY port={API_PORT}",flush=True)
    await server.serve()


if __name__ == "__main__":
    with PostgresContainer(image="pgvector/pgvector:pg16",driver="asyncpg") as pg, DockerContainer("redis:7-alpine").with_exposed_ports(6379) as redis:
        url = pg.get_connection_url()
        os.environ.update(DATABASE_URL=url,MIGRATION_DATABASE_URL=url,
            JWT_SECRET="isolated-phase34-only-jwt-secret-more-than-32-characters",
            REDIS_URL=f"redis://{redis.get_container_host_ip()}:{redis.get_exposed_port(6379)}/0",
            DEEPSEEK_API_KEY="synthetic-dummy-not-real",ML_API_URL="http://127.0.0.1:9",FIREBASE_PROJECT_ID="",FIREBASE_CREDENTIALS_PATH="",FIREBASE_WEB_API_KEY="",
            SIGNAL_PIPELINE_ENABLED="false",SHOPIFY_POLL_ENABLED="false",WHATSAPP_DIGEST_WORKER_ENABLED="false",WEBHOOK_RETRY_WORKER_ENABLED="false",
            SMTP_HOST="",SMTP_SENDER="",SMTP_USERNAME="",SMTP_PASSWORD="",
            ALLOWED_ORIGINS=f'["http://127.0.0.1:{WEB_PORT}"]')
        result = subprocess.run([sys.executable,"-m","alembic","upgrade","head"],cwd=BACKEND,env=dict(os.environ),capture_output=True,text=True)
        if result.returncode:
            print("Isolated Phase34 migrations failed",flush=True)
            raise SystemExit(1)
        asyncio.run(main(url))
