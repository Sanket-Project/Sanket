"""Recover pre-SMTP claims while preserving ambiguous DATA acceptance."""

from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE communication_deliveries DROP CONSTRAINT communication_deliveries_state_check"
    )
    op.execute(
        "ALTER TABLE communication_deliveries ADD CONSTRAINT communication_deliveries_state_check CHECK(state IN ('claimed','sending','sent','failed','ambiguous','unavailable'))"
    )
    op.execute(
        "ALTER TABLE communication_deliveries ADD COLUMN lease_until timestamptz, ADD COLUMN lease_token uuid, ADD COLUMN attempts integer NOT NULL DEFAULT 0 CHECK(attempts>=0)"
    )


def downgrade():
    op.execute("UPDATE communication_deliveries SET state='failed' WHERE state='claimed'")
    op.execute(
        "ALTER TABLE communication_deliveries DROP COLUMN lease_until, DROP COLUMN lease_token, DROP COLUMN attempts"
    )
    op.execute(
        "ALTER TABLE communication_deliveries DROP CONSTRAINT communication_deliveries_state_check"
    )
    op.execute(
        "ALTER TABLE communication_deliveries ADD CONSTRAINT communication_deliveries_state_check CHECK(state IN ('sending','sent','failed','ambiguous','unavailable'))"
    )
