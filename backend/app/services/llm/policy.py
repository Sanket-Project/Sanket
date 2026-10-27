from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import select

from app.models.enums import IndustryCode
from app.models.industry import IndustryProfile
from app.models.tenant import Tenant, User
from app.services.llm.contracts import TaskInput
from app.services.llm.errors import AIError

Sharing = Literal["disabled", "headers_only", "redacted_samples"]


@dataclass(frozen=True)
class AIContext:
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    industry: IndustryCode
    task_name: str = "import_mapping"

    def __post_init__(self):
        if not (isinstance(self.tenant_id, uuid.UUID) and isinstance(self.user_id, uuid.UUID)
                and isinstance(self.industry, IndustryCode)):
            raise AIError("invalid_context")
        from app.services.llm.tasks import TASK_NAMES
        if self.task_name not in TASK_NAMES:
            raise AIError("invalid_input")


@dataclass(frozen=True)
class Policy:
    enabled: bool
    task_enabled: bool
    sharing: Sharing
    aggregate_context: bool = False
    product_names: bool = False


def resolve_policy(industry: str, flags: Any, settings: Any, *, task_name: str = "import_mapping") -> Policy:
    from app.services.llm.tasks import TASK_NAMES
    if task_name not in TASK_NAMES:
        raise AIError("invalid_input")
    flags = flags if isinstance(flags, dict) else {}
    if not isinstance(settings, dict):
        return Policy(False, False, "disabled")
    ai = settings.get("ai", {})
    if not isinstance(ai, dict):
        return Policy(False, False, "disabled")
    sharing = ai.get("data_sharing_level", "disabled" if industry == "pharma" else "headers_only")
    if sharing not in {"disabled", "headers_only", "redacted_samples"}:
        sharing = "disabled"
    return Policy(flags.get("ai_enabled") is True, flags.get(f"ai_{task_name}") is True, sharing,
                  sharing != "disabled" and ai.get("allow_aggregate_context") is True,
                  sharing != "disabled" and ai.get("allow_product_names") is True)


class PolicyStore:
    def __init__(self, db):
        self.db = db

    async def _rows(self, session, ctx: AIContext, *, lock: bool = False):
        query = select(User).where(
            User.id == ctx.user_id, User.tenant_id == ctx.tenant_id, User.is_active.is_(True))
        # Serialize sharing/flag changes with role demotion or deactivation,
        # rather than authorizing from an earlier committed membership snapshot.
        user = await session.scalar(query.with_for_update() if lock else query)
        if user is None:
            raise AIError("invalid_context")
        query = select(Tenant).where(Tenant.id == ctx.tenant_id, Tenant.industry == ctx.industry)
        tenant = await session.scalar(query.with_for_update() if lock else query)
        if tenant is None:
            raise AIError("invalid_context")
        query = select(IndustryProfile).where(
            IndustryProfile.tenant_id == ctx.tenant_id, IndustryProfile.industry == ctx.industry)
        profile = await session.scalar(query.with_for_update() if lock else query)
        return user, tenant, profile

    async def load(self, ctx: AIContext) -> Policy:
        async with self.db.session(str(ctx.tenant_id)) as session:
            _, tenant, profile = await self._rows(session, ctx)
            return resolve_policy(ctx.industry.value, profile.feature_flags if profile else {}, tenant.settings,
                                  task_name=ctx.task_name)

    async def describe(self, ctx: AIContext) -> dict:
        from app.services.llm.tasks import TASK_NAMES
        async with self.db.session(str(ctx.tenant_id)) as session:
            user, tenant, profile = await self._rows(session, ctx)
            flags = profile.feature_flags if profile else {}
            policy = resolve_policy(ctx.industry.value, flags, tenant.settings)
            return {"enabled": policy.enabled, "sharing": policy.sharing,
                    "tasks": {name: (flags or {}).get(f"ai_{name}") is True for name in sorted(TASK_NAMES)},
                    "aggregate_context": policy.aggregate_context, "product_names": policy.product_names,
                    "can_manage": user.role in {"owner", "admin"}}

    async def configure(self, ctx: AIContext, *, enabled: bool, tasks: dict[str, bool], sharing: Sharing,
                        aggregate_context: bool, product_names: bool) -> None:
        from app.services import audit
        from app.services.llm.tasks import TASK_NAMES
        if (any(type(v) is not bool for v in (enabled, aggregate_context, product_names))
                or not isinstance(tasks, dict) or not set(tasks) <= TASK_NAMES
                or any(type(v) is not bool for v in tasks.values())
                or sharing not in {"disabled", "headers_only", "redacted_samples"}):
            raise AIError("invalid_input")
        async with self.db.session(str(ctx.tenant_id)) as session:
            user, tenant, profile = await self._rows(session, ctx, lock=True)
            if user.role not in {"owner", "admin"}:
                raise AIError("invalid_context")
            if profile is None:
                profile = IndustryProfile(tenant_id=ctx.tenant_id, industry=ctx.industry, feature_flags={})
                session.add(profile)
            flags = dict(profile.feature_flags or {})
            flags.update({f"ai_{name}": value for name, value in tasks.items()})
            flags["ai_enabled"] = enabled
            settings = dict(tenant.settings or {})
            previous = settings.get("ai")
            settings["ai"] = {**(previous if isinstance(previous, dict) else {}),
                              "data_sharing_level": sharing, "allow_aggregate_context": aggregate_context,
                              "allow_product_names": product_names}
            tenant.settings, profile.feature_flags = settings, flags
            await audit.record(session, tenant_id=ctx.tenant_id, user_id=ctx.user_id, industry=ctx.industry,
                               action="ai.policy.updated", entity_type="workspace", entity_id=str(ctx.tenant_id),
                               strict=True, new_value={"enabled": enabled, "tasks": tasks, "sharing": sharing,
                                                       "aggregate_context": aggregate_context, "product_names": product_names})

    async def update(self, ctx: AIContext, *, enabled: bool, task_enabled: bool, sharing: Sharing) -> Policy:
        from app.services import audit

        if (type(enabled) is not bool or type(task_enabled) is not bool
                or sharing not in {"disabled", "headers_only", "redacted_samples"}):
            raise AIError("invalid_input")
        async with self.db.session(str(ctx.tenant_id)) as session:
            user, tenant, profile = await self._rows(session, ctx, lock=True)
            if user.role not in {"owner", "admin"}:
                raise AIError("invalid_context")
            if profile is None:
                profile = IndustryProfile(tenant_id=ctx.tenant_id, industry=ctx.industry, feature_flags={})
                session.add(profile)
            flags = dict(profile.feature_flags or {})
            flags.update(ai_enabled=enabled, ai_import_mapping=task_enabled)
            settings = dict(tenant.settings or {})
            ai = settings.get("ai", {})
            settings["ai"] = {**(ai if isinstance(ai, dict) else {}), "data_sharing_level": sharing}
            profile.feature_flags = flags
            tenant.settings = settings
            await audit.record(session, tenant_id=ctx.tenant_id, user_id=ctx.user_id,
                               industry=ctx.industry, action="ai.policy.updated", entity_type="workspace",
                               entity_id=str(ctx.tenant_id), strict=True,
                               new_value={"enabled": enabled, "task_enabled": task_enabled,
                                          "sharing": sharing})
            return Policy(enabled, task_enabled, sharing)


_CONTACT = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|(?:\+?\d[\d\s()-]{7,}\d)")


def project_input(task: TaskInput, policy: Policy, rows: list[dict] | None = None) -> dict:
    """Allowlisted structural hints only. No actual transaction cell values leave."""
    if policy.sharing == "disabled":
        raise AIError("sharing_disabled")
    columns = [{"id": c.id, "label": _CONTACT.sub("[redacted]", c.label), "kind": c.kind}
               for c in task.columns]
    result = {"columns": columns, "allowed_fields": list(task.allowed_fields)}
    if policy.sharing == "redacted_samples" and rows:
        # Repeated text values get local opaque tokens. Unknown text is never copied.
        tokens: dict[str, str] = {}
        examples = []
        for row in rows[:3]:
            example = {}
            for column in task.columns:
                cell = row.get(column.id)
                if cell is None:
                    hint = "missing"
                elif isinstance(cell, bool):
                    hint = "boolean"
                elif isinstance(cell, (int, float)):
                    hint = "integer" if isinstance(cell, int) else "decimal"
                else:
                    # A local token carries repetition, not the original value.
                    key = str(cell)[:512]
                    hint = tokens.setdefault(key, f"text_{len(tokens) + 1}")
                example[column.id] = hint
            examples.append(example)
        result["examples"] = examples
    return result
