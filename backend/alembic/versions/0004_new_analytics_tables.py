"""Add analytics improvement tables: forecast_accuracy_metrics, supplier_lead_time_log,
pos_ingest, data_quality_issues.

Revision ID: 0004
Revises: 0003
Create Date: 2026-05-29
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "forecast_accuracy_metrics",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("sku_id", sa.UUID(), nullable=False),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column("mape", sa.Numeric(8, 4), nullable=True),
        sa.Column("wape", sa.Numeric(8, 4), nullable=True),
        sa.Column("n_obs", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("computed_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_fam_tenant_sku", "forecast_accuracy_metrics", ["tenant_id", "sku_id"])
    op.create_index("idx_fam_tenant_model", "forecast_accuracy_metrics", ["tenant_id", "model_name"])

    op.create_table(
        "supplier_lead_time_log",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("sku_id", sa.UUID(), nullable=False),
        sa.Column("supplier_id", sa.Text(), nullable=True),
        sa.Column("promised_lead_time_days", sa.SmallInteger(), nullable=False),
        sa.Column("actual_lead_time_days", sa.SmallInteger(), nullable=True),
        sa.Column("variance_days", sa.Integer(), nullable=True),
        sa.Column("order_date", sa.Date(), nullable=False),
        sa.Column("receipt_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_sltl_tenant_sku", "supplier_lead_time_log", ["tenant_id", "sku_id"])

    op.create_table(
        "pos_ingest",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("sku_id", sa.UUID(), nullable=False),
        sa.Column("sale_time", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("units_sold", sa.Integer(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=False, server_default="pos"),
        sa.Column("region", sa.Text(), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("ingested_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("quality_score", sa.Numeric(5, 4), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_pos_tenant_sku", "pos_ingest", ["tenant_id", "sku_id", "sale_time"])

    op.create_table(
        "data_quality_issues",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.Text(), nullable=True),
        sa.Column("issue_code", sa.Text(), nullable=False),
        sa.Column("issue_message", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False, server_default="warning"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_dqi_entity", "data_quality_issues", ["entity_type", "entity_id"])
    op.create_index("idx_dqi_tenant", "data_quality_issues", ["tenant_id", "created_at"])


def downgrade() -> None:
    op.drop_table("data_quality_issues")
    op.drop_table("pos_ingest")
    op.drop_table("supplier_lead_time_log")
    op.drop_table("forecast_accuracy_metrics")
