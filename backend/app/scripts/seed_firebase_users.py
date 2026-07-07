"""Provision existing SANKET users into Firebase Authentication.

For every active ``users`` row this script:
  1. creates (or fetches) the matching Firebase user by email,
  2. sets custom claims ``{tid, role, ind, industries}`` so issued ID tokens
     drive tenant context with no DB lookup,
  3. writes the Firebase ``uid`` back onto the row.

Idempotent — safe to run repeatedly. No-ops (with a clear log line) when Firebase
is not configured, so it is harmless to call in dev.

Usage:
    python -m app.scripts.seed_firebase_users [--default-password 'Temp@Pass123!']

A default password is only applied to *newly created* Firebase users; existing
Firebase users are left untouched. Newly created users should reset their
password via the Firebase password-reset flow.
"""

from __future__ import annotations

import argparse
import asyncio

import structlog
from sqlalchemy import select, update

from app.config import get_settings
from app.core.database import Database
from app.core.firebase_auth import get_verifier
from app.models.tenant import Tenant, User

log = structlog.get_logger(__name__)


async def seed_firebase_users(default_password: str | None, reset_password: bool = False) -> int:
    settings = get_settings()
    if not settings.firebase_enabled:
        log.warning(
            "seed_firebase_users.skipped",
            reason="Firebase not configured (set FIREBASE_PROJECT_ID / "
            "FIREBASE_CREDENTIALS_PATH). Dev-login fallback remains active.",
        )
        return 0

    verifier = get_verifier()
    db = Database(settings)
    provisioned = 0
    try:
        async with db.session_no_rls() as session:
            users = (await session.scalars(select(User).where(User.is_active.is_(True)))).all()
            # Preload tenants for the industries claim
            tenants = {t.id: t for t in (await session.scalars(select(Tenant))).all()}
            for user in users:
                tenant = tenants.get(user.tenant_id)
                industries = (
                    [i.value if hasattr(i, "value") else str(i) for i in tenant.industries]
                    if tenant
                    else None
                )
                uid = verifier.create_or_get_user(
                    email=user.email,
                    password=default_password,
                    display_name=user.full_name,
                    reset_password=reset_password,
                )
                verifier.set_user_claims(
                    uid,
                    puid=str(user.id),
                    tid=str(user.tenant_id),
                    role=user.role.value,
                    ind=user.active_industry.value,
                    industries=industries,
                )
                await session.execute(
                    update(User).where(User.id == user.id).values(firebase_uid=uid)
                )
                provisioned += 1
                log.info(
                    "seed_firebase_users.provisioned",
                    email=user.email,
                    uid=uid,
                    role=user.role.value,
                )
    finally:
        await db.close()

    log.info("seed_firebase_users.completed", count=provisioned)
    return provisioned


def main() -> None:
    parser = argparse.ArgumentParser(description="Provision SANKET users into Firebase Auth")
    parser.add_argument(
        "--default-password",
        default=None,
        help="Password applied to newly-created Firebase users only.",
    )
    parser.add_argument(
        "--reset-password",
        action="store_true",
        help="Also overwrite the password of users that already exist in "
        "Firebase (use with --default-password). Off by default.",
    )
    args = parser.parse_args()
    asyncio.run(seed_firebase_users(args.default_password, args.reset_password))


if __name__ == "__main__":
    main()
