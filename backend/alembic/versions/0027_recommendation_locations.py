"""Location-aware decisions: allocation / transfer kinds, origin + destination.

The open-queue uniqueness moves from (tenant, sku, kind) to (tenant, sku, kind,
destination, origin): one SKU legitimately has one allocation per store.

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ZERO = "'00000000-0000-0000-0000-000000000000'::uuid"


def upgrade() -> None:
    op.add_column("recommendations", sa.Column("location_id", postgresql.UUID(as_uuid=True)))
    op.add_column("recommendations",
                  sa.Column("source_location_id", postgresql.UUID(as_uuid=True)))
    op.create_foreign_key("fk_recommendations_location", "recommendations", "locations",
                          ["location_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_recommendations_source_location", "recommendations", "locations",
                          ["source_location_id"], ["id"], ondelete="SET NULL")
    op.drop_constraint("ck_recommendations_kind", "recommendations", type_="check")
    op.create_check_constraint(
        "ck_recommendations_kind", "recommendations",
        "kind IN ('purchase_order', 'excess_stock', 'safety_stock_update', 'allocation', 'transfer')",
    )
    op.execute("DROP INDEX IF EXISTS uq_recommendations_open_per_sku_kind")
    op.execute(
        "CREATE UNIQUE INDEX uq_recommendations_open_per_sku_kind_loc ON recommendations "
        f"(tenant_id, sku_id, kind, COALESCE(location_id, {_ZERO}), "
        f"COALESCE(source_location_id, {_ZERO})) WHERE status = 'open'"
    )
    op.create_index("ix_recommendations_tenant_kind_source", "recommendations",
                    ["tenant_id", "kind", "source_location_id"])


def downgrade() -> None:
    op.drop_index("ix_recommendations_tenant_kind_source", table_name="recommendations")
    op.execute("DROP INDEX IF EXISTS uq_recommendations_open_per_sku_kind_loc")
    op.execute("DELETE FROM recommendations WHERE kind IN ('allocation', 'transfer')")
    op.execute(
        "CREATE UNIQUE INDEX uq_recommendations_open_per_sku_kind "
        "ON recommendations (tenant_id, sku_id, kind) WHERE status = 'open'"
    )
    op.drop_constraint("ck_recommendations_kind", "recommendations", type_="check")
    op.create_check_constraint(
        "ck_recommendations_kind", "recommendations",
        "kind IN ('purchase_order', 'excess_stock', 'safety_stock_update')",
    )
    op.drop_constraint("fk_recommendations_source_location", "recommendations", type_="foreignkey")
    op.drop_constraint("fk_recommendations_location", "recommendations", type_="foreignkey")
    op.drop_column("recommendations", "source_location_id")
    op.drop_column("recommendations", "location_id")
