from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog
from app.models.enums import IndustryCode

log = structlog.get_logger(__name__)


async def record(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    action: str,
    entity_type: str,
    user_id: uuid.UUID | None = None,
    industry: IndustryCode | None = None,
    entity_id: str | None = None,
    old_value: dict[str, Any] | None = None,
    new_value: dict[str, Any] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> None:
    """Insert an immutable audit log entry. Errors are swallowed and logged
    so that audit failures never break primary business logic."""
    try:
        await session.execute(
            insert(AuditLog).values(
                tenant_id=tenant_id,
                user_id=user_id,
                industry=industry,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                old_value=old_value,
                new_value=new_value,
                ip_address=ip_address,
                user_agent=user_agent,
                request_id=request_id,
            )
        )
    except Exception as exc:
        log.error(
            "audit.write.failed",
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            error=str(exc),
        )
