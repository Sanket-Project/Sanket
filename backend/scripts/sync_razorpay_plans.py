"""Utility script to synchronize database plans with Razorpay API.

Creates Razorpay plans via the Razorpay REST API for active plans in the
`plans` table that do not yet have a `razorpay_plan_id`, and saves the
generated IDs back to PostgreSQL.
"""

from __future__ import annotations

import asyncio
import os
import sys

# Add backend directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import structlog
from sqlalchemy import select

from app.config import get_settings
from app.core.database import Database
from app.models.billing import Plan
from app.services.billing.razorpay_client import get_razorpay_client

log = structlog.get_logger(__name__)


async def main() -> None:
    settings = get_settings()
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        log.error("RAZORPAY_KEY_ID or RAZORPAY_KEY_SECRET is not configured in environment.")
        sys.exit(1)

    client = get_razorpay_client(settings)
    rzp_module = client._module()

    db = Database(settings)

    async with db.session_no_rls() as session:
        res = await session.execute(select(Plan).where(Plan.is_active.is_(True)))
        plans = res.scalars().all()

        synced_count = 0
        for plan in plans:
            if plan.base_price_cents == 0:
                log.info("Skipping free/enterprise plan", plan_id=plan.id)
                continue

            if plan.razorpay_plan_id:
                log.info(
                    "Plan already has razorpay_plan_id",
                    plan_id=plan.id,
                    rzp_id=plan.razorpay_plan_id,
                )
                continue

            period = "yearly" if plan.billing_interval == "year" else "monthly"
            data = {
                "period": period,
                "interval": 1,
                "item": {
                    "name": f"SANKET {plan.display_name}",
                    "amount": plan.base_price_cents,
                    "currency": "INR",
                    "description": f"Subscription plan for {plan.display_name}",
                },
            }

            def _create(p_data: dict) -> dict:
                return rzp_module.plan.create(data=p_data)

            rzp_plan = await asyncio.to_thread(_create, data)
            rzp_plan_id = rzp_plan["id"]
            plan.razorpay_plan_id = rzp_plan_id
            synced_count += 1
            log.info("Created Razorpay plan", plan_id=plan.id, razorpay_plan_id=rzp_plan_id)

        if synced_count > 0:
            await session.commit()
            log.info("Successfully synced plans with Razorpay", count=synced_count)
        else:
            log.info("No plans needed syncing.")

    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
