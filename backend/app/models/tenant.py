from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    Text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import ARRAY, CITEXT, INET, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKey
from app.models.enums import (
    IndustryCode,
    TenantStatus,
    TenantTier,
    UserRole,
)


class Tenant(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "tenants"

    slug: Mapped[str] = mapped_column(CITEXT, unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    tier: Mapped[TenantTier] = mapped_column(
        SAEnum(TenantTier, name="tenant_tier"), nullable=False, default=TenantTier.growth
    )
    status: Mapped[TenantStatus] = mapped_column(
        SAEnum(TenantStatus, name="tenant_status"), nullable=False, default=TenantStatus.trial
    )
    industries: Mapped[list[str]] = mapped_column(
        ARRAY(SAEnum(IndustryCode, name="industry_code")), nullable=False, default=list
    )
    active_industry: Mapped[IndustryCode] = mapped_column(
        SAEnum(IndustryCode, name="industry_code"), nullable=False
    )
    max_skus: Mapped[int] = mapped_column(Integer, nullable=False, default=10000)
    max_users: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=5)
    data_retention_days: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=730)
    settings: Mapped[dict] = mapped_column(
        __import__("sqlalchemy.dialects.postgresql", fromlist=["JSONB"]).JSONB,
        nullable=False,
        default=dict,
    )
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    contract_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    users: Mapped[list[User]] = relationship("User", back_populates="tenant", lazy="raise")
    industry_profiles: Mapped[list[IndustryProfile]] = relationship(  # type: ignore[name-defined]
        "IndustryProfile", back_populates="tenant", lazy="raise"
    )


class User(UUIDPrimaryKey, TimestampMixin, Base):
    __tablename__ = "users"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    # Firebase UID — the join key between a Firebase identity and this row.
    # Nullable so existing rows backfill lazily on first sign-in; unique so a
    # Firebase user maps to at most one tenant user.
    firebase_uid: Mapped[str | None] = mapped_column(Text, unique=True)
    # Nullable now that Firebase owns passwords in production. Still populated
    # for the local dev-login fallback (verified with Argon2).
    password_hash: Mapped[str | None] = mapped_column(Text)
    full_name: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role"), nullable=False, default=UserRole.analyst
    )
    active_industry: Mapped[IndustryCode] = mapped_column(
        SAEnum(IndustryCode, name="industry_code"), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mfa_secret: Mapped[str | None] = mapped_column(Text)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    tenant: Mapped[Tenant] = relationship("Tenant", back_populates="users", lazy="raise")
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        "RefreshToken", back_populates="user", lazy="raise"
    )


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip_address: Mapped[str | None] = mapped_column(INET)
    user_agent: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=__import__("sqlalchemy", fromlist=["func"]).func.now(),
        nullable=False,
    )

    user: Mapped[User] = relationship("User", back_populates="refresh_tokens", lazy="raise")


# Avoid circular import — IndustryProfile is defined in industry.py
# but needs Tenant relationship. The relationship is declared here
# as a forward reference and resolved by SQLAlchemy's mapper.
from app.models.industry import IndustryProfile  # noqa: E402

Tenant.industry_profiles = relationship(  # type: ignore[assignment]
    "IndustryProfile", back_populates="tenant", lazy="raise"
)
