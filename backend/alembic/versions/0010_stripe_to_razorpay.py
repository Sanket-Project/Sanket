"""Rename Stripe billing columns to Razorpay.

Swaps payment provider from Stripe to Razorpay. The `subscription_status`
enum is unchanged — Razorpay's lifecycle is mapped onto it in the app layer.

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-11
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _rename_if_exists(table: str, old: str, new: str) -> None:
    # Idempotent rename: the baseline snapshot (sql/005) already uses the
    # razorpay_* names on a fresh chain, so only rename when the old Stripe-era
    # column is still present.
    op.execute(
        f"""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = '{table}' AND column_name = '{old}'
            ) AND NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = '{table}' AND column_name = '{new}'
            ) THEN
                ALTER TABLE {table} RENAME COLUMN {old} TO {new};
            END IF;
        END $$;
        """
    )


def upgrade() -> None:
    _rename_if_exists("plans", "stripe_price_id", "razorpay_plan_id")
    _rename_if_exists("subscriptions", "stripe_customer_id", "razorpay_customer_id")
    _rename_if_exists("subscriptions", "stripe_subscription_id", "razorpay_subscription_id")


def downgrade() -> None:
    op.alter_column(
        "subscriptions", "razorpay_subscription_id", new_column_name="stripe_subscription_id"
    )
    op.alter_column("subscriptions", "razorpay_customer_id", new_column_name="stripe_customer_id")
    op.alter_column("plans", "razorpay_plan_id", new_column_name="stripe_price_id")
