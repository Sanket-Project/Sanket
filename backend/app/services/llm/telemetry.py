from __future__ import annotations

import uuid
from typing import Literal, get_args

import structlog
from sqlalchemy import select, text

from app.config import Settings
from app.models.billing import MeterKind
from app.models.tenant import User
from app.services import audit
from app.services import usage as metering
from app.services.llm.errors import AIError, Reason, TokenUsage
from app.services.llm.policy import AIContext, Policy
from app.services.llm.tasks import get_task

log = structlog.get_logger(__name__)


class Telemetry:
    def __init__(self, db, settings: Settings):
        self.db, self.settings = db, settings

    async def record(self, ctx: AIContext, attempt: uuid.UUID,
                     event: Literal["started", "finished", "cache_hit", "blocked"], *,
                     policy: Policy, usage: TokenUsage | None = None,
                     reason: Reason | None = None, latency_ms: int = 0) -> None:
        if (not isinstance(attempt, uuid.UUID) or event not in {"started", "finished", "cache_hit", "blocked"}
                or (reason is not None and reason not in get_args(Reason))
                or type(latency_ms) is not int or not 0 <= latency_ms <= 120000):
            raise AIError("invalid_input")
        action = f"ai.call.{event}"
        try:
            # A separate transaction prevents telemetry failures poisoning domain writes.
            async with self.db.session(str(ctx.tenant_id)) as session:
                member = await session.scalar(select(User.id).where(
                    User.id == ctx.user_id, User.tenant_id == ctx.tenant_id, User.is_active.is_(True)))
                if member is None:
                    raise AIError("invalid_context")
                await session.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                                      {"key": f"llm:{ctx.tenant_id}:{attempt}:{event}"})
                exists = await session.scalar(text("""SELECT 1 FROM audit_log WHERE tenant_id=:tid
                    AND request_id=:id AND action=:action LIMIT 1"""),
                                              {"tid": ctx.tenant_id, "id": str(attempt), "action": action})
                if exists:
                    return
                if event == "finished" and usage is not None:
                    for meter, quantity in [(MeterKind.llm_input_token, usage.input_tokens),
                                            (MeterKind.llm_output_token, usage.output_tokens)]:
                        await metering.record(session, tenant_id=ctx.tenant_id, meter=meter,
                                              quantity=quantity, strict=True,
                                              idempotency_key=f"llm:{attempt}:{meter.value}",
                                              metadata={"task": ctx.task_name, "attempt": str(attempt)})
                await audit.record(
                    session, tenant_id=ctx.tenant_id, user_id=ctx.user_id, industry=ctx.industry,
                    action=action, entity_type="llm", entity_id=str(attempt), request_id=str(attempt), strict=True,
                    new_value={"task": ctx.task_name, "model": self.settings.llm_model,
                               "schema_version": get_task(ctx.task_name).schema_version, "sharing": policy.sharing, "latency_ms": latency_ms,
                               "cache_hit": event == "cache_hit", "reason": reason,
                               "usage_known": usage is not None,
                               "input_tokens": usage.input_tokens if usage else None,
                               "output_tokens": usage.output_tokens if usage else None},
                )
        except AIError:
            raise
        except Exception:
            log.error("ai.accounting.failed", attempt_id=str(attempt), tenant_id=str(ctx.tenant_id))
            raise AIError("accounting_unavailable") from None
