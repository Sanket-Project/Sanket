"""Business facts are loaded by the server under the requesting workspace."""
from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal

from app.services.llm.errors import AIError
from app.services.llm.facts import Fact, NarrativeInput, render_narrative
from app.services.llm.policy import AIContext, PolicyStore
from app.services.llm.tasks import request_for


class Ledger:
    def __init__(self):
        self.rows = []

    def add(self, identifier, label, value, unit, source, *, kind="metric", period=None):
        if isinstance(value, (int, float, Decimal)):
            value = format(Decimal(str(value)), "f")
            if "." in value:
                value = value.rstrip("0").rstrip(".")
        self.rows.append(dict(id=identifier, label=label[:240], value=value, unit=unit, source=source,
                              kind=kind, period=period))

    def note(self, identifier, text, source, *, kind="advice"):
        self.add(identifier, text, None, "", source, kind=kind)

    def finish(self, language="en"):
        snapshot = hashlib.sha256(json.dumps(self.rows, sort_keys=True, default=str).encode()).hexdigest()
        return NarrativeInput(snapshot=snapshot, language=language,
                              facts=[Fact(**row, snapshot=snapshot) for row in self.rows])


async def build_context(db, ctx: AIContext, *, entity_id=None, connector=None, language="en", run_id=None) -> NarrativeInput:
    ledger = Ledger()
    async with db.session(str(ctx.tenant_id)) as session:
        await PolicyStore(db)._rows(session, ctx)
        if ctx.task_name == "onboarding":
            from app.services import onboarding_readiness
            from app.connectors import get_spec, grouped_catalog
            report = await onboarding_readiness.readiness(session, tenant_id=ctx.tenant_id, industry=ctx.industry.value)
            for milestone in report["milestones"]:
                for key, value in milestone["metrics"].items():
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        identifier = key if not any(row["id"] == key for row in ledger.rows) else f"{milestone['key']}_{key}"
                        ledger.add(identifier, key.replace("_", " ").capitalize(), value, "", "/onboarding")
            if not any(row["id"] == "skus_with_stock" and row["value"] != "0" for row in ledger.rows):
                ledger.note("inventory_gap", "No inventory positions are recorded. Upload inventory to ground reorder decisions.", "/onboarding", kind="data_gap")
            if connector:
                spec = get_spec(connector.strip().casefold())
                if spec is None:
                    matches = [s for group in grouped_catalog() for s in group.connectors
                               if any(re.search(r"(?<!\w)" + re.escape(name.casefold()) + r"(?!\w)", connector.casefold())
                                      for name in (s.key, s.name))]
                    spec = matches[0] if len(matches) == 1 else None
                if spec is None:
                    raise ValueError("Unknown connector")
                ledger.add("connector_status", f"{spec.name} connector availability", spec.availability.value, "", "/integrations", kind="status")
                ledger.note("connector_setup", spec.summary, "/integrations")
                if spec.availability.value == "planned":
                    ledger.note("connector_action", "This connector is planned. Request access in Integrations; automatic sync is not yet available.", "/integrations")
                elif spec.auth_fields:
                    ledger.note("connector_action", "Open Integrations, choose this connector and provide: " + ", ".join(f.label for f in spec.auth_fields if f.required), "/integrations")
        elif ctx.task_name == "data_quality":
            from app.services import data_quality_audit
            report = await data_quality_audit.audit(session, tenant_id=ctx.tenant_id, industry=ctx.industry.value)
            for key in ("health_score", "issues_found", "critical", "warnings"):
                ledger.add(key, key.replace("_", " ").capitalize(), report[key], "", "/data-quality")
            for index, finding in enumerate(report["findings"][:25]):
                ledger.add(f"finding_{index}", finding["label"], finding["count"], "records", "/data-quality")
                ledger.note(f"reason_{index}", finding["why_it_matters"], "/data-quality")
                ledger.note(f"fix_{index}", finding["how_to_fix"], "/data-quality")
        else:
            from app.services.llm.explanations import project_context
            await project_context(ledger, session, db, ctx, entity_id, connector=connector, run_id=run_id)
    return ledger.finish(language)


async def generate_summary(db, ai, ctx: AIContext, *, entity_id=None, connector=None, language="en", run_id=None) -> dict:
    policy = await PolicyStore(db).load(ctx)
    if not policy.enabled or not policy.task_enabled:
        return {"state": "disabled", "reason": "feature_disabled", "blocks": []}
    if policy.sharing == "disabled" or not policy.aggregate_context:
        return {"state": "policy_blocked", "reason": "sharing_disabled", "blocks": []}
    if ai is None:
        return {"state": "unavailable", "reason": "configuration_missing", "blocks": []}
    data = await build_context(db, ctx, entity_id=entity_id, connector=connector, language=language, run_id=run_id)
    result = await ai.run(ctx, request_for(ctx.task_name, data.model_dump(mode="json")))
    return {"state": result.state, "reason": result.reason, "snapshot": data.snapshot,
            "blocks": render_narrative(data, result.value) if result.state == "success" else []}
