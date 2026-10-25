"""Migration 0022 backfills record keys for pre-fix upload rows without deleting any.

The SQL backfill must produce exactly the keys the importer computes in Python
(``app.services.sales_identity``); otherwise re-uploading a file that was
imported before the fix would duplicate it all over again.
"""

from __future__ import annotations

import importlib.util
import json
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text

from app.services import sales_identity as si

_MIGRATION = (
    Path(__file__).resolve().parents[1] / "alembic" / "versions" / "0022_sales_record_identity.py"
)


def _backfill_sql() -> str:
    spec = importlib.util.spec_from_file_location("m0022", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module.BACKFILL_SQL


async def _tenant(db, slug: str) -> uuid.UUID:
    tid = uuid.uuid4()
    await db.execute(
        text(
            "INSERT INTO tenants (id, slug, display_name, tier, status, industry) "
            "VALUES (:id, :slug, :name, 'growth', 'active', 'fashion')"
        ),
        {"id": str(tid), "slug": slug, "name": f"{slug} (synthetic test tenant)"},
    )
    return tid


async def _legacy_sale(db, tenant, sku, *, upload, order=None, units=5, source="upload"):
    rid = uuid.uuid4()
    await db.execute(
        text(
            """
            INSERT INTO historical_sales (id, tenant_id, sku_id, industry, sale_time, channel,
                                          units_sold, gross_revenue, net_revenue, metadata)
            VALUES (:id, :t, :s, 'fashion', :ts, 'Boduppal', :u, :g, :n, CAST(:m AS jsonb))
            """
        ),
        {
            "id": str(rid),
            "t": str(tenant),
            "s": str(sku),
            "ts": datetime(2026, 8, 24, tzinfo=UTC),
            "u": units,
            "g": Decimal("6000"),
            "n": Decimal("5900"),
            "m": json.dumps({"source": source, "order_id": order, "upload_id": upload}),
        },
    )
    return rid


def _python_key(sku, *, order=None) -> str:
    return si.base_key(
        source="upload",
        mode="transaction",
        sku_id=sku,
        sale_time=datetime(2026, 8, 24, tzinfo=UTC),
        channel="Boduppal",
        region=None,
        location=None,
        units=5,
        gross=Decimal("6000"),
        net=Decimal("5900"),
        order_id=order,
        line_id=None,
    )


async def test_backfill_keys_match_the_importer_and_delete_nothing(db_session):
    a = await _tenant(db_session, f"mig22-a-{uuid.uuid4().hex[:6]}")
    b = await _tenant(db_session, f"mig22-b-{uuid.uuid4().hex[:6]}")
    sku, sku_b = uuid.uuid4(), uuid.uuid4()

    a_u1_first = await _legacy_sale(db_session, a, sku, upload="u1")
    a_u1_second = await _legacy_sale(db_session, a, sku, upload="u1")  # identical line, same file
    a_u1_order = await _legacy_sale(db_session, a, sku, upload="u1", order="ORD-1")
    a_u2_replay = await _legacy_sale(db_session, a, sku, upload="u2")  # same file uploaded again
    a_u2_order = await _legacy_sale(db_session, a, sku, upload="u2", order="ORD-1")
    a_shopify = await _legacy_sale(db_session, a, sku, upload=None, source="shopify")
    b_row = await _legacy_sale(db_session, b, sku_b, upload="u9")
    await db_session.commit()

    before = await db_session.scalar(
        text("SELECT count(*) FROM historical_sales WHERE tenant_id IN (:a, :b)"),
        {"a": str(a), "b": str(b)},
    )
    await db_session.execute(text(_backfill_sql()))
    await db_session.commit()

    rows = dict(
        (
            await db_session.execute(
                text("SELECT id, record_key FROM historical_sales WHERE tenant_id IN (:a, :b)"),
                {"a": str(a), "b": str(b)},
            )
        ).all()
    )
    after = len(rows)

    fp = _python_key(sku)
    order_key = _python_key(sku, order="ORD-1")
    assert after == before == 7
    assert rows[a_u1_first] == f"{fp}#1"
    assert rows[a_u1_second] == f"{fp}#2"
    assert rows[a_u2_replay] == f"{fp}#1"  # the replayed copy collides: a provable duplicate
    assert rows[a_u1_order] == rows[a_u2_order] == f"{order_key}#1"
    assert rows[a_shopify] is None  # only upload rows are keyed
    assert rows[b_row] == f"{_python_key(sku_b)}#1"


async def test_backfill_is_idempotent(db_session):
    a = await _tenant(db_session, f"mig22-c-{uuid.uuid4().hex[:6]}")
    rid = await _legacy_sale(db_session, a, uuid.uuid4(), upload="u1")
    await db_session.commit()
    await db_session.execute(text(_backfill_sql()))
    first = await db_session.scalar(
        text("SELECT record_key FROM historical_sales WHERE id = :id"), {"id": str(rid)}
    )
    await db_session.execute(text(_backfill_sql()))
    second = await db_session.scalar(
        text("SELECT record_key FROM historical_sales WHERE id = :id"), {"id": str(rid)}
    )
    await db_session.commit()
    assert first is not None
    assert first == second
