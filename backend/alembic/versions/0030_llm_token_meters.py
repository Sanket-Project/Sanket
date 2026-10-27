"""Add AI token meters without changing existing billing behavior.

Revision ID: 0030
Revises: 0029
"""
from alembic import op

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE meter_kind ADD VALUE IF NOT EXISTS 'llm_input_token'")
    op.execute("ALTER TYPE meter_kind ADD VALUE IF NOT EXISTS 'llm_output_token'")


def downgrade() -> None:
    # Additive enum labels and append-only usage history deliberately survive.
    # Roll back by disabling AI, retaining an enum-aware application version.
    pass
