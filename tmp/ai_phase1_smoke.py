"""Disposable running-app fixture; no customer database or model is used."""
import asyncio
import json
import os
import socket
import subprocess
import sys
import uuid
from pathlib import Path

from testcontainers.postgres import PostgresContainer
from testcontainers.core.container import DockerContainer

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))
EVIDENCE = ROOT / "docs/audit/2026-10-27-ai-phase-1"


async def main(url, port):
    from sqlalchemy import text
    from sqlalchemy.engine import make_url
    from app.config import get_settings
    from app.core.database import Database
    from app.core.security import hash_password
    from app.main import create_app
    import uvicorn

    os.environ["DATABASE_URL"] = make_url(url).set(username="sanket_app", password="changeme").render_as_string(hide_password=False)
    get_settings.cache_clear()
    config = get_settings()
    db = Database(config)
    await db.assert_tenant_isolation_enforced(strict=True)
    tid, uid = uuid.uuid4(), uuid.uuid4()
    async with db.session(str(tid)) as session:
        await session.execute(text("""INSERT INTO tenants (id,slug,display_name,industry,status,settings)
            VALUES (:tid,'ai-foundation-smoke','AI foundation smoke','fashion','active',
            '{"onboarding":{"status":"complete"},"currency":"INR"}'::jsonb)"""), {"tid": tid})
        await session.execute(text("""INSERT INTO users (id,tenant_id,email,full_name,password_hash,role)
            VALUES (:uid,:tid,'ai-foundation-smoke@example.com','Smoke fixture',:password,'owner')"""),
                              {"uid": uid, "tid": tid, "password": hash_password("SmokeOnly2026!", config)})
        await session.execute(text("""INSERT INTO subscriptions
            (id,tenant_id,plan_id,status,current_period_start,current_period_end)
            VALUES (:id,:tid,'enterprise_monthly','active',now()-interval '1 day',now()+interval '1 day')"""),
                              {"id": uuid.uuid4(), "tid": tid})
    await db.close()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "smoke-context.json").write_text(json.dumps({"port": port, "tenant": str(tid), "user": str(uid),
                                                             "isolated": True, "ai_enabled": False}))
    print(f"ISOLATED_API_READY port={port}", flush=True)
    import httpx
    import app.services.llm.client as provider_module
    original = provider_module.ProviderClient
    def handler(request):
        envelope = json.loads(request.content)
        payload = json.loads(envelope["messages"][1]["content"])
        if "columns" in payload:
            special = {"Qty Sold (Pcs)": "quantity", "मात्रा": "quantity", "Unit Retail Price": "price"}
            output = {"selections": [{"column_id": c["id"], "field": special.get(c["label"]), "confidence": "high", "reason": "header_meaning"} for c in payload["columns"]]}
        else:
            output = {"blocks": [{"proposition": f["kind"] if f["kind"] in {"advice","hypothesis","data_gap"} else "missing" if f["value"] is None else "fact", "fact_ids": [f["id"]]} for f in payload.get("facts", [])[:8]]}
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(output)}}], "usage": {"prompt_tokens": 20, "completion_tokens": 10}})
    provider_module.ProviderClient = lambda settings: original(settings, transport=httpx.MockTransport(handler))
    app = create_app()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    async def stop_fixture():
        server.should_exit = True
        return {"stopping": True}
    app.add_api_route("/_fixture/stop", stop_fixture, methods=["POST"], include_in_schema=False)
    await server.serve()


if __name__ == "__main__":
    with PostgresContainer(image="pgvector/pgvector:pg16", driver="asyncpg") as pg, DockerContainer("redis:7-alpine").with_exposed_ports(6379) as redis:
        url = pg.get_connection_url()
        os.environ.update(DATABASE_URL=url, MIGRATION_DATABASE_URL=url,
            JWT_SECRET="isolated-smoke-only-jwt-secret-more-than-32-characters", REDIS_URL=f"redis://{redis.get_container_host_ip()}:{redis.get_exposed_port(6379)}/0",
            DEEPSEEK_API_KEY="smoke-dummy-not-real", ML_API_URL="http://127.0.0.1:9", FIREBASE_PROJECT_ID="", FIREBASE_CREDENTIALS_PATH="", FIREBASE_WEB_API_KEY="",
            SIGNAL_PIPELINE_ENABLED="false", SHOPIFY_POLL_ENABLED="false", WHATSAPP_DIGEST_WORKER_ENABLED="false",
            WEBHOOK_RETRY_WORKER_ENABLED="false", FIREBASE_CREDENTIALS_JSON="", ALLOWED_ORIGINS='["http://127.0.0.1:5179"]')
        result = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND,
                                env=dict(os.environ), capture_output=True, text=True)
        if result.returncode:
            print("Isolated migration failed", flush=True)
            raise SystemExit(1)
        with socket.socket() as probe:
            previous = EVIDENCE / "smoke-context.json"
            probe.bind(("127.0.0.1", json.loads(previous.read_text())["port"] if previous.exists() else 0))
            port = probe.getsockname()[1]
        asyncio.run(main(url, port))
