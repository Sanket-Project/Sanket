"""Add firebase_uid to users and relax password_hash for Firebase auth.

Firebase becomes the identity provider: each user is linked to a Firebase UID
and passwords are owned by Firebase (password_hash retained only for the local
dev-login fallback, hence now nullable).

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-31
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Idempotent: the baseline schema snapshot (sql/002) already defines these on
    # a fresh `alembic upgrade head`, so guard every change. DROP NOT NULL is a
    # no-op when the column is already nullable.
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS firebase_uid TEXT")
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'uq_users_firebase_uid'
            ) THEN
                ALTER TABLE users ADD CONSTRAINT uq_users_firebase_uid UNIQUE (firebase_uid);
            END IF;
        END $$;
        """
    )
    op.execute("ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL")


def downgrade() -> None:
    op.alter_column("users", "password_hash", existing_type=sa.Text(), nullable=False)
    op.drop_constraint("uq_users_firebase_uid", "users", type_="unique")
    op.drop_column("users", "firebase_uid")
