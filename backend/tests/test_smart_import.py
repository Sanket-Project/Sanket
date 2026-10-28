from unittest.mock import AsyncMock

import pytest
from sqlalchemy import text
from test_import_confirmation import SECRET, seed
from test_import_layout import workbook

from app.services.llm.contracts import AIResult
from app.services.llm.import_plan_task import PlanOutput, PlanSelection

STOCK = (
    b'"Company Name","Stock No","Item Description","Category","Brand","Style No","Sub Category",'
    b'"Cost Price","Retail Price","Closing Bal.Qty","Closing Bal.Val"\n'
    b'"ALWAL","S49159WL58646","WESTREN - Straight Pant - SUKANYA - 49159 - WHITE - L","WESTREN","SUKANYA",'
    b'"49159","Straight Pant","454.0000","699.0000","1.0000","454.0000"\n'
    b'"ALWAL","S49159WL58648","WESTREN - Straight Pant - SUKANYA - 49159 - WHITE - L","WESTREN","SUKANYA",'
    b'"49159","Straight Pant","454.0000","699.0000","1.0000","454.0000"\n'
    b'"WH","M0007K0L54854","KURTIS - KURTIS - MYVI - 0007 - NA - 0L","KURTIS","MYVI","0007","KURTIS",'
    b'"395.0000","699.0000","3.0000","1185.0000"\n'
    b'"","","Grand Total : ","","","","","","","5.00","2093.00 "\n'
)
LETTERHEAD = "Sai Balaji Fashions - WH\nGross Margin Report\nDate Range : 01-01-2026 - 25-10-2026"


def gross(qty=22):
    return workbook({"Sheet1": [
        [LETTERHEAD] * 6,
        ["Company Name", "Stock No", "Item Description", "Brand", "Sales Qty", "Net Sales Value"],
        ["ALWAL", "77SHADP0L49996", "PLAZO SETS - PLAZO SETS - 7SHADES - 7SHAD - NA - 0L", "7SHADES", qty, 21448.33],
    ]})


def dsr():
    return workbook({"Sheet1": [
        ["Company Name", "Voucher Date", "Type", "Total Sales Bill", "Sales Qty", "Sales Amount"],
        ["ALWAL", "2026-10-01", "Sales/Return", 7, 19, 18246],
        ["Sub Total : ", None, None, 7, 19, 18246],
    ]})


async def scalar(db, ctx, sql):
    async with db.session(str(ctx.tenant_id)) as s:
        return await s.scalar(text(sql), {"t": ctx.tenant_id})


async def test_stock_balance_plans_groups_pieces_and_imports(app_role_db):
    from app.services.integrations.smart_import import confirm_plan, plan_files
    ctx = await seed(app_role_db)
    plan = (await plan_files(app_role_db, None, ctx, SECRET, [("stock.csv", STOCK)]))["files"][0]
    decision = plan["decision"]
    assert plan["plan_source"] == "rules"
    assert decision["destinations"] == ["products", "inventory"]
    assert decision["transforms"] == {"parse_variant": True, "group_pieces": True}
    assert decision["mapping"]["sku"] == "x_sku"
    assert plan["preview"]["source_rows"] == 3
    assert plan["preview"]["output_rows"] == 2
    assert [e["reason"] for e in plan["exclusions"]] == ["summary_row"]
    assert {"code": "0L", "count": 1, "suggestion": None, "meaning": "Source-specific code — review required"} in plan["size_codes"]
    assert await scalar(app_role_db, ctx, "SELECT count(*) FROM skus WHERE tenant_id=:t") == 0

    decision["size_map"] = {"0L": "L"}
    result = await confirm_plan(app_role_db, ctx, SECRET, "stock.csv", STOCK, plan["plan_token"], decision)
    assert result["destinations"]["inventory"]["inventory_rows"] == 2
    assert await scalar(app_role_db, ctx, "SELECT count(*) FROM skus WHERE tenant_id=:t") == 2
    assert await scalar(app_role_db, ctx, """SELECT l.on_hand_units FROM inventory_levels l JOIN skus s ON s.id=l.sku_id
        WHERE l.tenant_id=:t AND s.sku_code='SUKANYA-49159-WHITE-L'""") == 2
    assert await scalar(app_role_db, ctx, """SELECT attributes->>'size' FROM skus
        WHERE tenant_id=:t AND sku_code='MYVI-0007-0L'""") == "L"
    assert await scalar(app_role_db, ctx, """SELECT unit_price FROM skus
        WHERE tenant_id=:t AND sku_code='MYVI-0007-0L'""") == 699


async def test_unknown_size_stays_blank_without_user_choice(app_role_db):
    from app.services.integrations.smart_import import confirm_plan, plan_files
    ctx = await seed(app_role_db)
    plan = (await plan_files(app_role_db, None, ctx, SECRET, [("stock.csv", STOCK)]))["files"][0]
    await confirm_plan(app_role_db, ctx, SECRET, "stock.csv", STOCK, plan["plan_token"], plan["decision"])
    assert await scalar(app_role_db, ctx, """SELECT attributes->>'size' FROM skus
        WHERE tenant_id=:t AND sku_code='MYVI-0007-0L'""") is None
    assert await scalar(app_role_db, ctx, """SELECT attributes->>'size' FROM skus
        WHERE tenant_id=:t AND sku_code='SUKANYA-49159-WHITE-L'""") == "L"


async def test_gross_profit_becomes_period_sales_and_reimport_replaces(app_role_db):
    from app.services.integrations.smart_import import confirm_plan, plan_files
    ctx = await seed(app_role_db)
    first, second = gross(), gross(30)
    plan = (await plan_files(app_role_db, None, ctx, SECRET, [("gp.xlsx", first)]))["files"][0]
    assert plan["decision"]["destinations"] == ["products", "period_sales"]
    assert plan["decision"]["period"] == {"start": "2026-01-01", "end": "2026-10-25"}
    await confirm_plan(app_role_db, ctx, SECRET, "gp.xlsx", first, plan["plan_token"], plan["decision"])
    again = (await plan_files(app_role_db, None, ctx, SECRET, [("gp.xlsx", second)]))["files"][0]
    result = await confirm_plan(app_role_db, ctx, SECRET, "gp.xlsx", second, again["plan_token"], again["decision"])
    assert result["destinations"]["period_sales"]["period_rows"] == 1
    assert await scalar(app_role_db, ctx, "SELECT count(*) FROM sku_period_sales WHERE tenant_id=:t") == 1
    assert await scalar(app_role_db, ctx, "SELECT units FROM sku_period_sales WHERE tenant_id=:t") == 30
    assert await scalar(app_role_db, ctx, "SELECT count(*) FROM historical_sales WHERE tenant_id=:t") == 0


async def test_period_sales_requires_a_period(app_role_db):
    from app.services.integrations.smart_import import confirm_plan, plan_files
    ctx = await seed(app_role_db)
    content = gross()
    plan = (await plan_files(app_role_db, None, ctx, SECRET, [("gp.xlsx", content)]))["files"][0]
    decision = {**plan["decision"], "period": None}
    with pytest.raises(ValueError, match="period"):
        await confirm_plan(app_role_db, ctx, SECRET, "gp.xlsx", content, plan["plan_token"], decision)


async def test_store_day_totals_are_unusable_and_cannot_be_confirmed(app_role_db):
    from app.services.integrations.smart_import import confirm_plan, plan_files
    ctx = await seed(app_role_db)
    content = dsr()
    plan = (await plan_files(app_role_db, None, ctx, SECRET, [("dsr.xlsx", content)]))["files"][0]
    assert plan["decision"]["destinations"] == []
    assert plan["unusable_reason"] == "no_item_column"
    with pytest.raises(ValueError, match="destination"):
        await confirm_plan(app_role_db, ctx, SECRET, "dsr.xlsx", content, plan["plan_token"], plan["decision"])


async def test_one_bad_file_does_not_block_the_batch(app_role_db):
    from app.services.integrations.smart_import import plan_files
    ctx = await seed(app_role_db)
    files = (await plan_files(app_role_db, None, ctx, SECRET, [("bad.xlsx", b"\x00\x01"), ("stock.csv", STOCK)]))["files"]
    assert files[0]["error"]
    assert files[1]["decision"]["destinations"] == ["products", "inventory"]


async def test_ai_suggestion_fills_an_unmapped_column(app_role_db):
    from app.services.integrations.smart_import import plan_files
    ctx = await seed(app_role_db)
    content = b"Item Ref,On Shelf\nA-1,4\n"
    output = PlanOutput(selections=[PlanSelection(column_id="c1", field="sku", confidence="high"),
                                    PlanSelection(column_id="c2", field="available", confidence="medium")],
                        destinations=["inventory"])
    ai = AsyncMock()
    ai.run.return_value = AIResult(state="success", value=output)
    plan = (await plan_files(app_role_db, ai, ctx, SECRET, [("x.csv", content)]))["files"][0]
    assert plan["plan_source"] == "ai"
    assert plan["provenance"] == {"c1": "ai", "c2": "ai"}
    assert plan["decision"]["destinations"] == ["inventory"]
    assert ai.run.await_args.args[0].task_name == "import_plan"


async def test_tampered_or_foreign_token_is_refused(app_role_db):
    from app.services.integrations.smart_import import confirm_plan, plan_files
    ctx, other = await seed(app_role_db), await seed(app_role_db)
    plan = (await plan_files(app_role_db, None, ctx, SECRET, [("stock.csv", STOCK)]))["files"][0]
    with pytest.raises(ValueError, match="stale or invalid"):
        await confirm_plan(app_role_db, other, SECRET, "stock.csv", STOCK, plan["plan_token"], plan["decision"])
    with pytest.raises(ValueError, match="stale or invalid"):
        await confirm_plan(app_role_db, ctx, SECRET, "stock.csv", STOCK + b"\n", plan["plan_token"], plan["decision"])


async def test_decision_cannot_reference_unknown_columns_or_fields(app_role_db):
    from app.services.integrations.smart_import import confirm_plan, plan_files
    ctx = await seed(app_role_db)
    plan = (await plan_files(app_role_db, None, ctx, SECRET, [("stock.csv", STOCK)]))["files"][0]
    for bad in ({"sku": "c99"}, {"password": "c1"}):
        decision = {**plan["decision"], "mapping": {**plan["decision"]["mapping"], **bad}}
        with pytest.raises(ValueError, match="unsupported fields or unknown columns"):
            await confirm_plan(app_role_db, ctx, SECRET, "stock.csv", STOCK, plan["plan_token"], decision)
    assert await scalar(app_role_db, ctx, "SELECT count(*) FROM skus WHERE tenant_id=:t") == 0


async def test_preview_reflects_edits_without_writing(app_role_db):
    from app.services.integrations.smart_import import plan_files, preview_plan
    ctx = await seed(app_role_db)
    plan = (await plan_files(app_role_db, None, ctx, SECRET, [("stock.csv", STOCK)]))["files"][0]
    decision = {**plan["decision"], "transforms": {"parse_variant": True, "group_pieces": False},
                "mapping": {**plan["decision"]["mapping"], "sku": "c2"}}
    preview = await preview_plan(app_role_db, ctx, SECRET, "stock.csv", STOCK, plan["plan_token"], decision)
    assert preview["preview"]["output_rows"] == 3
    assert await scalar(app_role_db, ctx, "SELECT count(*) FROM skus WHERE tenant_id=:t") == 0


async def test_each_file_is_parsed_once_per_request(app_role_db, monkeypatch):
    from app.services.integrations import import_layout
    from app.services.integrations.smart_import import confirm_plan, plan_files
    ctx = await seed(app_role_db)
    content = gross()
    calls = []
    real = import_layout._read
    monkeypatch.setattr(import_layout, "_read", lambda *a, **k: calls.append(a[0]) or real(*a, **k))
    plan = (await plan_files(app_role_db, None, ctx, SECRET, [("gp.xlsx", content)]))["files"][0]
    assert calls == ["gp.xlsx"]
    await confirm_plan(app_role_db, ctx, SECRET, "gp.xlsx", content, plan["plan_token"], plan["decision"])
    assert calls == ["gp.xlsx", "gp.xlsx"]


async def test_files_without_a_style_column_group_to_the_same_skus(app_role_db):
    from app.services.integrations.smart_import import confirm_plan, plan_files
    ctx = await seed(app_role_db)
    content = workbook({"Sheet1": [
        [LETTERHEAD] * 4,
        ["Company Name", "Stock No", "Item Description", "Brand", "Sales Qty"],
        ["ALWAL", "S49159WL58646", "WESTREN - Straight Pant - SUKANYA - 49159 - WHITE - L", "SUKANYA", 2],
        ["ALWAL", "S49159WL58648", "WESTREN - Straight Pant - SUKANYA - 49159 - WHITE - L", "SUKANYA", 3],
    ]})
    plan = (await plan_files(app_role_db, None, ctx, SECRET, [("gp.xlsx", content)]))["files"][0]
    assert plan["decision"]["transforms"] == {"parse_variant": True, "group_pieces": True}
    assert plan["preview"]["conflicts"] == 0
    await confirm_plan(app_role_db, ctx, SECRET, "gp.xlsx", content, plan["plan_token"], plan["decision"])
    assert await scalar(app_role_db, ctx, """SELECT p.units FROM sku_period_sales p JOIN skus s ON s.id=p.sku_id
        WHERE p.tenant_id=:t AND s.sku_code='SUKANYA-49159-WHITE-L'""") == 5


async def test_net_returns_are_stored_and_catalogue_is_written_once_per_sku(app_role_db):
    from app.services.integrations.smart_import import confirm_plan, plan_files
    ctx = await seed(app_role_db)
    content = workbook({"Sheet1": [
        [LETTERHEAD] * 4,
        ["Company Name", "Stock No", "Item Description", "Brand", "Sales Qty"],
        ["ALWAL", "B79300P1X48269", "KURTHIS - KURTHIS - BHAKTI - 79300 - NA - 1X", "BHAKTI", -1],
        ["WH", "B79300P1X48270", "KURTHIS - KURTHIS - BHAKTI - 79300 - NA - 1X", "BHAKTI", 4],
    ]})
    plan = (await plan_files(app_role_db, None, ctx, SECRET, [("gp.xlsx", content)]))["files"][0]
    result = await confirm_plan(app_role_db, ctx, SECRET, "gp.xlsx", content, plan["plan_token"], plan["decision"])
    assert result["destinations"]["products"]["rows_imported"] == 1
    assert result["destinations"]["period_sales"]["period_rows"] == 2
    assert await scalar(app_role_db, ctx, "SELECT min(units) FROM sku_period_sales WHERE tenant_id=:t") == -1


async def test_period_errors_name_the_sku(app_role_db):
    from app.services.integrations.smart_import import confirm_plan, plan_files
    ctx = await seed(app_role_db)
    content = workbook({"Sheet1": [
        [LETTERHEAD] * 4,
        ["Company Name", "Stock No", "Item Description", "Brand", "Sales Qty"],
        ["ALWAL", "B1", "KURTHIS - KURTHIS - BHAKTI - 1 - NA - L", "BHAKTI", "n/a"],
    ]})
    plan = (await plan_files(app_role_db, None, ctx, SECRET, [("gp.xlsx", content)]))["files"][0]
    assert any("BHAKTI-1-L" in problem for problem in plan["problems"])
    with pytest.raises(ValueError, match="BHAKTI-1-L"):
        await confirm_plan(app_role_db, ctx, SECRET, "gp.xlsx", content, plan["plan_token"], plan["decision"])


async def test_a_file_without_prices_does_not_clear_known_prices(app_role_db):
    from app.services.integrations.smart_import import confirm_plan, plan_files
    ctx = await seed(app_role_db)
    plan = (await plan_files(app_role_db, None, ctx, SECRET, [("stock.csv", STOCK)]))["files"][0]
    await confirm_plan(app_role_db, ctx, SECRET, "stock.csv", STOCK, plan["plan_token"], plan["decision"])
    content = workbook({"Sheet1": [
        [LETTERHEAD] * 4,
        ["Company Name", "Stock No", "Item Description", "Brand", "Sales Qty"],
        ["ALWAL", "S49159WL58646", "WESTREN - Straight Pant - SUKANYA - 49159 - WHITE - L", "SUKANYA", 2],
    ]})
    plan = (await plan_files(app_role_db, None, ctx, SECRET, [("gp.xlsx", content)]))["files"][0]
    await confirm_plan(app_role_db, ctx, SECRET, "gp.xlsx", content, plan["plan_token"], plan["decision"])
    assert await scalar(app_role_db, ctx, """SELECT unit_price FROM skus
        WHERE tenant_id=:t AND sku_code='SUKANYA-49159-WHITE-L'""") == 699
    assert await scalar(app_role_db, ctx, """SELECT attributes->>'size' FROM skus
        WHERE tenant_id=:t AND sku_code='SUKANYA-49159-WHITE-L'""") == "L"


async def test_rows_with_an_item_code_but_no_style_are_kept(app_role_db):
    from app.services.integrations.smart_import import plan_files
    ctx = await seed(app_role_db)
    content = STOCK.replace(b'"Grand Total : "', b'"x"') + (
        b'"NGO","FI3443753","INTIMATES - BRA - FLORET -  - NA - 34","INTIMATES","FLORET","","BRA",'
        b'"100","199","1.0000","100"\n')
    plan = (await plan_files(app_role_db, None, ctx, SECRET, [("stock.csv", content)]))["files"][0]
    assert [(e["row"], e["reason"]) for e in plan["exclusions"]] == [(5, "no_item")]
    assert plan["preview"]["source_rows"] == 4
