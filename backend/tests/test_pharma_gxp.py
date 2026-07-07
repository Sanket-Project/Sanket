"""GxP / 21 CFR Part 11 invariants — the kind of failure that would
otherwise only show up in an audit."""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def _setup_pharma_data(
    db: AsyncSession, tenant_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID]:
    await db.execute(
        text("SELECT set_config('app.current_tenant_id', :tid, true)"), {"tid": str(tenant_id)}
    )
    product_id = uuid.uuid4()
    sku_id = uuid.uuid4()
    await db.execute(
        text(
            """
            INSERT INTO products (id, tenant_id, industry, name, category)
            VALUES (:pid, :tid, 'pharma', 'Drug A', 'Antibiotic')
            """
        ),
        {"pid": str(product_id), "tid": str(tenant_id)},
    )
    sku_code = f"DRUG-A-{uuid.uuid4().hex[:8]}"
    await db.execute(
        text(
            """
            INSERT INTO skus (id, tenant_id, product_id, industry, sku_code)
            VALUES (:sid, :tid, :pid, 'pharma', :sku_code)
            """
        ),
        {"sid": str(sku_id), "tid": str(tenant_id), "pid": str(product_id), "sku_code": sku_code},
    )
    await db.flush()
    return product_id, sku_id


async def test_cold_chain_batch_without_temps_rejected_by_constraint(
    db_session: AsyncSession, test_tenant_id: uuid.UUID
) -> None:
    _, sku_id = await _setup_pharma_data(db_session, test_tenant_id)
    with pytest.raises(Exception) as exc:
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    """
                    INSERT INTO pharma_batches (
                        tenant_id, sku_id, lot_number,
                        manufactured_at, expiry_date,
                        quantity_produced, quantity_remaining,
                        cold_chain_required
                    ) VALUES (
                        :tid, :sid, 'LOT-COLD-1',
                        :mfg, :exp,
                        100, 100,
                        TRUE
                    )
                    """
                ),
                {
                    "tid": str(test_tenant_id),
                    "sid": str(sku_id),
                    "mfg": date.today(),
                    "exp": date.today() + timedelta(days=730),
                },
            )
    assert "chk_cold_chain_temps" in str(exc.value) or "check" in str(exc.value).lower()


async def test_expiry_after_manufacture_constraint(
    db_session: AsyncSession, test_tenant_id: uuid.UUID
) -> None:
    _, sku_id = await _setup_pharma_data(db_session, test_tenant_id)
    with pytest.raises(Exception):
        async with db_session.begin_nested():
            await db_session.execute(
                text(
                    """
                    INSERT INTO pharma_batches (
                        tenant_id, sku_id, lot_number,
                        manufactured_at, expiry_date,
                        quantity_produced, quantity_remaining
                    ) VALUES (
                        :tid, :sid, 'LOT-BAD-EXP',
                        :mfg, :exp,
                        100, 100
                    )
                    """
                ),
                {
                    "tid": str(test_tenant_id),
                    "sid": str(sku_id),
                    "mfg": date.today(),
                    "exp": date.today() - timedelta(days=1),
                },
            )


async def test_audit_log_is_append_only(
    db_session: AsyncSession, test_tenant_id: uuid.UUID
) -> None:
    await db_session.execute(
        text("SELECT set_config('app.current_tenant_id', :tid, true)"), {"tid": str(test_tenant_id)}
    )
    await db_session.execute(
        text(
            """
            INSERT INTO audit_log (tenant_id, action, entity_type, entity_id)
            VALUES (:tid, 'test.write', 'test', 'X')
            """
        ),
        {"tid": str(test_tenant_id)},
    )
    await db_session.flush()

    # UPDATE / DELETE are silently NO-OP'd by the SQL RULE — verify by
    # asserting the row still exists and is unchanged.
    await db_session.execute(
        text("UPDATE audit_log SET action = 'tampered' WHERE entity_id = 'X'")
    )
    await db_session.execute(text("DELETE FROM audit_log WHERE entity_id = 'X'"))
    await db_session.flush()

    result = await db_session.execute(
        text("SELECT action FROM audit_log WHERE entity_id = 'X'")
    )
    rows = result.fetchall()
    assert len(rows) >= 1
    assert all(r.action == "test.write" for r in rows)
