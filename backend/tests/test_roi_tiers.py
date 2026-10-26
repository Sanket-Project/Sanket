"""ROI: opportunity, estimates at approval, and observed outcomes kept apart (F10).

Approving one synthetic recommendation used to produce
``total_value_realized=144258.44`` — working capital + carrying cost (derived
from it) + revenue protected — with no supplier order, receipt or observed
outcome behind any of it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.models.enums import (
    DecisionKind,
    DecisionStatus,
    DecisionUrgency,
    IndustryCode,
    ProductStatus,
)
from app.models.product import Product, Sku
from app.models.recommendation import Recommendation
from app.services import roi
from sqlalchemy import text
import json


async def _rec(s, tenant, *, status=DecisionStatus.open, currency="INR", alert=None,
               baseline=100, units=60):
    product = Product(tenant_id=tenant, industry=IndustryCode.fashion, name="Kurti (synthetic)",
                      category="Kurtis", status=ProductStatus.active)
    s.add(product)
    await s.flush()
    sku = Sku(tenant_id=tenant, product_id=product.id, industry=IndustryCode.fashion,
              sku_code=f"K-{uuid.uuid4().hex[:6]}", currency=currency)
    s.add(sku)
    await s.flush()
    return Recommendation(
        tenant_id=tenant,
        industry=IndustryCode.fashion,
        sku_id=sku.id,
        kind=DecisionKind.purchase_order,
        status=status,
        urgency=DecisionUrgency.high,
        headline="Order kurtis (synthetic)",
        recommended_units=units,
        baseline_units=baseline,
        unit_cost=Decimal("200"),
        unit_price=Decimal("500"),
        currency=currency,
        economics={"revenue_protected": 10000},
        inputs={"holding_cost_pct": 0.25, "protection_days": 42},
        linked_alert_id=alert,
        decided_at=datetime.now(UTC) if status == DecisionStatus.accepted else None,
    )


async def _summary(app_role_db, tenant):
    async with app_role_db.session(str(tenant)) as s:
        return await roi.summary(s, tenant_id=tenant, industry="fashion")


async def test_observed_improvement_uses_latest_forecast_not_an_average(db_session, app_role_db, make_tenant):
    tenant = await make_tenant()
    rec = await _rec(db_session, tenant)
    sku = rec.sku_id
    first = date(2026, 8, 31)
    for completed, prediction, model in [(datetime(2026, 8, 23, tzinfo=UTC), 500, "chronos"),
                                          (datetime(2026, 8, 30, tzinfo=UTC), 100, "moirai")]:
        run = uuid.uuid4()
        await db_session.execute(text("INSERT INTO forecast_runs (id, tenant_id, industry, model_stack, horizon_weeks, granularity, status, completed_at, metrics) VALUES (:r,:t,'fashion',ARRAY[:model],8,'weekly','completed',:c,CAST(:m AS jsonb))"),
            {"r": run, "t": tenant, "model": model, "c": completed,
             "m": json.dumps({"calendar": "W-MON-UTC", "history_end": str(first), "mode": "zero_shot"})})
        for i in range(8):
            await db_session.execute(text("INSERT INTO forecast_results (tenant_id,run_id,sku_id,forecast_date,p10,p50,p90,model_name) VALUES (:t,:r,:s,:d,:p,:p,:p,:model)"),
                {"t": tenant, "r": run, "s": sku, "d": first + timedelta(weeks=i), "p": prediction, "model": model})
    for i in range(-1, 8):
        await db_session.execute(text("INSERT INTO historical_sales (tenant_id,sku_id,industry,sale_time,channel,units_sold) VALUES (:t,:s,'fashion',:d,'pos',:u)"),
            {"t": tenant, "s": sku, "d": datetime.combine(first + timedelta(weeks=i), datetime.min.time(), tzinfo=UTC), "u": 100 if i % 2 == 0 else 200})
    await db_session.commit()
    async with app_role_db.session(str(tenant)) as session:
        result = await roi._forecast_improvement(session, tenant, IndustryCode.fashion, datetime(2026, 8, 1, tzinfo=UTC))
    assert result.value == 50.0
    assert result.evidence_count == 8
    assert {row["metric"]: row["value"] for row in result.details}["model_wape"] == .3333


def _lines(result):
    return {line["key"]: line for line in result["lines"]}


async def test_open_recommendations_are_opportunity_not_value(app_role_db, make_tenant):
    tenant = await make_tenant()
    async with app_role_db.session(str(tenant)) as s:
        s.add(await _rec(s, tenant))

    result = await _summary(app_role_db, tenant)
    lines = _lines(result)

    assert "total_value_realized" not in result
    assert lines["open_revenue_at_risk"]["tier"] == "opportunity"
    assert lines["open_revenue_at_risk"]["value"] == 10000
    assert lines["working_capital_vs_baseline"]["value"] == 0
    assert lines["realized_savings"]["value"] is None


async def test_approval_is_an_estimate_and_nothing_is_realized(app_role_db, make_tenant):
    tenant = await make_tenant()
    async with app_role_db.session(str(tenant)) as s:
        s.add(await _rec(s, tenant, status=DecisionStatus.accepted, alert=uuid.uuid4()))

    result = await _summary(app_role_db, tenant)
    lines = _lines(result)

    wc = lines["working_capital_vs_baseline"]
    assert wc["tier"] == "estimated_at_approval"
    assert wc["value"] == 8000.0  # (100 baseline - 60 ordered) x 200 cost
    assert wc["currency"] == "INR"
    assert lines["carrying_cost_implied"]["additive"] is False
    assert lines["approved_orders_on_alerted_skus"]["value"] == 1
    assert "stockouts_avoided" not in lines
    realized = lines["realized_savings"]
    assert realized["tier"] == "observed"
    assert realized["value"] is None
    assert "receipt" in realized["basis"]
    assert result["tiers"]["observed"]["status"] == "not_measurable"


async def test_currencies_are_kept_apart(app_role_db, make_tenant):
    tenant = await make_tenant()
    async with app_role_db.session(str(tenant)) as s:
        s.add(await _rec(s, tenant, status=DecisionStatus.accepted, currency="INR"))
        s.add(await _rec(s, tenant, status=DecisionStatus.accepted, currency="USD"))

    result = await _summary(app_role_db, tenant)
    wc = _lines(result)["working_capital_vs_baseline"]

    assert result["currency"] is None
    assert result["currencies"] == ["INR", "USD"]
    assert wc["value"] is None
    assert wc["values_by_currency"] == {"INR": 8000.0, "USD": 8000.0}


async def test_roi_endpoint_carries_tiers(client, signed_in_workspace):
    _, headers = await signed_in_workspace()
    r = await client.get("/api/v1/roi/summary", headers=headers)
    assert r.status_code == 200, r.text
    assert set(r.json()["tiers"]) == {"opportunity", "estimated_at_approval", "observed"}
