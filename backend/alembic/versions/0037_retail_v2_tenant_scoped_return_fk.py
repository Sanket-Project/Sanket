"""Make the V2 return-to-sale relationship tenant scoped.

Revision ID: 0037
Revises: 0036
"""

from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint(
        "uq_v2_sales_events_tenant_id_id",
        "v2_sales_events",
        ["tenant_id", "id"],
    )
    op.drop_constraint(
        "v2_return_events_sale_event_id_fkey",
        "v2_return_events",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_v2_return_events_tenant_sale",
        "v2_return_events",
        "v2_sales_events",
        ["tenant_id", "sale_event_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )


def downgrade():
    op.drop_constraint("fk_v2_return_events_tenant_sale", "v2_return_events", type_="foreignkey")
    op.create_foreign_key(
        "v2_return_events_sale_event_id_fkey",
        "v2_return_events",
        "v2_sales_events",
        ["sale_event_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint("uq_v2_sales_events_tenant_id_id", "v2_sales_events", type_="unique")
