# AI Smart Import (multi-file) — design

Date: 2026-10-27 · Status: approved in chat, build requested

## Problem

Clients hand over POS/ERP *report* exports, not import-ready tables (example:
Sai Balaji Fashions — stock balance CSV, gross-profit XLSX, daily sales XLSX,
purchase XLSX). Today's uploader takes one file, one kind, and maps columns by
alias (plus optional AI gap-filling). It cannot tell the user which file goes
where, cannot reshape per-piece stock codes into SKUs, has no home for a
"Jan–Oct total per SKU" figure, and maps `Cost Price` to `price`.

## Goals

1. Upload up to 10 files at once; each is analysed independently.
2. For each file, propose a **plan**: destination(s), column mapping, and a set
   of **fixed, tested transforms** — and say plainly when a file is unusable
   and why.
3. Show the plan as an editable before → after preview; nothing is written
   until the user confirms that file.
4. Store period totals (no dates) honestly as period sales, not as daily sales.

Non-goals: cross-file joins; LLM-authored transforms; feeding period totals
into the time-series forecast; days-of-cover UI on Inventory (follow-up).

## Destinations

| Destination | Required mapped fields | Writes |
|---|---|---|
| `products` | sku or name | SKUs (brand, category, price, size, colour…) via existing products import |
| `inventory` | sku, available | `inventory_positions` via existing inventory import |
| `sales` | sku, quantity, timestamp | `sales` via existing sales import |
| `period_sales` | sku, quantity, period start/end | new `sku_period_sales` |
| `unusable` | — | nothing; shows reason + what export to ask for |

A file may have several destinations, applied in order products → inventory /
period_sales / sales (catalogue details land before quantities). Stock balance
⇒ `[products, inventory]`; gross profit ⇒ `[products, period_sales]`.

## Plan = rules first, AI fills gaps

`import_plan.build_plan(table, ai_suggestion | None)`:

1. **Table discovery** — reuse `import_layout.discover_tables` (letterhead and
   header-row detection already work). Best table across the three kinds wins.
2. **Alias mapping** — existing `_build_header_map`, plus a planner rule: when
   both a retail/selling/MRP column and a cost column exist, `price` = retail.
   Planner-local aliases: `stockno`→sku, `closingbalqty`/`closingqty`/
   `closingstock`→available, `styleno`/`style`→style (planner-only field).
3. **AI suggestion** (task `import_plan`, flag `ai_import_plan`): input is
   column id/label/type, row count, and — only if the workspace sharing level is
   `redacted_samples` — 3 sample rows. Output is validated against the real
   column ids and a closed vocabulary:
   destinations ⊂ enum, reason ∈ enum, mapping field ∈ allowed fields,
   style column, description column, transform flags. AI may **fill unmapped
   fields and choose destinations**; it never replaces an alias/saved mapping.
4. **Rules fallback** (AI disabled / failed / invalid):
   sku+available → inventory; sku+quantity+date → sales; sku+quantity, no date
   → period_sales; sku/name only → products; any catalogue fields
   (brand/category/price) present alongside a quantity destination → also
   products; no sku and no name → unusable (`no_item_column`).
   The UI banner says which source produced the plan.
5. **Feasibility** — each destination lists missing required fields; the card
   shows "needs mapping" until they are mapped.

## Fixed transforms (`import_transforms.py`, pure, no DB)

- `drop_summary_rows` — drop rows whose sku/name is blank and whose any text
  cell normalises to `total`, `subtotal`, `grandtotal` (handles `Sub Total : `
  and `Grand Total : `). Excluded rows are listed with the reason.
- `parse_variant(description)` — split on `" - "` if present, else `"-"`;
  last token = size code, previous = colour; `NA` → no colour. Raw tokens are
  upper-cased and trimmed. Never guesses.
- `size_codes` — every distinct size code is run through
  `fashion_sizes.normalize_size`. Recognised codes map automatically;
  unrecognised codes (e.g. `0L`, `2X`, `FR`, `32`) are listed with counts and the
  user picks a canonical size or "leave blank" for each. Blank size is allowed;
  the raw code stays in the SKU identity.
- `group_pieces` — derived SKU code = `BRAND-STYLE-COLOUR-SIZECODE` (slugged,
  upper-case, `NA` parts dropped). Rows group by (derived sku, location):
  inventory/period quantities and values are summed; catalogue fields take the
  most common value, and conflicts are counted as warnings.
- `period_range` — parse `Date Range : DD-MM-YYYY - DD-MM-YYYY` from the rows
  above the header (DMY, the report's format); always shown editable and must
  be confirmed for `period_sales`.

Derived columns get ids `x_sku`, `x_colour`, `x_size`, `x_name` and appear in
the mapping dropdowns like source columns.

## Storage — `sku_period_sales` (migration 0033)

`id, tenant_id → tenants, sku_id → skus, location text, period_start date,
period_end date (≥ start), units numeric ≥ 0, net_value numeric null,
cost_value numeric null, source text, created_at, updated_at`;
`UNIQUE (tenant_id, sku_id, location, period_start, period_end)`; upsert on
re-import (correction replaces). ENABLE + FORCE RLS with the
`tenant_id = current_tenant_id()` policy; grants to `sanket_app`.

## API (router `integrations_hub`)

- `POST /integrations/import/plan` — multipart `files[]` (1–10, ≤10 MB each).
  Returns `{files: [{file_index, filename, plan_source, ai_state, table,
  destinations, mapping, transforms, size_codes, period, preview, exclusions,
  warnings, plan_token}]}`. A file that fails to parse returns `{error}` in its
  slot; others still plan.
- `POST /integrations/import/plan/confirm` — multipart `file` + `plan_token` +
  `decision` JSON (destinations, mapping, transforms, size_map, period,
  exclude_rows). Re-derives everything server-side from the file bytes; the
  token binds tenant, user, file hash and table. Owner/admin/analyst only. One
  transaction per file; returns per-destination stats. Audit
  `import.plan_confirmed`.

## UI

New **Smart import** option in the Integrations upload panel: multi-file
dropzone → one card per file with destination chips (editable), AI reason +
plan source, mapping dropdowns (source + derived columns), transform toggles,
before/after preview (raw rows → grouped SKUs × locations), unrecognised size
code table, period dates, exclusions/warnings, and "Import this file". A
summary bar offers "Import all ready files". Unusable files show the reason and
the recommended export.

## Errors & honesty

AI off/failing → rules plan + banner, never a blocked upload. Any row that
fails validation fails that file (existing all-or-nothing rule), with the row
errors shown. No values are invented: unknown sizes stay blank, missing periods
block `period_sales`.

## Testing

pytest: transforms (summary rows, variant parsing, grouping sums & conflicts,
size codes, period range), plan validator (rejects unknown ids/fields/enums),
rules planner on hand-written rows shaped like the four client reports, plan
+ confirm API (AI off, AI suggestion, partial multi-file failure, viewer
refused), RLS isolation for `sku_period_sales`. Vitest: Smart import panel
(multi-file cards, edits sent in confirm). Live check on the client files in the
Browser pane. Client data is not committed.

## Enabling AI

`DEEPSEEK_API_KEY` (backend env / k8s secret; optional `LLM_BASE_URL`,
`LLM_MODEL`), plus workspace flags `ai_enabled` and `ai_import_plan` and an AI
data-sharing level other than `disabled`.
