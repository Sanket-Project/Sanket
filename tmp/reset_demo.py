"""Inspect (default) or reset the swecha-demo workspace and load the 6-store pack. Local dev only.
Usage: reset_demo.py [apply]"""
import asyncio, sys, time
from pathlib import Path
import os
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import create_async_engine
from app.config import get_settings
from app.core.database import Database
from app.models.tenant import Tenant, User
from app.models.enums import IndustryCode
from app.services.integrations.file_import import import_rows, parse_table

DATA = Path(__file__).resolve().parents[1] / "data" / "swecha-6-stores"
WIPE = ["location_forecast_results", "forecast_results", "recommendations", "forecast_runs",
        "historical_sales", "inventory_levels", "skus", "products", "locations", "integration_connections"]
LOADS = [("products", "01-products.csv"), ("sales", "02-sales-train-104-weeks.csv"),
         ("sales", "03-sales-heldout-8-weeks.csv"), ("inventory", "04-inventory-2026-10-26.csv")]

async def counts(session, tid):
    tables = (await session.execute(text("""
        SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        JOIN pg_attribute a ON a.attrelid=c.oid AND a.attname='tenant_id' AND NOT a.attisdropped
        WHERE n.nspname='public' AND c.relkind IN ('r','p') AND NOT c.relispartition ORDER BY 1"""))).scalars().all()
    for tb in tables:
        n = await session.scalar(text(f'SELECT count(*) FROM "{tb}" WHERE tenant_id=:t'), {"t": tid})
        if n: print(f"  {tb:34s} {n}")

async def main():
    apply = len(sys.argv) > 1 and sys.argv[1] == "apply"
    s = get_settings()
    assert s.app_env == "development" and "sanket_recovered_20261026" in s.database_url
    db = Database(s)
    async with db.session_no_rls() as session:
        t = await session.scalar(select(Tenant).where(Tenant.slug == "swecha-demo"))
        tid = t.id
        print("tenant", tid, t.display_name); print("BEFORE"); await counts(session, tid)
    if not apply:
        await db.close(); return
    admin = create_async_engine(os.environ["MIGRATION_DATABASE_URL"])   # maintenance-only; scoped to one tenant
    async with admin.begin() as conn:                    # one transaction: all or nothing
        for tb in WIPE:
            r = await conn.execute(text(f'DELETE FROM "{tb}" WHERE tenant_id=:t'), {"t": tid})
            print(f"deleted {tb}: {r.rowcount}")
        await conn.execute(text("UPDATE tenants SET display_name='Swecha Fashions (test data)' WHERE id=:t"), {"t": tid})
        await conn.execute(text("UPDATE users SET full_name='Swecha Admin' WHERE tenant_id=:t"), {"t": tid})
    await admin.dispose()
    for kind, fn in LOADS:
        t0 = time.time()
        headers, records = parse_table(fn, (DATA / fn).read_bytes())
        stats = await import_rows(db=db, tenant_id=tid, industry=IndustryCode.fashion, kind=kind,
                                  headers=headers, records=records, identity="period", currency="INR")
        short = {k: v for k, v in stats.items() if not isinstance(v, list)}
        errs = stats.get("errors") or []
        print(f"import {fn}: {short} errors={len(errs)} {errs[:3]} ({time.time()-t0:.0f}s)")
    async with db.session_no_rls() as session:
        print("AFTER"); await counts(session, tid)
    await db.close()
asyncio.run(main())
