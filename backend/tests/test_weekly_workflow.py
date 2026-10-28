import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.services.notifications.preferences import Preferences
from app.services.notifications.weekly import run_weekly_summary, schedule_weekly


@pytest.mark.parametrize("delivery_state", ["sent", "failed"])
async def test_opted_in_worker_uses_authenticated_address_and_bound_week_identity(delivery_state):
    from contextlib import asynccontextmanager

    from app.services.llm.context import Ledger
    from app.services.llm.contracts import AIResult
    from app.services.llm.facts import NarrativeBlock, NarrativeOutput
    from app.services.llm.policy import Policy

    tid, uid = uuid.uuid4(), uuid.uuid4()
    prefs = Preferences(weekly_enabled=True)
    now = datetime(2026, 11, 2, 2, 30, tzinfo=UTC)
    ledger = Ledger()
    ledger.add("approved", "Accepted recommendations", 7, "", "/decisions", period="7 days")
    task = ledger.finish()
    user = SimpleNamespace(
        id=uid, tenant_id=tid, is_active=True, email="synthetic@example.test", role="owner"
    )

    class DB:
        @asynccontextmanager
        async def session(self, scope):
            assert scope == str(tid)
            yield object()

    ai = SimpleNamespace(
        run=AsyncMock(
            return_value=AIResult(
                state="success",
                value=NarrativeOutput(
                    blocks=[NarrativeBlock(proposition="fact", fact_ids=["approved"])]
                ),
            )
        )
    )
    delivery = AsyncMock(return_value={"state": delivery_state})
    queue = SimpleNamespace(enqueue_job=AsyncMock())
    policy = Policy(True, True, "headers_only", aggregate_context=True)
    with (
        patch("app.services.notifications.weekly.read_preferences", AsyncMock(return_value=prefs)),
        patch("app.services.notifications.weekly.PolicyStore.load", AsyncMock(return_value=policy)),
        patch("app.services.notifications.weekly.weekly_context", AsyncMock(return_value=task)),
        patch("app.services.notifications.weekly.load_member", AsyncMock(return_value=user)),
        patch("app.services.notifications.weekly.deliver_email", delivery),
    ):
        result = await run_weekly_summary(
            {"db": DB(), "ai": ai, "clock": lambda: now, "redis": queue},
            str(tid),
            str(uid),
            "fashion",
            now.isoformat(),
        )
    assert result["state"] == delivery_state
    assert delivery.call_args.args[4] == "synthetic@example.test"
    assert delivery.call_args.args[3].startswith("weekly:")
    assert "Accepted recommendations: 7" in delivery.call_args.args[6]
    assert "/workspace/decisions" in delivery.call_args.args[6]
    ai.run.assert_awaited_once()
    if delivery_state == "failed":
        assert queue.enqueue_job.await_count == 2
        assert queue.enqueue_job.call_args.kwargs["_job_id"].startswith("weekly-retry:")
    else:
        assert queue.enqueue_job.await_count == 1


async def test_disabled_preference_does_not_queue_or_generate():
    queue = SimpleNamespace(enqueue_job=AsyncMock())
    assert (
        await schedule_weekly(queue, uuid.uuid4(), uuid.uuid4(), "fashion", Preferences()) is None
    )
    queue.enqueue_job.assert_not_awaited()


async def test_enabled_schedule_has_scope_and_stable_due_identity():
    queue = SimpleNamespace(enqueue_job=AsyncMock())
    tid, uid = uuid.uuid4(), uuid.uuid4()
    due = await schedule_weekly(
        queue,
        tid,
        uid,
        "fashion",
        Preferences(weekly_enabled=True),
        now=datetime(2026, 10, 27, tzinfo=UTC),
    )
    call = queue.enqueue_job.call_args
    assert call.args[:4] == ("run_weekly_summary", str(tid), str(uid), "fashion")
    assert due.isoformat() in call.kwargs["_job_id"]


async def test_worker_opt_out_rechecked_before_ai_or_send():
    with patch(
        "app.services.notifications.weekly.read_preferences", AsyncMock(return_value=Preferences())
    ):
        assert await run_weekly_summary(
            {"db": object()},
            str(uuid.uuid4()),
            str(uuid.uuid4()),
            "fashion",
            datetime.now(UTC).isoformat(),
        ) == {"state": "disabled"}


def test_weekly_worker_registered_without_requiring_live_queue(monkeypatch):
    from app.config import get_settings

    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    get_settings.cache_clear()
    from app.workers.forecast_worker import WorkerSettings

    assert run_weekly_summary in WorkerSettings.functions
    get_settings.cache_clear()


async def test_job_for_old_delivery_hour_is_rejected_after_preferences_change():
    prefs = Preferences(weekly_enabled=True, send_hour=10)
    due = datetime(2026, 11, 2, 2, 30, tzinfo=UTC)
    with patch("app.services.notifications.weekly.read_preferences", AsyncMock(return_value=prefs)):
        result = await run_weekly_summary(
            {"db": object(), "clock": lambda: due},
            str(uuid.uuid4()),
            str(uuid.uuid4()),
            "fashion",
            due.isoformat(),
        )
    assert result["state"] == "stale_schedule"
