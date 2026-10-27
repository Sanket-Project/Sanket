"""Read-only projections of existing planning records; never infer missing signals."""
from datetime import UTC, datetime
from types import SimpleNamespace

from sqlalchemy import select

from app.models.alert import ShortageAlert
from app.models.product import Sku
from app.models.recommendation import Recommendation
from app.services.llm.errors import AIError


def project_decision(ledger, rec):
    source = "/decisions"
    period = rec.get("created_at")
    for key, label, unit in (("recommended_units", "Recommended order", "units"),
                             ("baseline_units", "Spreadsheet baseline", "units"),
                             ("confidence", "Decision confidence", "%")):
        ledger.add(key, label, rec.get(key), unit, source, period=period)
    inputs = rec.get("inputs") or {}
    for key, label, unit in (("days_of_cover", "Stock cover", "days"),
                             ("lead_time_days", "Supplier lead time", "days"),
                             ("demand_p50_over_window", "Forecast median demand over protection window", "units"),
                             ("demand_p90_over_window", "Forecast upper demand over protection window", "units"),
                             ("on_hand_units", "Recorded stock", "units"),
                             ("inbound_units", "Inbound stock", "units"),
                             ("protection_days", "Protection window", "days"),
                             ("unit_cost", "Recorded unit cost", rec["currency"]),
                             ("unit_price", "Recorded unit price", rec["currency"])):
        ledger.add(key, label, inputs.get(key), unit, source, period=period)
    for key, label in (("capital_committed", "Modeled capital required"),
                       ("revenue_protected", "Modeled revenue protected"),
                       ("working_capital_released", "Modeled working capital versus baseline")):
        ledger.add(key, label, (rec.get("economics") or {}).get(key), rec["currency"], source, period=period)
    if inputs.get("lead_time_assumed"):
        ledger.note("assumed_lead_time", "Supplier lead time is assumed; verify it before ordering", source, kind="data_gap")
    for key in ("location_id", "source_location_id"):
        if rec.get(key):
            ledger.note(key, f"{key.replace('_', ' ').capitalize()}: {rec[key]}", source)
    ledger.note("decision_basis", "Values describe the saved decision at " + str(period or "an unavailable timestamp"), source)


def project_alert(ledger, alert):
    for key, label, unit in (("risk_score", "Recorded shortage risk score", ""),
                             ("coverage_days", "Recorded stock coverage", "days"),
                             ("p10_demand", "Forecast lower demand", "units"),
                             ("p50_demand", "Forecast median demand", "units"),
                             ("p90_demand", "Forecast upper demand", "units"),
                             ("trend_score", "Recorded trend score", "")):
        ledger.add(key, label, alert.get(key), unit, "/alerts", period=str(alert.get("fired_at") or "unknown"))
    if alert.get("coverage_days") is None:
        ledger.note("coverage_gap", "Stock coverage is missing; this does not establish a measured demand drop", "/alerts", kind="data_gap")
    ledger.note("cause_unknown", "The alert records risk, but does not establish a cause. Check ingestion, dated stock and location coverage before attributing a change", "/alerts", kind="data_gap")


def industry_advice(ledger, industry, attributes):
    # These predicates require recorded attributes; industry membership never proves an event.
    if industry == "fashion" and attributes.get("season") in {"SS", "FW", "AW", "Cruise", "Resort"}:
        ledger.note("season_review", "A season is recorded for this item. Review its selling window before committing to replenishment", "/products")
    elif industry == "electronics" and type(attributes.get("model_year")) is int:
        ledger.note("model_review", "A model year is recorded. Review product lifecycle and replacement compatibility before a long replenishment commitment", "/products")
    elif industry == "pharma" and attributes.get("storage_class") in {"refrigerated", "frozen"}:
        ledger.note("storage_review", "A cold-storage class is recorded. Verify storage capacity and supplier handling before replenishment; this is operational advice", "/products")
    elif industry == "agrocenter" and attributes.get("product_type") in {"seed", "fertilizer", "pesticide"}:
        ledger.note("crop_review", "An agricultural input type is recorded. Verify the local crop calendar and storage constraints before committing to bulk stock", "/products")
    elif industry == "hardware" and attributes.get("product_type") in {"tool", "fastener", "building_material", "electrical", "plumbing", "paint", "safety"}:
        ledger.note("spec_review", "A hardware product type is recorded. Verify specifications, compatibility and supplier pack sizes before replenishment", "/products")
    else:
        ledger.note("industry_evidence_gap", "No verified industry-specific event is supplied. Review the recorded stock, demand and supplier constraints; event-specific advice is unavailable", "/products", kind="data_gap")


async def load_decision(session, ctx, entity_id):
    if entity_id is None:
        raise ValueError("Select a decision")
    rec = await session.scalar(select(Recommendation).where(
        Recommendation.tenant_id == ctx.tenant_id, Recommendation.industry == ctx.industry,
        Recommendation.id == entity_id))
    if rec is None:
        raise AIError("invalid_context")
    from app.routers.decisions import is_expired
    if is_expired(rec, datetime.now(UTC)) or str(rec.status) == "expired":
        raise ValueError("Decision expired; refresh the source queue")
    return rec


async def project_context(ledger, session, db, ctx, entity_id, *, connector=None, run_id=None):
    if ctx.task_name == "decision_explanation":
        from app.services.decision_builder import serialize
        project_decision(ledger, serialize(await load_decision(session, ctx, entity_id)))
    elif ctx.task_name == "alert_explanation" and connector == "anomaly":
        from app.routers.anomaly import anomaly_skus
        sku = await session.scalar(select(Sku.id).where(Sku.id == entity_id,
                                   Sku.tenant_id == ctx.tenant_id, Sku.industry == ctx.industry))
        if sku is None:
            raise AIError("invalid_context")
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(db=db)))
        report = await anomaly_skus(request, SimpleNamespace(code=ctx.industry.value), ctx.tenant_id, days=90, limit=200)
        match = next((s for s in report["anomalous_skus"] if s["sku_id"] == str(entity_id)), None)
        if match:
            ledger.add("anomaly_count", "Detected anomalous weeks", match["anomaly_count"], "", "/alerts")
            for index, row in enumerate(match["anomaly_rows"][:8]):
                ledger.add(f"anomaly_units_{index}", "Recorded sales during a flagged week", row["y"], "units", "/alerts", period=str(row["ds"]))
        ledger.note("anomaly_cause_gap", "An anomaly flags unusual recorded sales. It does not distinguish lost demand from missing ingestion or establish a cause", "/alerts", kind="data_gap")
    elif ctx.task_name == "alert_explanation":
        if connector is not None:
            raise ValueError("Unsupported alert source")
        alert = await session.scalar(select(ShortageAlert).where(
            ShortageAlert.id == entity_id, ShortageAlert.tenant_id == ctx.tenant_id,
            ShortageAlert.industry == ctx.industry))
        if alert is None:
            raise AIError("invalid_context")
        project_alert(ledger, {key: getattr(alert, key) for key in (
            "risk_score", "coverage_days", "p10_demand", "p50_demand", "p90_demand", "trend_score", "fired_at")})
    elif ctx.task_name == "industry_advice":
        attributes = {}
        if entity_id:
            rec = await load_decision(session, ctx, entity_id)
            sku = await session.scalar(select(Sku).where(Sku.id == rec.sku_id,
                                       Sku.tenant_id == ctx.tenant_id, Sku.industry == ctx.industry))
            attributes = sku.attributes if sku else {}
        industry_advice(ledger, ctx.industry.value, attributes or {})
    elif ctx.task_name == "planning_brief":
        from app.routers.decisions import list_decisions
        from app.services.decision_builder import latest_completed_run
        from app.services.planning_inputs import is_run_fresh
        from app.services import data_quality_audit
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(db=db)))
        report = await list_decisions(request, SimpleNamespace(code=ctx.industry.value), ctx.tenant_id,
                                      status="open", kind=None, limit=20)
        for key, label, unit in (("purchase_orders", "Open purchase orders in the displayed queue", ""),
                                 ("units_to_order", "Recommended order quantity in the displayed queue", "units"),
                                 ("critical", "Critical decisions in the displayed queue", ""),
                                 ("revenue_protected", "Modeled revenue protected by displayed open orders", report["totals"]["currency"])):
            ledger.add(key, label, report["totals"].get(key), unit, "/decisions")
        run = await latest_completed_run(session, ctx.tenant_id, ctx.industry)
        if run_id is not None and (run is None or run.id != run_id):
            raise ValueError("The displayed forecast snapshot changed; refresh the brief")
        if run is None or not is_run_fresh(run, datetime.now(UTC)):
            ledger.note("forecast_gap", "A current completed forecast is unavailable; refresh the source forecast before acting", "/forecasts", kind="data_gap")
        else:
            ledger.note("forecast_run", f"Saved forecast run {run.id}; completed {run.completed_at.isoformat()}", "/forecasts")
        quality = await data_quality_audit.audit(session, tenant_id=ctx.tenant_id, industry=ctx.industry.value)
        ledger.add("data_warnings", "Data-quality findings", quality["issues_found"], "", "/data-quality")
        ledger.note("brief_scope", "Planning brief: active workspace and industry; latest saved run; open queue limited to the displayed twenty decisions", "/dashboard")
    else:
        raise AIError("invalid_input")
