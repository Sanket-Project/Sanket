import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.notifications.communications import (
    deliver_email,
    read_preferences,
)
from app.services.notifications.email import EmailConfig


class DB:
    def __init__(self, member):
        self.member = member
        self.session_obj = SimpleNamespace(
            scalar=AsyncMock(return_value=member), execute=AsyncMock(), flush=AsyncMock()
        )
        self.scopes = []

    @asynccontextmanager
    async def session(self, scope):
        self.scopes.append(scope)
        yield self.session_obj


async def test_missing_or_inactive_member_cannot_use_preferences():
    tid, uid = uuid.uuid4(), uuid.uuid4()
    db = DB(None)
    with pytest.raises(ValueError, match="membership"):
        await read_preferences(db, tid, uid)
    assert db.scopes == [str(tid)]


async def test_send_requires_explicit_confirmation_before_db_or_transport():
    db = DB(None)
    with pytest.raises(ValueError, match="Confirm"):
        await deliver_email(
            db,
            uuid.uuid4(),
            uuid.uuid4(),
            "test-key",
            "qa@example.test",
            "Review",
            "Facts",
            confirm=False,
            config=EmailConfig(),
        )
    assert not db.scopes


async def test_viewer_cannot_send_even_when_confirmed():
    tid, uid = uuid.uuid4(), uuid.uuid4()
    db = DB(SimpleNamespace(id=uid, tenant_id=tid, role="viewer", is_active=True))
    with pytest.raises(ValueError, match="permission"):
        await deliver_email(
            db,
            tid,
            uid,
            "test-key",
            "qa@example.test",
            "Review",
            "Facts",
            confirm=True,
            config=EmailConfig(),
        )


async def test_server_preferences_are_default_off_and_self_scoped():
    tid, uid = uuid.uuid4(), uuid.uuid4()
    member = SimpleNamespace(id=uid, tenant_id=tid, role="analyst", is_active=True)
    db = DB(member)
    db.session_obj.scalar.side_effect = [member, None]
    prefs = await read_preferences(db, tid, uid)
    assert prefs.language == "en"
    assert not prefs.weekly_enabled
    assert db.scopes == [str(tid)]
