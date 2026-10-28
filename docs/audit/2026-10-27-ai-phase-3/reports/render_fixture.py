"""Synthetic artifact-only fixture; never writes a workspace or sends mail."""
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
import json
import uuid

from app.services import roi
from app.services.management_reports import project_report, render_report_pdf, supplier_draft

destination = Path(__file__).parent
rec = SimpleNamespace(id=uuid.UUID(int=1), sku_id=uuid.UUID(int=2), kind="purchase_order", status="accepted",
    baseline_units=100, recommended_units=50, accepted_units=37, unit_cost=200, unit_price=500,
    inputs={"unit_cost": 200, "holding_cost_pct": .25, "protection_days": 42}, economics={"revenue_protected": 10000},
    currency="INR", linked_alert_id=None, decided_at=datetime(2026, 10, 27, tzinfo=UTC),
    updated_at=datetime(2026, 10, 27, tzinfo=UTC), expires_at=datetime(2026, 11, 1, tzinfo=UTC))
tiers = {"opportunity": roi._opportunity([rec]), "estimated_at_approval": roi._at_approval([rec]), "observed": [roi._realized()]}
summary = dict(window_days=90, currency="INR", currencies=["INR"], tiers={key: {"label": roi.TIERS[key],
    "status": "not_measurable" if key == "observed" else "estimate", "lines": [line.as_dict() for line in lines]} for key, lines in tiers.items()},
    lines=[line.as_dict() for lines in tiers.values() for line in lines],
    caveat="Estimates use the inputs frozen on each recommendation. Approving a recommendation is a decision, not an outcome: none of these figures is money saved until orders, receipts and sales confirm it.")
report = project_report(summary, now=datetime(2026, 10, 27, tzinfo=UTC))
(destination / "synthetic-source.json").write_text(json.dumps({"fixture": "synthetic, artifact-only, no real business data", "report": report}, indent=2), encoding="utf-8")
for language in ("en", "hi", "te", "ta"):
    (destination / f"roi-{language}.pdf").write_bytes(render_report_pdf(report, language=language))
    (destination / f"supplier-{language}.json").write_text(json.dumps(supplier_draft(rec, "SYNTHETIC-SKU", language=language,
        now=datetime(2026, 10, 27, tzinfo=UTC)), ensure_ascii=False, indent=2), encoding="utf-8")
print("Rendered four synthetic report PDFs and four supplier draft fixtures")
