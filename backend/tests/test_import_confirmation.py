import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text

from app.models.enums import IndustryCode
from app.services.llm.policy import AIContext
from test_import_layout import workbook

SECRET = "confirmation-test-key-32-characters-long"


async def seed(db):
    tid, uid = uuid.uuid4(), uuid.uuid4()
    async with db.session(str(tid)) as s:
        await s.execute(text("INSERT INTO tenants (id,slug,display_name,industry) VALUES (:t,:slug,'Import fixture','fashion')"),
                        {"t": tid, "slug": f"review-{tid.hex}"})
        await s.execute(text("INSERT INTO users (id,tenant_id,email,full_name,role) VALUES (:u,:t,:e,'Review fixture','owner')"),
                        {"u": uid, "t": tid, "e": f"{uid.hex}@example.test"})
    return AIContext(tid, uid, IndustryCode.fashion)


async def test_analyze_no_writes_confirm_selected_inventory_and_remember(app_role_db):
    from app.services.integrations.import_review import analyze_import, confirm_import
    ctx = await seed(app_role_db)
    content = workbook({"Sales": [["SKU", "Qty", "Date"], ["A", 7, "2026-01-01"]],
                        "Inventory": [["SKU", "Available Stock", "Warehouse"], ["A", 25, "ST1"]]})
    result = await analyze_import(app_role_db, None, ctx, SECRET, "a.xlsx", content, "inventory")
    table = result["tables"][0]
    assert table["sheet"] == "Inventory"
    async with app_role_db.session(str(ctx.tenant_id)) as s:
        assert await s.scalar(text("SELECT count(*) FROM skus WHERE tenant_id=:t"), {"t": ctx.tenant_id}) == 0
    selection = [{"id": table["id"], "mapping": table["mapping"], "include_review_rows": [], "exclude_rows": []}]
    stats = await confirm_import(app_role_db, ctx, SECRET, "a.xlsx", content, "inventory",
                                 result["analysis_token"], selection, remember=True)
    assert stats["inventory_rows"] == 1
    again = await analyze_import(app_role_db, None, ctx, SECRET, "changed-name.xlsx", content, "inventory")
    assert again["tables"][0]["mapping_source"] == "saved"
    async with app_role_db.session(str(ctx.tenant_id)) as s:
        assert await s.scalar(text("SELECT on_hand_units FROM inventory_levels WHERE tenant_id=:t"), {"t": ctx.tenant_id}) == 25
        assert await s.scalar(text("SELECT count(*) FROM historical_sales WHERE tenant_id=:t"), {"t": ctx.tenant_id}) == 0
    other = await seed(app_role_db)
    foreign = await analyze_import(app_role_db, None, other, SECRET, "a.xlsx", content, "inventory")
    assert foreign["tables"][0]["mapping_source"] != "saved"


async def test_confirmation_requires_matching_file_and_all_tables_validate_before_writes(app_role_db):
    from app.services.integrations.import_review import analyze_import, confirm_import
    ctx = await seed(app_role_db)
    content = workbook({"One": [["SKU", "Qty", "Date"], ["A", 3, "2026-01-01"]],
                        "Two": [["SKU", "Qty", "Date"], ["B", "bad", "2026-01-01"]]})
    result = await analyze_import(app_role_db, None, ctx, SECRET, "a.xlsx", content, "sales")
    selection = [{"id": t["id"], "mapping": t["mapping"]} for t in result["tables"]]
    with pytest.raises(ValueError):
        await confirm_import(app_role_db, ctx, SECRET, "a.xlsx", content, "sales", result["analysis_token"], selection, remember=True)
    async with app_role_db.session(str(ctx.tenant_id)) as s:
        assert await s.scalar(text("SELECT count(*) FROM historical_sales WHERE tenant_id=:t"), {"t": ctx.tenant_id}) == 0
        assert await s.scalar(text("SELECT count(*) FROM import_mapping_profiles WHERE tenant_id=:t"), {"t": ctx.tenant_id}) == 0
    with pytest.raises(ValueError, match="analysis"):
        await confirm_import(app_role_db, ctx, SECRET, "a.xlsx", b"changed", "sales", result["analysis_token"], selection)


async def test_mapping_suggestions_protect_aliases_and_expose_confidence(app_role_db):
    from app.services.integrations.import_review import analyze_import
    from app.services.llm.contracts import AIResult, MappingOutput, Selection
    ctx = await seed(app_role_db)
    ai = AsyncMock()
    ai.run.return_value = AIResult(state="success", value=MappingOutput(selections=[
        Selection(column_id="c1", field=None, confidence="unknown"),
        Selection(column_id="c2", field="price", confidence="high"),
        Selection(column_id="c3", field="warehouse", confidence="medium"),
    ]))
    content = b"SKU,Unit Retail Price,Fulfillment Warehouse\nA,125,ST1\n"
    result = await analyze_import(app_role_db, ai, ctx, SECRET, "a.csv", content, "sales")
    table = result["tables"][0]
    assert table["mapping"] == {"sku": "c1", "price": "c2", "warehouse": "c3"}
    assert table["confidence"]["c2"] == "high"
    assert table["provenance"]["c1"] == "alias"


async def test_ambiguous_dates_are_previewed_and_require_confirmed_order(app_role_db):
    from app.services.integrations.import_review import analyze_import, confirm_import
    ctx = await seed(app_role_db)
    raw = b"SKU,Qty,Date\nDATE-1,3,01/02/2026\n"
    result = await analyze_import(app_role_db, None, ctx, SECRET, "dates.csv", raw, "sales")
    table = result["tables"][0]
    assert table["date_reviews"]["c3"][0]["dmy"] == "2026-02-01"
    selection = [{"id": table["id"], "mapping": table["mapping"]}]
    with pytest.raises(ValueError, match="date order"):
        await confirm_import(app_role_db, ctx, SECRET, "dates.csv", raw, "sales", result["analysis_token"], selection)
    selection[0]["date_order"] = "dmy"
    await confirm_import(app_role_db, ctx, SECRET, "dates.csv", raw, "sales", result["analysis_token"], selection)
    async with app_role_db.session(str(ctx.tenant_id)) as s:
        assert str(await s.scalar(text("SELECT sale_time::date FROM historical_sales WHERE tenant_id=:t"), {"t": ctx.tenant_id})) == "2026-02-01"


async def test_confirmed_sales_replay_is_success_without_new_rows(app_role_db):
    from app.services.integrations.import_review import analyze_import, confirm_import
    ctx = await seed(app_role_db)
    raw = b"SKU,Qty,Date\nREPLAY-A,3,2026-02-01\n"
    for attempt in range(2):
        analysis = await analyze_import(app_role_db, None, ctx, SECRET, "replay.csv", raw, "sales")
        table = analysis["tables"][0]
        stats = await confirm_import(app_role_db, ctx, SECRET, "replay.csv", raw, "sales", analysis["analysis_token"],
                                     [{"id": table["id"], "mapping": table["mapping"]}], remember=True)
        assert stats["rows_inserted"] == (1 if attempt == 0 else 0)
        assert stats["rows_unchanged"] == attempt


async def test_analyze_makes_at_most_one_model_request_for_the_selected_table(app_role_db):
    from app.services.integrations.import_review import analyze_import
    from app.services.llm.contracts import AIResult
    ctx = await seed(app_role_db)
    raw = workbook({"Sales": [["SKU", "Qty", "Date", "Unknown"], ["A", 2, "2026-01-01", "x"]],
                    "Inventory": [["SKU", "Available Stock", "Note"], ["A", 2, "x"]]})
    ai = AsyncMock()
    ai.run.return_value = AIResult(state="disabled", reason="feature_disabled")
    await analyze_import(app_role_db, ai, ctx, SECRET, "a.xlsx", raw, "sales")
    assert ai.run.await_count == 1
