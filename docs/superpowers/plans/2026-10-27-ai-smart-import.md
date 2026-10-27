# AI Smart Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upload up to 10 report-style files at once; for each, propose an editable plan (destinations, mapping, fixed transforms), preview before → after, and import on confirmation.

**Architecture:** Pure transforms (`import_transforms.py`) and a rules planner (`import_plan.py`) sit on top of the existing table discovery. A new LLM task `import_plan` can fill mapping gaps and choose destinations; its output is validated against a closed vocabulary. `smart_import.py` orchestrates plan + confirm, writing through the existing `import_rows` and a new `sku_period_sales` table.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic (raw SQL migrations), PostgreSQL RLS, pydantic strict models, PyJWT; React + TS + TanStack Query, Vitest.

**Spec:** `docs/superpowers/specs/2026-10-27-ai-smart-import-design.md`

## Global Constraints

- Max 10 files per plan request; max 10 MB per file (existing `_MAX_UPLOAD_BYTES`).
- New table gets `ENABLE` + `FORCE ROW LEVEL SECURITY`, policy `tenant_id=current_tenant_id()`, grants to `sanket_app`.
- AI never changes values and never replaces an alias/saved mapping; AI-off must still produce a usable plan.
- Unknown sizes are never guessed: `fashion_sizes.normalize_size` or a user-chosen value, else blank.
- Confirm is owner/admin/analyst only; one transaction per file; any row error fails that file.
- Icons only from `frontend/src/components/ui/icons.tsx`.
- No client data committed; tests use hand-written rows shaped like the client reports.

## File map

| File | Responsibility |
|---|---|
| `backend/app/services/integrations/import_transforms.py` (new) | summary-row drop, variant parse, size codes, piece grouping, period range parse |
| `backend/app/services/integrations/import_plan.py` (new) | planner fields/aliases, rules destinations, feasibility, AI merge |
| `backend/app/services/llm/import_plan_task.py` (new) | `PlanInput`, `PlanOutput`, `validate_plan`, system prompt |
| `backend/app/services/llm/tasks.py`, `service.py` (modify) | register `import_plan`, project its input like `import_mapping` |
| `backend/alembic/versions/0033_sku_period_sales.py` (new) | table + RLS |
| `backend/app/services/integrations/smart_import.py` (new) | `plan_files`, `confirm_plan`, period-sales writer |
| `backend/app/routers/integrations_hub.py` (modify) | `POST /import/plan`, `POST /import/plan/confirm` |
| `frontend/src/api/integrations.ts` (modify) | `planImport`, `confirmPlan`, types |
| `frontend/src/components/integrations/SmartImport.tsx` (new) | multi-file cards UI |
| `frontend/src/pages/Integrations.tsx` (modify) | add "Smart import" option to UploadPanel |

---

### Task 1: Pure transforms

**Files:** Create `backend/app/services/integrations/import_transforms.py`; Test `backend/tests/test_import_transforms.py`

**Interfaces — Produces:**
- `is_summary_row(record: dict, identity_ids: list[str]) -> bool`
- `parse_variant(description: str | None) -> tuple[str | None, str | None]` → `(colour, size_code)`
- `size_codes(codes: Iterable[str]) -> list[dict]` → `[{"code","count","suggestion"}]` sorted by count desc
- `group_pieces(records, *, brand, style, colour, size, location, sums: list[str]) -> tuple[list[dict], int]` → grouped records with `x_sku`, and the count of catalogue-value conflicts
- `parse_period(lines: list[str]) -> tuple[date, date] | None`

- [ ] **Step 1: failing tests**

```python
from datetime import date
from app.services.integrations import import_transforms as t

def test_summary_rows_need_blank_identity_and_total_label():
    assert t.is_summary_row({"c1": "", "c2": "", "c3": "Grand Total : ", "c10": "38419"}, ["c2"])
    assert t.is_summary_row({"c1": "Sub Total : ", "c4": 971}, ["c9"])
    assert not t.is_summary_row({"c2": "TOTAL-01", "c3": "Grand Total"}, ["c2"])

def test_parse_variant_spaced_and_compact():
    assert t.parse_variant("WESTREN - Straight Pant - SUKANYA - 49159 - STEEL GREY - L") == ("STEEL GREY", "L")
    assert t.parse_variant("KURTIS - KURTIS - MYVI - 0007 - NA - 0L") == (None, "0L")
    assert t.parse_variant("KURTHI-ZOLA-81807-NA-00M") == (None, "00M")
    assert t.parse_variant("mix-KINZA-2917-ASST-S TO XXL") == ("ASST", "S TO XXL")
    assert t.parse_variant("") == (None, None)
    assert t.parse_variant("ONEWORD") == (None, None)

def test_size_codes_suggest_only_known_sizes():
    out = t.size_codes(["0L", "0L", "XL", "2XL", "free"])
    assert out[0] == {"code": "0L", "count": 2, "suggestion": None}
    assert {"code": "2XL", "count": 1, "suggestion": "XXL"} in out
    assert {"code": "FREE", "count": 1, "suggestion": "FREE"} in out

def test_group_pieces_sums_per_location_and_counts_conflicts():
    rows = [
        {"b": "SUKANYA", "s": "49159", "col": "WHITE", "sz": "L", "loc": "ALWAL", "q": 1, "p": 699},
        {"b": "SUKANYA", "s": "49159", "col": "WHITE", "sz": "L", "loc": "ALWAL", "q": 2, "p": 799},
        {"b": "SUKANYA", "s": "49159", "col": "WHITE", "sz": "L", "loc": "WH", "q": 5, "p": 699},
        {"b": "MYVI", "s": "0007", "col": None, "sz": "0L", "loc": "ALWAL", "q": 1, "p": 699},
    ]
    out, conflicts = t.group_pieces(rows, brand="b", style="s", colour="col", size="sz", location="loc", sums=["q"])
    by = {(r["x_sku"], r["loc"]): r for r in out}
    assert by[("SUKANYA-49159-WHITE-L", "ALWAL")]["q"] == 3
    assert by[("SUKANYA-49159-WHITE-L", "WH")]["q"] == 5
    assert ("MYVI-0007-0L", "ALWAL") in by
    assert conflicts == 1

def test_parse_period_from_letterhead():
    lines = ["Sai Balaji Fashions - WH\nGross Margin Report\nDate Range : 01-01-2026 - 25-10-2026"]
    assert t.parse_period(lines) == (date(2026, 1, 1), date(2026, 10, 25))
    assert t.parse_period(["no range here"]) is None
```

- [ ] **Step 2:** `cd backend && uv run pytest tests/test_import_transforms.py -q` → FAIL (module missing)
- [ ] **Step 3:** implement (SKU part slug: upper-case, non-alnum runs → `-`, drop empty/`NA` parts; most-common catalogue values via `collections.Counter`; a conflict = a group where any non-sum, non-key column has >1 distinct non-blank value).
- [ ] **Step 4:** rerun → PASS
- [ ] **Step 5:** commit `feat(import): pure smart-import transforms`

### Task 2: Rules planner

**Files:** Create `backend/app/services/integrations/import_plan.py`; Test `backend/tests/test_import_plan.py`

**Interfaces:**
- Consumes: `import_layout.PhysicalColumn` (`id`, `label`, `kind`), `file_import._ALIASES`, `_norm`.
- Produces:
  - `PLAN_FIELDS: tuple[str, ...]` = every canonical field plus `"style"`, `"cogs"`
  - `DESTINATION_FIELDS: dict[str, tuple[str, ...]]` — fields each destination imports
  - `REQUIRED: dict[str, list[set[str]]]` — any-of groups per destination
  - `rules_mapping(columns) -> dict[str, str]` field → column id
  - `rules_destinations(mapping, columns) -> tuple[list[str], str | None]` → (destinations, unusable reason)
  - `missing_fields(destination, mapping, *, period) -> list[str]`
  - `merge_ai(mapping, destinations, suggestion) -> tuple[dict, list[str], str]` → (mapping, destinations, source)

- [ ] **Step 1: failing tests** (columns built with `PhysicalColumn(f"c{i}", label, label)`; `kind` set where dates matter)

```python
from app.services.integrations.import_layout import PhysicalColumn
from app.services.integrations import import_plan as p

def cols(*labels, kinds=None):
    out = [PhysicalColumn(f"c{i+1}", l, l) for i, l in enumerate(labels)]
    for c, k in zip(out, kinds or []):
        c.kind = k
    return out

STOCK = cols("Company Name", "Stock No", "Item Description", "Category", "Brand", "Style No",
             "Sub Category", "Cost Price", "Retail Price", "Closing Bal.Qty", "Closing Bal.Val")
GROSS = cols("Company Name", "Stock No", "Item Description", "Brand", "Sales Qty", "Net Sales Value")
DSR = cols("Company Name", "Voucher Date", "Type", "Total Sales Bill", "Sales Qty", "Sales Amount",
           kinds=["text", "date", "text", "integer", "integer", "integer"])

def test_stock_balance_maps_to_products_and_inventory_with_retail_price():
    m = p.rules_mapping(STOCK)
    assert m["sku"] == "c2" and m["available"] == "c10" and m["warehouse"] == "c1"
    assert m["price"] == "c9" and m["style"] == "c6" and m["description"] == "c3"
    assert p.rules_destinations(m, STOCK) == (["products", "inventory"], None)

def test_gross_profit_is_period_sales_and_needs_a_period():
    m = p.rules_mapping(GROSS)
    assert p.rules_destinations(m, GROSS) == (["products", "period_sales"], None)
    assert p.missing_fields("period_sales", m, period=None) == ["period"]

def test_store_day_totals_are_unusable():
    m = p.rules_mapping(DSR)
    assert p.rules_destinations(m, DSR) == ([], "no_item_column")

def test_ai_fills_gaps_but_never_replaces():
    m = {"sku": "c2"}
    s = {"selections": [{"column_id": "c2", "field": "name"}, {"column_id": "c5", "field": "quantity"}],
         "destinations": ["period_sales"]}
    mapping, dest, source = p.merge_ai(m, ["products"], s)
    assert mapping == {"sku": "c2", "quantity": "c5"} and dest == ["period_sales"] and source == "ai"
```

- [ ] **Step 2:** run → FAIL
- [ ] **Step 3:** implement. Planner aliases on top of `_ALIASES`: sku += `stockno, stockcode, barcodeno`; available += `closingbalqty, closingqty, closingstock, balanceqty`; warehouse += `companyname, storename, branch, outlet, store`; description += `itemdescription, itemdesc`; style = `styleno, style, stylenumber, stylecode, designno, designnumber`; cogs += `costofgoodswithouttax, costofgoods`; revenue += `netsalesvalue, netsales, netamount`. Retail preference: price = first column whose norm ∈ `{retailprice, mrp, sellingprice, saleprice, price, unitprice}`, else a cost column. Destination rules per spec §"Plan" step 4; `"products"` added when sku and any of brand/category/price/description present and a quantity destination exists, or alone when no quantity destination.
- [ ] **Step 4:** run → PASS
- [ ] **Step 5:** commit `feat(import): rules planner for smart import`

### Task 3: LLM task `import_plan`

**Files:** Create `backend/app/services/llm/import_plan_task.py`; Modify `backend/app/services/llm/tasks.py` (TASK_NAMES, get_task), `backend/app/services/llm/service.py:73` (project input for `import_plan` too); Test `backend/tests/llm/test_import_plan_task.py`

**Interfaces — Produces:**
- `PlanInput(columns: list[Column], allowed_fields: list[PlanField], row_count: int)`
- `PlanOutput(selections: list[PlanSelection], destinations: list[Destination], reason: Reason | None)`; `PlanSelection(column_id, field: PlanField | None, confidence)`
- `validate_plan(content: str, task: PlanInput) -> PlanOutput` (raises `AIError("invalid_output")`)
- `TaskRequest("import_plan", PlanInput(...))` dispatches with flag `ai_import_plan`

- [ ] **Step 1: failing tests**

```python
import json, pytest
from app.services.llm.contracts import Column
from app.services.llm.errors import AIError
from app.services.llm.import_plan_task import PlanInput, validate_plan
from app.services.llm.tasks import TASK_NAMES, get_task

TASK = PlanInput(columns=[Column(id="c1", label="Stock No", kind="text"), Column(id="c2", label="Qty", kind="integer")],
                 allowed_fields=["sku", "quantity", "style"], row_count=10)

def ok(**over):
    body = {"selections": [{"column_id": "c1", "field": "sku", "confidence": "high"},
                           {"column_id": "c2", "field": "quantity", "confidence": "medium"}],
            "destinations": ["period_sales"], "reason": None}
    body.update(over)
    return json.dumps(body)

def test_registered():
    assert "import_plan" in TASK_NAMES and get_task("import_plan").input_model is PlanInput

def test_accepts_valid_plan():
    assert validate_plan(ok(), TASK).destinations == ["period_sales"]

@pytest.mark.parametrize("bad", [
    ok(selections=[{"column_id": "c9", "field": "sku", "confidence": "high"}]),
    ok(destinations=["delete_everything"]),
    ok(selections=[{"column_id": "c1", "field": "sku", "confidence": "high"},
                   {"column_id": "c2", "field": "sku", "confidence": "high"}]),
    ok(selections=[{"column_id": "c1", "field": "price", "confidence": "high"},
                   {"column_id": "c2", "field": None, "confidence": "low"}]),
    "not json",
])
def test_rejects_invented_ids_fields_and_destinations(bad):
    with pytest.raises(AIError):
        validate_plan(bad, TASK)
```

- [ ] **Step 2:** run → FAIL
- [ ] **Step 3:** implement; in `service._run` change the projection to `if task.name in {"import_mapping", "import_plan"}` and add `row_count` to the projected payload for `import_plan`.
- [ ] **Step 4:** run plus existing `tests/llm` → PASS
- [ ] **Step 5:** commit `feat(ai): import_plan task contract`

### Task 4: `sku_period_sales` table

**Files:** Create `backend/alembic/versions/0033_sku_period_sales.py` (down_revision `"0032"`); Test `backend/tests/test_sku_period_sales_rls.py`

- [ ] **Step 1: failing test** — two tenants via `test_import_profiles_rls.workspace`; insert a SKU + period row for A; under B's session `SELECT count(*) FROM sku_period_sales` is 0; inserting a row with A's tenant_id under B raises `DBAPIError`; `period_end < period_start` raises.
- [ ] **Step 2:** run → FAIL (table missing)
- [ ] **Step 3:** migration per spec §Storage.
- [ ] **Step 4:** run → PASS
- [ ] **Step 5:** commit `feat(db): sku_period_sales with FORCE RLS`

### Task 5: Smart import service

**Files:** Create `backend/app/services/integrations/smart_import.py`; Test `backend/tests/test_smart_import.py`

**Interfaces:**
- Consumes: Tasks 1–4; `import_layout.discover_tables/_read`; `file_import.import_rows/_get_or_create_sku/_ensure_import_product`; `import_profiles.issue_analysis/verify_analysis` (kind `"plan"`); `import_review._member/_BoundDB`.
- Produces:
  - `async plan_files(db, ai, ctx, secret, files: list[tuple[str, bytes]]) -> dict` → `{"files": [...]}` (shape per spec §API)
  - `async confirm_plan(db, ctx, secret, filename, content, token, decision: dict) -> dict` → `{"destinations": {name: stats}, "rows_excluded": n}`

- [ ] **Step 1: failing tests** (DB, `app_role_db`, `seed` from `test_import_confirmation`):
  1. Stock-shaped CSV (letterless) with 3 rows incl. 2 pieces of one style/colour/size at one store + a `Grand Total : ` row → plan has destinations `[products, inventory]`, `plan_source == "rules"`, 1 exclusion, preview after-count 2; confirm with `group_pieces` on and `size_map {}` → 2 SKUs, inventory row for the grouped SKU has `on_hand_units == 2`.
  2. Gross-profit XLSX with letterhead row containing `Date Range : 01-01-2026 - 25-10-2026` → plan `period == {"start": "2026-01-01", "end": "2026-10-25"}`; confirm → `sku_period_sales.units` stored; re-confirm with changed qty replaces (1 row).
  3. DSR-shaped XLSX → destinations `[]`, `unusable_reason == "no_item_column"`; confirm refused with ValueError.
  4. Two files where one is not a table (`b"\x00\x01"` as `.csv`) → that slot has `error`, the other plans.
  5. Fake AI (`AsyncMock` returning `AIResult(state="success", value=PlanOutput(...))`) fills an unmapped column → `plan_source == "ai"` and `provenance[col] == "ai"`.
  6. Unknown size code `0L` with `size_map {"0L": "L"}` → SKU `size` attribute `L`; without it → blank.
- [ ] **Step 2:** run → FAIL
- [ ] **Step 3:** implement: best table = max score across `discover_tables(kind)` for the three kinds; columns + derived `x_*` columns; `apply(decision)` pipeline: exclude rows → drop summary → variant → size map → group → destination imports in order inside one `db.session`, `import_rows(... kind, headers, records, column_mapping=restricted, identity="period")`; period writer upserts `ON CONFLICT (tenant_id, sku_id, location, period_start, period_end) DO UPDATE`; audit `import.plan_confirmed`.
- [ ] **Step 4:** run → PASS
- [ ] **Step 5:** commit `feat(import): smart import plan and confirm`

### Task 6: API endpoints

**Files:** Modify `backend/app/routers/integrations_hub.py`; Test `backend/tests/test_smart_import_api.py`

- [ ] **Step 1: failing tests** — `client` + `signed_in_workspace("fashion")`: plan 2 files → 200, 2 slots; 11 files → 400; unauthenticated → 401; confirm round-trip → 200 with `destinations.inventory.inventory_rows`; tampered token → 400.
- [ ] **Step 2:** run → FAIL
- [ ] **Step 3:** `POST /import/plan` (`files: list[UploadFile]`), `POST /import/plan/confirm` (`file`, `plan_token`, `decision` JSON ≤ 64 kB); `ValueError → 400`.
- [ ] **Step 4:** run → PASS
- [ ] **Step 5:** commit `feat(api): smart import endpoints`

### Task 7: Frontend

**Files:** Modify `frontend/src/api/integrations.ts`, `frontend/src/pages/Integrations.tsx`; Create `frontend/src/components/integrations/SmartImport.tsx`, `SmartImport.test.tsx`

- [ ] **Step 1: failing Vitest** — mock `integrationsApi.planImport` with two slots (one usable stock plan, one unusable with reason); render; drop two files; expect two cards, the unusable reason text, an editable destination control, and that clicking "Import this file" calls `confirmPlan` with the edited decision (toggle `group_pieces` off first).
- [ ] **Step 2:** `cd frontend && npx vitest run src/components/integrations/SmartImport.test.tsx` → FAIL
- [ ] **Step 3:** implement the panel; add `{ key: "smart", label: "Smart import (AI, multiple files)" }` to UploadPanel.
- [ ] **Step 4:** run → PASS; `npm run typecheck && npm run lint`
- [ ] **Step 5:** commit `feat(ui): smart import panel`

### Task 8: Verification

- [ ] `cd backend && uv run pytest -q` (report real output; pre-existing failures named as such)
- [ ] `cd frontend && npm run typecheck && npm run lint && npm test`
- [ ] Live: start the dev stack, sign in to a fashion test workspace, upload the four client files in Smart import, screenshot the cards, import the stock file, confirm counts in DB.
- [ ] `superpowers:requesting-code-review` on the diff; fix findings.
