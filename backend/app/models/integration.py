from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKey
from app.models.enums import IndustryCode


class IntegrationConnection(UUIDPrimaryKey, TimestampMixin, Base):
    """A per-tenant link to an external data source (e.g. Shopify).

    One row per (tenant, provider) for the MVP. The access token is stored
    encrypted (see app.core.crypto); ``state`` holds provider sync cursors so
    incremental sync can resume, and ``last_sync_stats`` records the row counts
    from the most recent backfill for the UI.
    """

    __tablename__ = "integration_connections"
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider", name="uq_integration_tenant_provider"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    # Provider key, e.g. "shopify". Kept as TEXT (not an enum) so adding a new
    # provider doesn't require a DB migration.
    provider: Mapped[str] = mapped_column(Text, nullable=False)
    # connected | syncing | error | disconnected
    status: Mapped[str] = mapped_column(Text, nullable=False, default="disconnected")
    shop_domain: Mapped[str | None] = mapped_column(Text)
    access_token_encrypted: Mapped[str | None] = mapped_column(Text)
    # Which industry synced products/SKUs/sales land in.
    target_industry: Mapped[IndustryCode] = mapped_column(
        SAEnum(IndustryCode, name="industry_code"), nullable=False
    )
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_status: Mapped[str | None] = mapped_column(Text)
    last_sync_stats: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)
    state: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
