"""Billing P0 guards: plan-owned trial length + one-live-subscription-per-tenant.

Background
----------
Three defects made it possible to obtain a paid workspace without paying:

1. ``plans.razorpay_plan_id`` is NULL for every seeded row (005 never populated
   it, and ``sync_razorpay_plans.py`` only runs once Razorpay creds exist).
   ``SubscriptionManager.start_subscription`` branched on that column and fell
   into the enterprise/custom-billing path, which marks the subscription
   ``active`` without ever contacting Razorpay.
2. ``trial_days`` arrived in the request body, so a caller could ask for 60 days
   on any plan, repeatedly — trial reuse was only blocked in the React layer.
3. Nothing stopped a tenant from holding several live subscriptions at once, so
   a double-submit created two Razorpay subscriptions and billed twice.

This migration supplies the schema half of the fix:

* ``plans.trial_days`` — trial length becomes a property of the plan, set by us,
  instead of a client-supplied number.
* ``uq_subscriptions_one_live_per_tenant`` — a partial unique index that makes
  duplicate live subscriptions unrepresentable rather than merely unlikely. The
  application-level guard races under concurrent requests; this does not.

Existing rows are backfilled with the historical default (14 days on priced
plans, 0 on the ``enterprise_monthly`` custom-billed plan).

Note: if the index creation fails, production already has tenants holding more
than one live subscription — dedupe them before re-running. The query in the
docstring below finds them.

    SELECT tenant_id, count(*) FROM subscriptions
    WHERE status IN ('trialing','active','past_due')
    GROUP BY tenant_id HAVING count(*) > 1;

Revision ID: 0017
Revises: 0016
Create Date: 2026-07-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Statuses that represent a subscription currently occupying a tenant's slot.
# 'paused' is deliberately excluded: Razorpay can pause a mandate for an
# extended period and the tenant should be able to start fresh.
_LIVE_STATUSES = "'trialing', 'active', 'past_due'"


def upgrade() -> None:
    op.add_column(
        "plans",
        sa.Column("trial_days", sa.Integer(), nullable=False, server_default="0"),
    )
    # Preserve the previous behaviour: priced plans offered a 14-day trial.
    op.execute("UPDATE plans SET trial_days = 14 WHERE base_price_cents > 0")

    op.create_index(
        "uq_subscriptions_one_live_per_tenant",
        "subscriptions",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text(f"status IN ({_LIVE_STATUSES})"),
    )


def downgrade() -> None:
    op.drop_index("uq_subscriptions_one_live_per_tenant", table_name="subscriptions")
    op.drop_column("plans", "trial_days")
