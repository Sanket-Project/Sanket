"""Request-owned interactive flows; no chat history, raw prompts, or tools in storage."""
from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

from app.config import get_settings
from app.services.llm.context import Ledger
from app.services.llm.facts import render_narrative
from app.services.llm.interactive import question_input, scenario_input
from app.services.llm.policy import PolicyStore
from app.services.llm.tasks import request_for
from app.services.notifications.localization import translate


async def permitted(db, ctx):
    policy = await PolicyStore(db).load(ctx)
    if not policy.enabled or not policy.task_enabled:
        return {"state": "disabled", "reason": "feature_disabled"}
    if policy.sharing == "disabled" or not policy.aggregate_context:
        return {"state": "policy_blocked", "reason": "sharing_disabled"}
    return None


async def interpret(request, ai, ctx, text, language="en"):
    denied = await permitted(request.app.state.db, ctx)
    if denied:
        return {**denied, "assumptions": {}, "evidence": [], "requires_confirmation": True}
    data = scenario_input(text, language)
    if not data.candidates:
        return {"state": "needs_clarification", "assumptions": {}, "evidence": [], "requires_confirmation": True,
                "unresolved": ["Specify a numeric demand/price/cost percentage, lead-time change in days/weeks, or supplier outage duration."]}
    if ai is None:
        return {"state": "unavailable", "reason": "configuration_missing", "assumptions": {}, "evidence": [], "requires_confirmation": True}
    result = await ai.run(ctx, request_for("scenario_interpretation", data.model_dump(mode="json")))
    denied = await permitted(request.app.state.db, ctx)
    if denied:
        return {**denied, "assumptions": {}, "evidence": [], "requires_confirmation": True}
    if result.state != "success":
        return {"state": result.state, "reason": result.reason, "assumptions": {}, "evidence": [], "requires_confirmation": True}
    selected = [c for c in data.candidates if c.id in result.value.candidate_ids]
    return {"state": "success" if selected else "needs_clarification", "requires_confirmation": True,
            "assumptions": {c.field: int(c.value) if c.field in {"lead_time_delta_days", "supplier_outage_weeks"} else c.value for c in selected},
            "evidence": [c.model_dump() for c in selected],
            "unresolved": ["Only the listed numeric assumptions were interpreted. Review any other conditions manually."]}


async def explain_result(request, ai, ctx, payload, language="en"):
    """Called only with the just-computed engine result, never a browser-supplied result."""
    denied = await permitted(request.app.state.db, ctx)
    if denied:
        return {**denied, "blocks": []}
    if ai is None:
        return {"state": "unavailable", "reason": "configuration_missing", "blocks": []}
    ledger = Ledger()
    period = f"Saved run {payload['run_id']}"
    for scope in ("baseline", "result"):
        prefix = "baseline" if scope == "baseline" else "scenario"
        row = payload[scope]
        for field, label, unit in (("short_units", "unfulfilled demand", "units"), ("fill_rate", "fill rate (fraction)", ""),
                                   ("gross_margin", "modeled gross margin", row.get("currency", ""))):
            ledger.add(f"{prefix}_{field}", f"{prefix.capitalize()} {label}", row.get(field), unit, "/scenarios", period=period)
    ledger.add("scenario_horizon", "Simulation horizon", payload["config"]["horizon_weeks"], "weeks", "/scenarios", period=period)
    if payload.get("readiness", {}).get("advisory"):
        ledger.note("scenario_advisory", "These simulation results are advisory because input coverage is incomplete or stale", "/scenarios", kind="data_gap")
    data = ledger.finish(language)
    result = await ai.run(ctx, request_for("scenario_explanation", data.model_dump(mode="json")))
    denied = await permitted(request.app.state.db, ctx)
    if denied:
        return {**denied, "blocks": []}
    blocks = render_narrative(data, result.value) if result.state == "success" else []
    if result.state == "success" and payload.get("readiness", {}).get("advisory"):
        blocks.append({"text": translate("These simulation results are advisory because input coverage is incomplete or stale", language), "kind": "data_gap", "sources": [{"fact_id": "scenario_advisory", "href": "/scenarios"}]})
    return {"state": result.state, "reason": result.reason, "snapshot": data.snapshot, "blocks": blocks}


async def read_operation(request, ctx, step):
    """Call the existing read handlers with the current request identity and explicit bounds.

    The containing route inherits the same subscription dependency as these APIs.
    No worker/service account, HTTP dispatch, SQL plan, or caller-controlled route exists.
    """
    from app.services.industry_context import get_industry_context
    industry = get_industry_context(ctx.industry.value)
    sku = None
    if step.sku_id is not None:
        from app.routers.skus import get_sku
        from app.services.llm.errors import AIError
        sku = await get_sku(str(step.sku_id), request, industry, ctx.tenant_id)
        if sku.industry != ctx.industry:
            raise AIError("invalid_context")
    if step.operation == "analytics":
        from app.routers.sales_analytics import sales_summary
        return await sales_summary(request, industry, ctx.tenant_id)
    if step.operation == "inventory":
        from app.routers.inventory import stock_overview
        return await stock_overview(request, industry, ctx.tenant_id, offset=0, limit=20, search="",
                                    location=step.location or "", attention="all", sort="sku")
    if step.operation == "trends":
        from app.routers.trends import company_trend_analysis
        return await company_trend_analysis(request, industry, ctx.tenant_id, days=step.days,
                                            product_id=None, sku_id=step.sku_id, state=step.state, district=step.district)
    if step.operation == "sku":
        if sku is not None:
            return {"sku_id": str(sku.id), "unit_cost": sku.unit_cost, "unit_price": sku.unit_price,
                    "lead_time_days": sku.lead_time_days, "moq": sku.moq, "currency": sku.currency}
        from app.routers.skus import list_skus
        rows = await list_skus(request, industry, ctx.tenant_id, limit=20, offset=0, active_only=True)
        return {"count": len(rows)}
    if step.operation == "saved_forecast":
        from app.routers.forecasts import latest_forecast
        return await latest_forecast(request, ctx.tenant_id, industry, view="summary", offset=0, limit=20, run_id=None)
    raise ValueError("Unsupported read operation")


def project_operation(ledger, step, data):
    """Only named source-owned numeric fields leave the server; rows/names never do."""
    operation = step.operation
    source = {"analytics": "/dashboard", "trends": "/trends", "sku": "/skus", "inventory": "/inventory", "saved_forecast": "/forecasts"}[operation]
    observed = datetime.now(UTC).isoformat()

    def add(name, label, value, unit="", period=None):
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float, Decimal))):
            return
        ledger.add(f"{operation}_{name}", label, value, unit, source, period=period or observed)

    if operation == "analytics":
        row = data.get(step.period, {})
        if not row.get("transactions"):
            ledger.note("analytics_missing", "No sales observations are available for the selected period", source, kind="data_gap")
            return
        period = f"{row.get('period_start', step.period)} / {data.get('as_of', observed)}"
        for name, label, unit in (("units_sold", "Recorded units sold", "units"), ("transactions", "Recorded transactions", ""), ("returns", "Recorded returns", "units")):
            add(name, label, row.get(name), unit, period)
        currency = row.get("currency")
        if isinstance(currency, str) and len(currency) == 3 and currency.isalpha():
            for name, label in (("gross_revenue", "Recorded gross revenue"), ("net_revenue", "Recorded net revenue")):
                add(name, label, row.get(name), currency.upper(), period)
    elif operation == "inventory":
        if not data.get("total_skus"):
            ledger.note("inventory_missing", "No recorded inventory positions are available", source, kind="data_gap")
            return
        add("skus", "SKUs with recorded inventory", data.get("total_skus"))
        add("available_units", "Available inventory in recorded positions", data.get("totals", {}).get("available_units"), "units")
        add("inbound_units", "Recorded inbound inventory", data.get("totals", {}).get("inbound_units"), "units")
        ledger.note("inventory_scope", "Inventory totals cover recorded positions; unrecorded stock is unknown", source, kind="data_gap")
    elif operation == "trends":
        sales = data.get("sales", {})
        if sales.get("status") != "available":
            ledger.note("trends_missing", "Company trend observations are unavailable for this scope", source, kind="data_gap")
            return
        for name, label, unit in (("current_units", "Current comparison-period sales", "units"), ("previous_units", "Previous comparison-period sales", "units"), ("change_pct", "Measured sales change", "%")):
            add(name, label, sales.get(name), unit, sales.get("as_of"))
        if data.get("external", {}).get("status") != "available":
            ledger.note("trends_external_missing", "No matching external trend evidence is available", source, kind="data_gap")
    elif operation == "sku":
        if data.get("sku_id"):
            source = f"/skus/{data['sku_id']}"
            for name, label, unit in (("lead_time_days", "Recorded SKU lead time", "days"), ("moq", "Recorded SKU minimum order quantity", "units")):
                add(name, label, data.get(name), unit)
            currency = data.get("currency")
            if isinstance(currency, str) and len(currency) == 3 and currency.isalpha():
                for name, label in (("unit_cost", "Recorded SKU unit cost"), ("unit_price", "Recorded SKU unit price")):
                    add(name, label, data.get(name), currency.upper())
        else:
            add("count", "Active SKUs in the first catalogue page (maximum twenty)", data.get("count"))
    else:
        forecast = data.get("forecast")
        if forecast is None:
            ledger.note("saved_forecast_missing", "No saved forecast run is available", source, kind="data_gap")
            return
        for name, label in (("total_skus", "SKUs in the saved forecast"), ("horizon_weeks", "Saved forecast horizon")):
            add(name, label, forecast.get(name), "weeks" if name == "horizon_weeks" else "", str(forecast.get("completed_at") or observed))
        rows = forecast.get("rows") or []
        for i, row in enumerate(rows[:20]):
            period = f"{str(row.get('forecast_date', ''))[:10]} / {str(forecast.get('run_id', ''))[:36]}"
            for band, label in (("p10", "Saved forecast lower demand"), ("p50", "Saved forecast median demand"), ("p90", "Saved forecast upper demand")):
                add(f"week_{i}_{band}", label, row.get(band), "units", period)
        if len(rows) > 20:
            ledger.note("saved_forecast_bounded", "This answer includes only the first twenty saved forecast weeks; open the source for the full horizon", source, kind="data_gap")
        if data.get("stale"):
            ledger.note("saved_forecast_stale", "The saved forecast is stale; this answer does not refresh it", source, kind="data_gap")


async def answer(request, ai, ctx, text, language="en"):
    # One deadline covers planning, all reads and rendering. Cancellation propagates.
    async with asyncio.timeout(get_settings().llm_deadline_s):
        denied = await permitted(request.app.state.db, ctx)
        if denied:
            return {**denied, "blocks": []}
        data = question_input(text, language)
        if ai is None:
            return {"state": "unavailable", "reason": "configuration_missing", "blocks": []}
        plan = await ai.run(ctx, request_for("data_qa_plan", data.model_dump(mode="json")))
        if plan.state != "success":
            return {"state": plan.state, "reason": plan.reason, "blocks": []}
        ledger = Ledger()
        for step in plan.value.steps:
            denied = await permitted(request.app.state.db, ctx)
            if denied:
                return {**denied, "blocks": []}
            source = await read_operation(request, ctx, step)
            project_operation(ledger, step, source)
        answer_ctx = replace(ctx, task_name="data_qa_answer")
        denied = await permitted(request.app.state.db, answer_ctx)
        if denied:
            return {**denied, "blocks": []}
        facts = ledger.finish(language)
        if not any(f.value is not None for f in facts.facts):
            return {"state": "no_data", "message": "I don't have data for that in this workspace.", "blocks": [],
                    "missing_sources": sorted({f.source for f in facts.facts})}
        result = await ai.run(answer_ctx, request_for("data_qa_answer", {**facts.model_dump(mode="json"), "question": data.question}))
        denied = await permitted(request.app.state.db, answer_ctx)
        if denied:
            return {**denied, "blocks": []}
        blocks = render_narrative(facts, result.value) if result.state == "success" else []
        if result.state == "success":
            # Coverage/staleness disclosures are mandatory even when the model omits them.
            cited = {s["fact_id"] for block in blocks for s in block["sources"]}
            for fact in facts.facts:
                if fact.kind == "data_gap" and fact.id not in cited:
                    blocks.append({"text": translate(fact.label, language), "kind": "data_gap", "sources": [{"fact_id": fact.id, "href": fact.source}]})
        return {"state": result.state, "reason": result.reason, "snapshot": facts.snapshot, "blocks": blocks}
