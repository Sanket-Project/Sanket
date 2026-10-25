"""Refuse to forecast from history that is provably corrupt.

A forecast built on doubled sales history looks exactly as confident as one
built on clean data — the audit's replayed workspace scored 97.45% WAPE while
the dashboard showed nothing wrong. When Data Quality has *proven* duplicates
(rows sharing a record key), every path that turns history into a forecast or a
purchase recommendation stops and says why, instead of quietly inflating demand.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.data_quality_audit import confirmed_duplicate_count


async def assert_forecastable(session: AsyncSession, *, tenant_id: uuid.UUID, industry: str) -> None:
    """Raise 409 while confirmed duplicate sales exist for this tenant/industry."""
    extra = await confirmed_duplicate_count(session, tenant_id=tenant_id, industry=industry)
    if extra:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Duplicate sales detected: {extra} duplicate sales rows from repeated imports "
                "would inflate demand. Remove them in Data Quality (Remove duplicate sales) "
                "before forecasting."
            ),
        )
