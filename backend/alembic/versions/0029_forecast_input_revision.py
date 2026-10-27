"""Capture the committed sales revision observed when a refresh is reserved.

Revision ID: 0029
Revises: 0028
"""
from alembic import op

revision = '0029'
down_revision = '0028'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute('ALTER TABLE forecast_refreshes ADD COLUMN input_revision timestamptz')


def downgrade() -> None:
    op.execute('ALTER TABLE forecast_refreshes DROP COLUMN input_revision')
