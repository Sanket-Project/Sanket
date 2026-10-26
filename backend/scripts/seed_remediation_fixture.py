"""Prepare a clearly labelled synthetic E2E tenant on the isolated local stack.

Sales are deliberately NOT inserted: Playwright imports the generated files.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import asyncpg
import httpx

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "docs/audit/2026-10-25-fashion-readiness"
OUT = ROOT / "docs/audit/2026-10-26-fashion-remediation/e2e"


def validate_target(url: str, port: int) -> None:
    parsed = urlsplit(url.replace("postgresql+asyncpg", "postgresql"))
    if (port != 55433 or parsed.port != port or parsed.hostname not in {"localhost", "127.0.0.1"}
            or parsed.username != "sanket_app"):
        raise ValueError("Synthetic seeding requires explicit --db-port 55433 and loopback sanket_app URL on that port")


async def seed(db_port: int, slug: str) -> None:
    url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg", "postgresql")
    validate_target(url, db_port)
    OUT.mkdir(parents=True, exist_ok=True)
    email = f"{slug}@example.com"
    password = "SyntheticFashion2026!"
    async with httpx.AsyncClient(base_url="http://127.0.0.1:8011/api/v1", timeout=120) as client:
        signup = await client.post("/auth/signup", json={"name": "SYNTHETIC Fashion Remediation",
            "email": email, "password": password, "tenant_slug": slug, "industry": "fashion"})
        if signup.status_code not in {201, 409}:
            signup.raise_for_status()
        login = await client.post("/auth/dev-login", json={"email": email, "password": password, "tenant_slug": slug})
        login.raise_for_status()
        auth = login.json()
        tenant_id = uuid.UUID(auth["tenant_id"])
        client.headers["Authorization"] = f"Bearer {auth['access_token']}"
        conn = await asyncpg.connect(url)
        try:
            role = await conn.fetchrow("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user")
            if role["rolsuper"] or role["rolbypassrls"]:
                raise ValueError("Seed role must enforce RLS")
            async with conn.transaction():
                await conn.execute("SELECT set_config('app.current_tenant_id',$1,true)", str(tenant_id))
                await conn.execute("""INSERT INTO subscriptions(id,tenant_id,plan_id,status,current_period_start,current_period_end,cancel_at_period_end,metadata)
                  SELECT $1,$2,'growth_monthly','active',now(),now()+interval '30 days',false,'{"synthetic_fixture":true}'
                  WHERE NOT EXISTS (SELECT 1 FROM subscriptions WHERE tenant_id=$2 AND current_period_end>now())""", uuid.uuid4(), tenant_id)
                await conn.execute("UPDATE tenants SET display_name='SYNTHETIC Fashion Remediation', settings=settings || $2::jsonb WHERE id=$1",
                    tenant_id, json.dumps({"currency":"INR", "synthetic_fixture":True}))
        finally:
            await conn.close()

        async def call(method, path, **kw):
            response = await client.request(method, path, **kw)
            response.raise_for_status()
            return response.json()

        await call("PUT", "/onboarding/state", json={"status":"complete"})

        existing = await call("GET", "/skus")
        skus = existing if isinstance(existing, list) else existing.get("items", existing.get("skus", []))
        by_code = {s["sku_code"]: s for s in skus}
        with (AUDIT / "synthetic-training-sales.csv").open(newline="", encoding="utf-8") as file:
            source_rows = list(csv.DictReader(file))
        economics = {}
        for row in source_rows:
            if int(row["quantity"]) > 0:
                economics[row["sku"]] = {"code":row["sku"],"unit_price":float(row["price"]),
                    "unit_cost":float(row["cogs"])/int(row["quantity"])}
        manifest = list(economics.values())
        for item in [*manifest, {"code":"UNSOLD-5XL", "unit_price":999, "unit_cost":500}]:
            code = item["code"]
            if code not in by_code:
                product = await call("POST", "/products", json={"name":f"SYNTHETIC {code}","category":"Fashion fixture",
                    "attributes":{"sample_data":True}})
                by_code[code] = await call("POST", f"/skus/{product['id']}/skus", json={
                    "sku_code":code,"unit_price":item["unit_price"],"unit_cost":item["unit_cost"],"currency":"INR",
                    "lead_time_days":14,"moq":6,"attributes":{"size":"5XL" if code=="UNSOLD-5XL" else code.split("-")[-1],"sample_data":True}})
        await call("PUT", "/inventory/levels", json={"items":[{"sku_id":s["id"],"on_hand_units":stock,
            "location":loc,"source":"synthetic_remediation"} for s in by_code.values()
            for loc,stock in [("Boduppal",1),("Alwal",12)]]})
        # Split each total across locations without changing portfolio demand.
        for name in ["synthetic-training-sales.csv", "synthetic-heldout-sales.csv"]:
            with (AUDIT/name).open(newline="", encoding="utf-8") as file:
                rows = list(csv.DictReader(file))
            prepared = []
            for row in rows:
                total = int(row["quantity"])
                first = round(total*.7)
                for location, units in [("Boduppal", first),("Alwal", total-first)]:
                    prepared.append({**row,"quantity":units,"revenue":units*float(row["price"]),
                        "location":location,"channel":"synthetic","order_id":f"{row['order_id']}-{location}","currency":"INR"})
            with (OUT/name).open("w",newline="",encoding="utf-8") as file:
                writer = csv.DictWriter(file, fieldnames=list(prepared[0]))
                writer.writeheader()
                writer.writerows(prepared)
        (OUT/"fixture.json").write_text(json.dumps({"synthetic":True,"slug":slug,"email":email,
            "password":password,"tenant_id":str(tenant_id),"skus":by_code},indent=2),encoding="utf-8")
        print(f"Prepared SYNTHETIC fixture {slug}; sales files require UI import. RLS enforced.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-port", type=int, required=True)
    parser.add_argument("--slug", default="synthetic-remediation")
    args = parser.parse_args()
    asyncio.run(seed(args.db_port, args.slug))
