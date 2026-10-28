"""Scoped membership, durable preferences and conservative SMTP idempotency."""

import asyncio
import hashlib
import json
import uuid

from sqlalchemy import select, text

from app.models.tenant import User
from app.services.notifications.email import address, send_email
from app.services.notifications.preferences import Preferences


async def load_member(session, tenant_id, user_id):
    user = await session.scalar(
        select(User)
        .where(User.id == user_id, User.tenant_id == tenant_id, User.is_active.is_(True))
        .with_for_update()
    )
    if user is None or not user.is_active or user.tenant_id != tenant_id or user.id != user_id:
        raise ValueError("Current workspace membership is required")
    return user


async def read_preferences(db, tenant_id, user_id):
    async with db.session(str(tenant_id)) as session:
        await load_member(session, tenant_id, user_id)
        value = await session.scalar(
            text(
                "SELECT preferences FROM communication_preferences WHERE tenant_id=:tid AND user_id=:uid"
            ),
            {"tid": tenant_id, "uid": user_id},
        )
    return Preferences.model_validate(value or {})


async def write_preferences(db, tenant_id, user_id, preferences):
    preferences = Preferences.model_validate(preferences)
    async with db.session(str(tenant_id)) as session:
        await load_member(session, tenant_id, user_id)
        await session.execute(
            text("""INSERT INTO communication_preferences(tenant_id,user_id,preferences)
            VALUES(:tid,:uid,CAST(:prefs AS jsonb)) ON CONFLICT(tenant_id,user_id)
            DO UPDATE SET preferences=EXCLUDED.preferences,updated_at=clock_timestamp()"""),
            {"tid": tenant_id, "uid": user_id, "prefs": preferences.model_dump_json()},
        )
    return preferences


async def deliver_email(
    db,
    tenant_id,
    user_id,
    key,
    recipient,
    subject,
    body,
    *,
    confirm,
    config,
    attachment=None,
    weekly=False,
    eligibility=None,
):
    if confirm is not True:
        raise ValueError("Confirm the reviewed email before sending")
    if not isinstance(key, str) or not 1 <= len(key) <= 160:
        raise ValueError("Invalid delivery identity")
    recipient = address(recipient)
    digest = hashlib.sha256(
        json.dumps(
            [recipient, subject, body, hashlib.sha256(attachment or b"").hexdigest()],
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    lease = uuid.uuid4()
    params = {"tid": tenant_id, "uid": user_id, "key": key, "digest": digest, "lease": lease}

    async def authorize(session):
        user = await load_member(session, tenant_id, user_id)
        if user.role not in {"owner", "admin"} and not weekly:
            raise ValueError("Sending requires administrator permission")
        if weekly and address(user.email) != recipient:
            raise ValueError("Weekly messages use the authenticated member address")
        if eligibility is not None:
            await eligibility(session, user)
        return user

    async with db.session(str(tenant_id)) as session:
        await authorize(session)
        if not config.configured:
            return {"state": "unavailable"}
        result = await session.execute(
            text("""INSERT INTO communication_deliveries(tenant_id,user_id,delivery_key,content_hash,state,lease_token,lease_until,attempts)
            VALUES(:tid,:uid,:key,:digest,'claimed',:lease,clock_timestamp()+interval '30 seconds',1) ON CONFLICT DO NOTHING RETURNING state"""),
            params,
        )
        inserted = result.scalar_one_or_none()
        if inserted is None:
            prior = (
                (
                    await session.execute(
                        text(
                            "SELECT state,content_hash,attempts,lease_until<=clock_timestamp() AS expired FROM communication_deliveries WHERE tenant_id=:tid AND user_id=:uid AND delivery_key=:key FOR UPDATE"
                        ),
                        {"tid": tenant_id, "uid": user_id, "key": key},
                    )
                )
                .mappings()
                .one()
            )
            if prior["content_hash"] != digest:
                raise ValueError(
                    "Delivery identity already belongs to a different reviewed message"
                )
            recoverable = (
                (prior["state"] == "claimed" and prior["expired"])
                or prior["state"] in {"failed", "unavailable"}
            ) and prior["attempts"] < 2
            if not recoverable:
                return {
                    "state": "ambiguous"
                    if prior["state"] == "sending"
                    else ("pending" if prior["state"] == "claimed" else prior["state"]),
                    "replayed": True,
                }
            await session.execute(
                text(
                    "UPDATE communication_deliveries SET state='claimed',lease_token=:lease,lease_until=clock_timestamp()+interval '30 seconds',attempts=attempts+1,updated_at=clock_timestamp() WHERE tenant_id=:tid AND user_id=:uid AND delivery_key=:key"
                ),
                params,
            )

    async def begin_dispatch():
        async with db.session(str(tenant_id)) as session:
            await authorize(session)
            changed = await session.execute(
                text(
                    "UPDATE communication_deliveries SET state='sending',lease_until=NULL,updated_at=clock_timestamp() WHERE tenant_id=:tid AND user_id=:uid AND delivery_key=:key AND state='claimed' AND lease_token=:lease AND lease_until>clock_timestamp() RETURNING state"
                ),
                params,
            )
            if changed.scalar_one_or_none() is None:
                raise ValueError("Delivery lease expired; review retry state")

    # Claim is recoverable through TLS/authentication. The durable sending transition
    # happens immediately before SMTP DATA; uncertain acceptance then requires review.
    loop = asyncio.get_running_loop()

    def before_dispatch():
        asyncio.run_coroutine_threadsafe(begin_dispatch(), loop).result(timeout=15)

    state = await asyncio.to_thread(
        send_email, config, recipient, subject, body, attachment, before_dispatch
    )
    async with db.session(str(tenant_id)) as session:
        await session.execute(
            text(
                "UPDATE communication_deliveries SET state=:state,lease_until=NULL,updated_at=clock_timestamp() WHERE tenant_id=:tid AND user_id=:uid AND delivery_key=:key AND lease_token=:lease"
            ),
            {"state": state, **params},
        )
    return {"state": state}
