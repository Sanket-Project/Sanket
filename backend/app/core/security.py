"""Password hashing helpers.

Firebase owns credential storage and token issuance in production; these Argon2
helpers remain only for the local dev-login fallback and for seeding dev users.
"""

from __future__ import annotations

import structlog
from passlib.context import CryptContext

from app.config import Settings

log = structlog.get_logger(__name__)

_pwd_context: CryptContext | None = None


def _get_pwd_context(settings: Settings) -> CryptContext:
    global _pwd_context
    if _pwd_context is None:
        _pwd_context = CryptContext(
            schemes=["argon2"],
            deprecated="auto",
            argon2__time_cost=settings.argon2_time_cost,
            argon2__memory_cost=settings.argon2_memory_cost,
            argon2__parallelism=settings.argon2_parallelism,
        )
    return _pwd_context


def hash_password(plain: str, settings: Settings) -> str:
    return _get_pwd_context(settings).hash(plain)


def verify_password(plain: str, hashed: str, settings: Settings) -> bool:
    return _get_pwd_context(settings).verify(plain, hashed)


def needs_rehash(hashed: str, settings: Settings) -> bool:
    return _get_pwd_context(settings).needs_update(hashed)
