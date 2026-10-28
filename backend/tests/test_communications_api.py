import asyncio
import uuid
from unittest.mock import patch

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError


async def test_preferences_are_server_persisted_and_self_only(
    client, signed_in_workspace, db_session
):
    tenant, headers = await signed_in_workspace()
    response = await client.get("/api/v1/communications/preferences", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["preferences"]["weekly_enabled"] is False
    payload = {
        "language": "te",
        "weekly_enabled": False,
        "timezone": "Asia/Kolkata",
        "send_hour": 8,
    }
    response = await client.put("/api/v1/communications/preferences", headers=headers, json=payload)
    assert response.status_code == 200, response.text
    assert (await client.get("/api/v1/communications/preferences", headers=headers)).json()[
        "preferences"
    ] == payload
    response = await client.put(
        "/api/v1/communications/preferences",
        headers=headers,
        json={**payload, "user_id": str(uuid.uuid4())},
    )
    assert response.status_code == 422


async def test_preferences_invalid_timezone_is_validation_error(client, signed_in_workspace):
    _, headers = await signed_in_workspace()
    response = await client.put(
        "/api/v1/communications/preferences", headers=headers, json={"timezone": "Mars/Base"}
    )
    assert response.status_code == 422


async def test_delivery_preferences_force_rls(db_session, make_tenant, app_role_db):
    from app.services.notifications.communications import read_preferences, write_preferences
    from app.services.notifications.preferences import Preferences

    a, b = await make_tenant(), await make_tenant()
    uid = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO users(id,tenant_id,email,full_name,role,is_active) VALUES(:uid,:tid,'fixture@example.test','Fixture','owner',true)"
        ),
        {"uid": uid, "tid": a},
    )
    await db_session.commit()
    await write_preferences(app_role_db, a, uid, Preferences(language="hi"))
    assert (await read_preferences(app_role_db, a, uid)).language == "hi"
    async with app_role_db.session(str(b)) as session:
        assert (
            await session.scalar(
                text("SELECT count(*) FROM communication_preferences WHERE tenant_id=:tid"),
                {"tid": a},
            )
            == 0
        )
        with pytest.raises(DBAPIError, match="row-level security"):
            await session.execute(
                text(
                    "INSERT INTO communication_deliveries(tenant_id,user_id,delivery_key,content_hash,state) VALUES(:tid,:uid,'foreign','hash','sent')"
                ),
                {"tid": a, "uid": uid},
            )


async def test_delivery_concurrency_sends_once_and_never_retries_ambiguous(
    db_session, make_tenant, app_role_db
):
    from app.services.notifications.communications import deliver_email
    from app.services.notifications.email import EmailConfig

    tenant = await make_tenant()
    uid = uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO users(id,tenant_id,email,full_name,role,is_active) VALUES(:uid,:tid,'sink@example.test','Synthetic','owner',true)"
        ),
        {"uid": uid, "tid": tenant},
    )
    await db_session.commit()
    config = EmailConfig(host="localhost", sender="sanket@example.test")

    async def send(key="one", body="Engine facts"):
        return await deliver_email(
            app_role_db,
            tenant,
            uid,
            key,
            "sink@example.test",
            "Review",
            body,
            confirm=True,
            config=config,
        )

    with patch(
        "app.services.notifications.communications.send_email", return_value="sent"
    ) as transport:
        results = await asyncio.gather(send(), send())
        assert transport.call_count == 1
        assert {result["state"] for result in results} <= {"sent", "pending", "ambiguous"}
        with pytest.raises(ValueError, match="different reviewed"):
            await send(body="Changed after review")
    with patch(
        "app.services.notifications.communications.send_email", return_value="ambiguous"
    ) as transport:
        assert (await send("two"))["state"] == "ambiguous"
        assert (await send("two"))["state"] == "ambiguous"
        assert transport.call_count == 1


async def test_pre_dispatch_lease_recovers_and_rejected_send_retries_are_bounded(
    db_session, make_tenant, app_role_db
):
    from app.services.notifications.communications import deliver_email
    from app.services.notifications.email import EmailConfig

    tenant, uid = await make_tenant(), uuid.uuid4()
    await db_session.execute(
        text(
            "INSERT INTO users(id,tenant_id,email,full_name,role,is_active) VALUES(:uid,:tid,'sink@example.test','Synthetic','owner',true)"
        ),
        {"uid": uid, "tid": tenant},
    )
    await db_session.commit()
    config = EmailConfig(host="localhost", sender="sanket@example.test")

    async def send(key="retry", eligibility=None):
        return await deliver_email(
            app_role_db,
            tenant,
            uid,
            key,
            "sink@example.test",
            "Review",
            "Facts",
            confirm=True,
            config=config,
            eligibility=eligibility,
        )

    with patch(
        "app.services.notifications.communications.send_email", return_value="failed"
    ) as transport:
        assert (await send())["state"] == "failed"
        assert (await send())["state"] == "failed"
        assert (await send())["state"] == "failed"
        assert transport.call_count == 2
    async with app_role_db.session(str(tenant)) as session:
        row = (
            (
                await session.execute(
                    text(
                        "SELECT content_hash FROM communication_deliveries WHERE tenant_id=:tid AND user_id=:uid AND delivery_key='retry'"
                    ),
                    {"tid": tenant, "uid": uid},
                )
            )
            .mappings()
            .one()
        )
        await session.execute(
            text(
                "INSERT INTO communication_deliveries(tenant_id,user_id,delivery_key,content_hash,state,lease_until) VALUES(:tid,:uid,'recover',:digest,'claimed',clock_timestamp()-interval '1 second')"
            ),
            {"tid": tenant, "uid": uid, "digest": row["content_hash"]},
        )
    with patch(
        "app.services.notifications.communications.send_email", return_value="sent"
    ) as transport:
        assert (await send("recover"))["state"] == "sent"
        assert transport.call_count == 1

    async def revoked(session, user):
        raise ValueError("Opt-in revoked")

    with patch(
        "app.services.notifications.communications.send_email", return_value="sent"
    ) as transport:
        with pytest.raises(ValueError, match="Opt-in revoked"):
            await send("revoked", eligibility=revoked)
        transport.assert_not_called()
    checks = 0

    async def revoke_after_claim(session, user):
        nonlocal checks
        checks += 1
        if checks == 2:
            raise ValueError("Revoked before SMTP DATA")

    def transport_with_data_boundary(*args):
        args[-1]()
        raise AssertionError("SMTP DATA must not run after revocation")

    with patch(
        "app.services.notifications.communications.send_email",
        side_effect=transport_with_data_boundary,
    ):
        with pytest.raises(ValueError, match="Revoked before SMTP DATA"):
            await send("revoked-before-data", eligibility=revoke_after_claim)
    assert checks == 2
