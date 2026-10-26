"""Recreate synthetic revision-0021 data, read-only dump, restore, upgrade.

This is NOT a restore of the unavailable original audit database. It only
creates sanket_legacy_source and sanket_legacy_upgrade in the disposable
sanket-remediation-restore-db container (loopback port 55434). Existing
databases are never replaced. Run with backend/.venv/Scripts/python.exe.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from decimal import Decimal

import asyncpg

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
CONTAINER = "sanket-remediation-restore-db"
SOURCE = "sanket_legacy_source"
TARGET = "sanket_legacy_upgrade"
PORT = 55434
PASSWORD = "remediation-restore-local"  # disposable synthetic fixture only
TENANTS = [uuid.UUID("25a00000-0000-4000-8000-000000000001"), uuid.UUID("25a00000-0000-4000-8000-000000000002")]
SKUS = [uuid.UUID("25b00000-0000-4000-8000-000000000001"), uuid.UUID("25b00000-0000-4000-8000-000000000002")]


def command(args, **kwargs):
    process = subprocess.run(args, capture_output=True, **kwargs)
    if process.returncode:
        raise RuntimeError(f"{args[0]} exited {process.returncode}: {process.stderr.decode(errors='replace')}")
    return process


def admin_sql(database, sql):
    return command(["docker", "exec", CONTAINER, "psql", "-X", "-U", "postgres", "-d", database,
                    "-v", "ON_ERROR_STOP=1", "-Atc", sql]).stdout.decode().strip()


def migrate(database, revision, logfile):
    env = dict(os.environ)
    env["MIGRATION_DATABASE_URL"] = f"postgresql+asyncpg://postgres:{PASSWORD}@127.0.0.1:{PORT}/{database}"
    env["DATABASE_URL"] = f"postgresql+asyncpg://sanket_app:{PASSWORD}@127.0.0.1:{PORT}/{database}"
    result = command([sys.executable, "-m", "alembic", "upgrade", revision], cwd=ROOT / "backend", env=env)
    (OUT / logfile).write_bytes(result.stdout + result.stderr)


async def connect(database):
    return await asyncpg.connect(user="sanket_app", password=PASSWORD, host="127.0.0.1", port=PORT, database=database)


async def seed():
    connection = await connect(SOURCE)
    try:
        role = dict(await connection.fetchrow("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname=current_user"))
        assert not role["rolsuper"] and not role["rolbypassrls"]
        for index, tenant in enumerate(TENANTS):
            async with connection.transaction():
                await connection.execute("SELECT set_config('app.current_tenant_id',$1,true)", str(tenant))
                await connection.execute("INSERT INTO tenants(id,slug,display_name,tier,status,industry,settings) VALUES($1,$2,$3,'growth','active','fashion',$4::jsonb)",
                    tenant, f"synthetic-legacy-upgrade-{index+1}", "SYNTHETIC recreated legacy upgrade fixture", json.dumps({"synthetic_fixture": True}))
                rows = [("u1", "LEGACY-ORDER-1", "1", 5), ("u2", "LEGACY-ORDER-1", "1", 5)]
                if index == 0:
                    rows.extend([("u1", None, None, 7), ("u2", None, None, 7), ("u0", None, None, 0)])
                for ordinal, (upload, order, line, units) in enumerate(rows):
                    metadata = {"source": "synthetic_unkeyed" if units == 0 else "upload", "upload_id": upload,
                                "order_id": order, "line_id": line, "synthetic_fixture": True}
                    await connection.execute("INSERT INTO historical_sales(id,tenant_id,sku_id,industry,sale_time,channel,units_sold,gross_revenue,net_revenue,metadata) VALUES($1,$2,$3,'fashion',$4,'synthetic',$5,$6,$6,$7::jsonb)",
                        uuid.UUID(f"25c00000-0000-4000-8000-{index*100+ordinal+1:012d}"), tenant, SKUS[index],
                        datetime(2026, 8, 24, tzinfo=UTC), units, Decimal(units * 1000), json.dumps(metadata))
    finally:
        await connection.close()


async def inspect(database, upgraded=False):
    connection = await connect(database)
    try:
        role = dict(await connection.fetchrow("SELECT rolsuper,rolbypassrls FROM pg_roles WHERE rolname=current_user"))
        assert not role["rolsuper"] and not role["rolbypassrls"]
        data = []
        for tenant in TENANTS:
            async with connection.transaction():
                await connection.execute("SELECT set_config('app.current_tenant_id',$1,true)", str(tenant))
                rows = await connection.fetch("SELECT id,tenant_id,sku_id,industry,sale_time,channel,region,units_sold,gross_revenue,net_revenue,returns,promo_flag,markdown_pct,in_stock,metadata FROM historical_sales ORDER BY id")
                foreign = await connection.fetchval("SELECT count(*) FROM historical_sales WHERE tenant_id<>$1", tenant)
                assert foreign == 0 and all(r["tenant_id"] == tenant for r in rows)
                stable = [dict(row) for row in rows]
                result = {"tenant_id": str(tenant), "rows": len(rows), "units": sum(r["units_sold"] for r in rows),
                          "foreign_rows_visible": foreign,
                          "content_sha256": hashlib.sha256(json.dumps(stable, sort_keys=True, default=str).encode()).hexdigest()}
                if upgraded:
                    keyed = await connection.fetch("SELECT record_key,count(*) AS copies FROM historical_sales WHERE record_key IS NOT NULL GROUP BY record_key ORDER BY record_key")
                    result["key_groups"] = [dict(row) for row in keyed]
                    result["unkeyed_rows"] = await connection.fetchval("SELECT count(*) FROM historical_sales WHERE record_key IS NULL")
                    assert len(keyed) == (2 if tenant == TENANTS[0] else 1)
                    assert all(row["copies"] == 2 for row in keyed)
                    assert result["unkeyed_rows"] == (1 if tenant == TENANTS[0] else 0)
                data.append(result)
        return {"role": "sanket_app", "role_flags": role, "tenants": data}
    finally:
        await connection.close()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    bindings = json.loads(command(["docker", "inspect", CONTAINER]).stdout)[0]["NetworkSettings"]["Ports"]
    assert any(v["HostPort"] == str(PORT) for v in bindings.get("5432/tcp", [])), "Wrong disposable container binding"
    for database in (SOURCE, TARGET):
        exists = admin_sql("postgres", f"SELECT count(*) FROM pg_database WHERE datname='{database}'")
        if exists != "0":
            raise RuntimeError(f"Refusing to replace existing database {database}")
        admin_sql("postgres", f"CREATE DATABASE {database}")
    migrate(SOURCE, "0021", "legacy-to-0021.log")
    asyncio.run(seed())
    before = asyncio.run(inspect(SOURCE))
    # pg_dump holds a consistent read-only snapshot; source stays revision0021.
    dumped = command(["docker", "exec", "-e", "PGOPTIONS=-c default_transaction_read_only=on", CONTAINER,
                      "pg_dump", "-U", "postgres", "-d", SOURCE, "-Fc"])
    dump_path = OUT / "synthetic-legacy-0021.dump"
    dump_path.write_bytes(dumped.stdout)
    restored = command(["docker", "exec", "-i", CONTAINER, "pg_restore", "-U", "postgres", "-d", TARGET, "--exit-on-error"], input=dumped.stdout)
    (OUT / "legacy-restore.log").write_bytes(restored.stdout + restored.stderr)
    migrate(TARGET, "head", "legacy-upgrade-head.log")
    after = asyncio.run(inspect(TARGET, upgraded=True))
    for old, new in zip(before["tenants"], after["tenants"]):
        assert all(old[key] == new[key] for key in ("rows", "units", "content_sha256")), "Migration changed original sale content"
    source_revision = admin_sql(SOURCE, "SELECT version_num FROM alembic_version")
    target_revision = admin_sql(TARGET, "SELECT version_num FROM alembic_version")
    assert source_revision == "0021" and target_revision == "0024"
    result = {"status": "passed", "synthetic_only": True, "original_audit_database_available": False,
              "source": f"recreated synthetic {SOURCE} on loopback:{PORT}", "target": TARGET,
              "source_revision_unchanged": source_revision, "target_revision": target_revision,
              "dump_sha256": hashlib.sha256(dumped.stdout).hexdigest(), "dump_bytes": len(dumped.stdout),
              "dump_read_only": True, "rows_and_totals_preserved": True, "before": before, "after": after}
    (OUT / "legacy-upgrade-verification.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
