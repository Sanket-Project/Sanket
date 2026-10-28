"""Durable tenant/user scoped recurring jobs; no cross-tenant database access."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import text

from app.config import get_settings
from app.models.enums import IndustryCode
from app.services.llm.context import Ledger
from app.services.llm.facts import render_narrative
from app.services.llm.policy import AIContext, PolicyStore, resolve_policy
from app.services.llm.tasks import request_for
from app.services.notifications.communications import deliver_email, load_member, read_preferences
from app.services.notifications.email import EmailConfig
from app.services.notifications.localization import translate
from app.services.notifications.preferences import Preferences, delivery_key, next_delivery


async def schedule_weekly(queue, tenant_id, user_id, industry, prefs, *, now=None):
    if not prefs.weekly_enabled or queue is None:
        return None
    due = next_delivery(now or datetime.now(UTC), prefs.timezone, prefs.send_hour)
    await queue.enqueue_job(
        "run_weekly_summary",
        str(tenant_id),
        str(user_id),
        industry,
        due.isoformat(),
        _job_id=f"weekly:{tenant_id}:{user_id}:{due.isoformat()}",
        _defer_until=due,
    )
    return due


async def weekly_context(db, ctx, language):
    from app.services.roi import summary

    ledger = Ledger()
    async with db.session(str(ctx.tenant_id)) as session:
        await load_member(session, ctx.tenant_id, ctx.user_id)
        report = await summary(
            session, tenant_id=ctx.tenant_id, industry=ctx.industry.value, window_days=7
        )
    for line in report["lines"]:
        currencies = line.get("values_by_currency") or {}
        if currencies:
            for currency, value in currencies.items():
                ledger.add(
                    line["key"] + "_" + currency,
                    line["label"],
                    value,
                    currency,
                    "/roi",
                    period="7 days",
                )
        else:
            ledger.add(
                line["key"],
                line["label"],
                line["value"],
                line["unit"] if line["unit"] != "currency" else "",
                "/roi",
                period="7 days",
            )
    for key, value in report["adoption"].items():
        ledger.add(
            key,
            "Accepted recommendations" if key.endswith("accepted") else "Open recommendations",
            value,
            "",
            "/decisions",
            period="7 days",
        )
    return ledger.finish(language)


async def run_weekly_summary(job, tenant_id, user_id, industry, due_iso):
    tid, uid = UUID(tenant_id), UUID(user_id)
    db = job["db"]
    prefs = await read_preferences(db, tid, uid)
    if not prefs.weekly_enabled:
        return {"state": "disabled"}
    due = datetime.fromisoformat(due_iso)
    now = job.get("clock", lambda: datetime.now(UTC))()
    await schedule_weekly(job.get("redis"), tid, uid, industry, prefs, now=max(now, due))
    if due != next_delivery(due - timedelta(seconds=1), prefs.timezone, prefs.send_hour):
        return {"state": "stale_schedule"}
    if now < due or now - due > timedelta(hours=24):
        return {"state": "skipped_window"}
    ctx = AIContext(tid, uid, IndustryCode(industry), task_name="weekly_summary")
    policy = await PolicyStore(db).load(ctx)
    if (
        not policy.enabled
        or not policy.task_enabled
        or not policy.aggregate_context
        or policy.sharing == "disabled"
    ):
        return {"state": "disabled"}
    ai = job.get("ai")
    if ai is None:
        return {"state": "unavailable"}
    data = await weekly_context(db, ctx, prefs.language)
    result = await ai.run(ctx, request_for("weekly_summary", data.model_dump(mode="json")))
    if result.state != "success":
        return {"state": result.state}
    blocks = render_narrative(data, result.value)
    origin = get_settings().billing_callback_base
    body = (
        translate("AI-generated", prefs.language)
        + "\n\n"
        + "\n".join(
            block["text"]
            + " "
            + " ".join(origin + "/workspace" + source["href"] for source in block["sources"])
            for block in blocks
        )
    )
    current = await read_preferences(db, tid, uid)
    current_policy = await PolicyStore(db).load(ctx)
    if current != prefs or not current.weekly_enabled or current_policy != policy:
        return {"state": "disabled"}
    async with db.session(str(tid)) as session:
        user = await load_member(session, tid, uid)
        recipient = user.email

    async def eligibility(session, user):
        _, tenant, profile = await PolicyStore(db)._rows(session, ctx, lock=True)
        value = await session.scalar(
            text(
                "SELECT preferences FROM communication_preferences WHERE tenant_id=:tid AND user_id=:uid FOR UPDATE"
            ),
            {"tid": tid, "uid": uid},
        )
        actual = Preferences.model_validate(value or {})
        actual_policy = resolve_policy(
            industry,
            profile.feature_flags if profile else {},
            tenant.settings,
            task_name="weekly_summary",
        )
        if actual != prefs or not actual.weekly_enabled or actual_policy != policy:
            raise ValueError("Weekly preference or AI policy changed before dispatch")

    delivery = await deliver_email(
        db,
        tid,
        uid,
        "weekly:" + delivery_key(due, prefs.timezone),
        recipient,
        translate("Weekly planning summary", prefs.language),
        body,
        confirm=True,
        config=EmailConfig.from_settings(get_settings()),
        weekly=True,
        eligibility=eligibility,
    )
    if (
        delivery["state"] == "failed"
        and not delivery.get("replayed")
        and job.get("redis") is not None
    ):
        await job["redis"].enqueue_job(
            "run_weekly_summary",
            tenant_id,
            user_id,
            industry,
            due_iso,
            _job_id=f"weekly-retry:{tenant_id}:{user_id}:{due_iso}",
            _defer_until=now + timedelta(minutes=5),
        )
    return delivery
