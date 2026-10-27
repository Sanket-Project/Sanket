"""Optional exact-file local acceptance. The private source workbook is never copied to CI."""
import json
import hashlib
from collections import Counter
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from sqlalchemy import text

from app.services.integrations.file_import import map_sales_row, map_inventory_row
from app.services.integrations.import_layout import discover_tables
from app.services.integrations.import_review import analyze_import, confirm_import
from app.services.llm.client import ProviderClient
from app.services.llm.policy import PolicyStore
from app.services.llm.service import AIService
from app.services.llm.state import AIState
from app.services.llm.telemetry import Telemetry
from test_config import settings
from test_rls import seed_workspace

SOURCE = Path(__file__).resolve().parents[3] / "_to_delete/qa_artifacts/Redwine_Label_Fashion_Sales_and_Inventory_Record (1).xlsx"


@pytest.mark.skipif(not SOURCE.exists(), reason="Exact private Redwine workbook is a local opt-in fixture")
async def test_exact_redwine_sales_and_inventory_roundtrip(app_role_db, ai_redis):
    raw = SOURCE.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == "6d3c3ce4fcd7f0ee94aaa111f4632bd510c997449c0748d607206d03f1a143d6"
    ctx = await seed_workspace(app_role_db)
    await PolicyStore(app_role_db).configure(ctx, enabled=True, tasks={"import_mapping": True}, sharing="headers_only",
                                            aggregate_context=False, product_names=False)
    calls = []
    def handler(request):
        payload = json.loads(json.loads(request.content)["messages"][1]["content"])
        calls.append(True)
        special = {"Unit Retail Price": "price", "Fulfillment Warehouse": "warehouse",
                   "Stock On Hand (Qty)": "available", "Warehouse Code": "warehouse"}
        selections = [{"column_id": c["id"], "field": special.get(c["label"]), "confidence": "high", "reason": "header_meaning"} for c in payload["columns"]]
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"selections": selections})}}],
                                        "usage": {"prompt_tokens": 120, "completion_tokens": 50}})
    config = settings()
    ai = AIService(config, PolicyStore(app_role_db), AIState(ai_redis, config),
                   ProviderClient(config, transport=httpx.MockTransport(handler)), Telemetry(app_role_db, config))
    secret = "redwine-test-secret-32-characters-long"
    try:
        for kind, sheet, count in [("sales", "Sales Ledger", 500), ("inventory", "Warehouse Inventory", 150)]:
            analysis = await analyze_import(app_role_db, ai, ctx, secret, SOURCE.name, raw, kind)
            top = analysis["tables"][0]
            assert top["sheet"] == sheet
            assert top["rows_total"] == count
            assert top["warning_count"] > 0
            table = discover_tables(SOURCE.name, raw, kind)[0]
            mapper = map_sales_row if kind == "sales" else map_inventory_row
            expected = [mapper(row, top["mapping"]) for row in table.records]
            stats = await confirm_import(app_role_db, ctx, secret, SOURCE.name, raw, kind, analysis["analysis_token"],
                                          [{"id": top["id"], "mapping": top["mapping"]}], remember=True)
            assert stats["sales_rows" if kind == "sales" else "inventory_rows"] == count
            async with app_role_db.session(str(ctx.tenant_id)) as session:
                if kind == "sales":
                    rows = (await session.execute(text("""SELECT s.sku_code,h.units_sold,h.gross_revenue,h.location
                        FROM historical_sales h JOIN skus s ON h.sku_id=s.id AND h.tenant_id=s.tenant_id
                        WHERE h.tenant_id=:t"""), {"t": ctx.tenant_id})).all()
                    actual = Counter((r.sku_code, r.units_sold, r.gross_revenue, r.location) for r in rows)
                    reference = Counter((r["_sku_code"], r["units_sold"], r["gross_revenue"], r["location"]) for r in expected)
                else:
                    rows = (await session.execute(text("""SELECT s.sku_code,i.on_hand_units FROM inventory_levels i
                        JOIN skus s ON i.sku_id=s.id AND i.tenant_id=s.tenant_id WHERE i.tenant_id=:t"""), {"t": ctx.tenant_id})).all()
                    actual = Counter((r.sku_code, r.on_hand_units) for r in rows)
                    reference = Counter((r["_sku_code"], r["on_hand_units"]) for r in expected)
                if actual != reference:
                    pytest.fail("Imported field comparisons do not match the selected workbook source", pytrace=False)
            before = len(calls)
            again = await analyze_import(app_role_db, ai, ctx, secret, "renamed.xlsx", raw, kind)
            assert again["tables"][0]["mapping_source"] == "saved"
            assert len(calls) == before
    finally:
        await ai.aclose()
