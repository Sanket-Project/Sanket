# Import, validation and migration specification

This is the proposed V2 behavior, not a statement that current endpoints implement it. Exact ordered eight-file columns, types, requiredness and samples are in DATA_DICTIONARY.md and data_dictionary.csv.

## 1. Upload contract and import order

Each import has server-owned tenant/actor, registered source system, entity kind, schema version, source export identifier, file hash, parser options, mapping profile/revision, timezone, quantity semantics, monetary basis, coverage scope and stock-posting mode. A file cannot supply or switch tenant context. CSV is UTF-8; allow BOM on read. Detect delimiter with confidence, then show it. XLSX uses a selected sheet/table region and bounded expansion limits. Preserve raw headers and row/cell locators. No spreadsheet formula or macro is executed.

Use dependency order: reference dictionaries and verified fiscal settings; suppliers; locations parent-first; products; SKUs; approved opening snapshot; sales; linked returns; purchase orders, receipts, invoices, purchase returns. In a historical migration, opening stock/cost time and event cutoff determine whether historical events are analytical-only or stock-posting. Never process an already-inclusive stock baseline and subtract its earlier sales again. A manifest groups related files, their versions, scopes and import order. Independent customer sources can have different layouts while resolving to the same canonical contract.

For this package, configure DEMO-BRAND, KURTI/DUPATTA category schemas, AW26, DEMO-FESTIVE-26, BLUE/NATURAL colors, IN_ALPHA/M and ONE_SIZE/OS sizes, pos channel, size_issue reason and illustrative DEMO-TAX-5 in an isolated test workspace. GSTIN/HSN are blank and fiscal posting must remain blocked until verified. The examples demonstrate contract and arithmetic, not tax-ready business records.

## 2. State machine and preview

`uploaded -> quarantined/scanned -> analyzed -> mapped -> staged -> validated -> awaiting_confirmation -> posting -> completed / completed_with_errors / failed / cancelled`.

Analysis suggests header row, sheet, tables, date/currency conventions, report grain and canonical targets. It is a proposal, not silent authority. Confirmation binds file digest, source, tenant, selected regions, version, profile revision, transformations, counts, posting mode and financial control totals. Changing any of them invalidates preview confirmation. Reuse the existing file-bound analysis/review/profile machinery; retain mapping revision concurrency controls.

Preview displays a representative sample including errors and rare cases, total rows, new/updated/unchanged/conflicting entities, sales/returns quantities separately, tax/discount/payment totals, stock delta, report grain, date range, source authority, duplicate count, unresolved keys and excluded totals. A sample-only preview is not sufficient validation: validate all rows before claiming a file is valid. Show unknown values distinctly from zeros.

## 3. Header and mapping strategy

Normalize headers for matching while preserving original labels and indices. Detect duplicate raw headers and collisions after normalization; never let one silently overwrite another. Detect repeated page headers, merged titles, footers and grand totals. A saved profile identifies all accepted table boundaries and exclusions, including row 9 headers for the actual sales/profit sources and row 2 for the actual purchase source. Row 1 is valid for the stock CSV. Persist exclusions with reasons and control totals.

| Retailer source header | Proposed target | Interpretation that must be confirmed |
|---|---|---|
| Stock No / SKU | sku_code | Source item identifier, not GTIN or product style |
| Item Name / Product Description | product_name or source description | Display label, not identity or authoritative size/color extraction |
| Brand | brand_code through alias table | Explicit lookup; new brand creation separately confirmed |
| Closing Qty | on_hand_qty only if physically held | Snapshot date/location and count definition required |
| Available Stock | external available observation | Cannot map to on_hand_qty unless reservations/unavailable buckets establish equation; otherwise available-only observation lane |
| Retail Price / MRP | price item after confirming meaning | A retail price is not automatically MRP, ex-tax or realized sale price |

Profile scope: tenant, source system/export type, entity kind, template version and structural fingerprint. Include normalized header order/set, duplicate positions, sheet/table selectors, mapping, transformations, locale/date format/timezone, unit/currency/tax basis, quantity meaning, grain, defaults, lookup alias versions, totals rules and revision. Header fingerprint similarity can suggest an old profile; changed interpretation requires review. Never auto-reuse solely because column names match.

Use allowlisted deterministic transforms: trim, explicit locale decimal parsing (including confirmed Indian grouping), date format parsing, enum crosswalk, fixed configured constants, unit conversion, and type-dependent sign normalization. No arbitrary Python/SQL from uploaded files or LLM output. AI may propose mapping but cannot invent missing business facts. Ambiguous dates such as 03/04/2026 require a saved date convention. Preserve UTC timestamp and location business date. Date-only reports retain date grain; do not invent a transaction time.

Normalize category/brand/color/size/location using tenant-reviewed alias dictionaries, preserving raw values. `0L`, `2X`, `FR` from existing source descriptions must not be guessed into L/XXL/OS without an approved retailer crosswalk. Use exact/fuzzy matching suggestions with confidence; unresolved variants block affected rows. Never merge distinct Stock No values based only on a matching style or name. No inferred GTIN, supplier registration or product quantity split.

## 4. Validation rules

| Rule family | Required behavior | Error code example |
|---|---|---|
| Parse/type | Reject malformed CSV/XLSX, nonfinite numbers, fractional piece qty, invalid JSON, invalid encoding, impossible dates, empty required values | PARSE_ERROR / INVALID_TYPE |
| Keys | Require stable tenant/source entity IDs; reject duplicate conflicting keys within file; identical duplicates are explicitly marked skipped | DUPLICATE_KEY / CONFLICTING_DUPLICATE |
| Referential integrity | Resolve product/SKU/location/supplier/category within same tenant; no name-created SKU for V2 transactions | UNKNOWN_SKU / CROSS_TENANT_REFERENCE |
| Masters | Unique product code, SKU code, option signature; valid typed attributes; category-compatible size/color; parent required | INVALID_VARIANT |
| Prices | Currency explicit; no negative prices; explicit effective date and tax basis; validate selling price/MRP policy | INVALID_PRICE |
| Inventory | Explicit as_of/location/authority; nonnegative disjoint state buckets, reservations+damage+quarantine <= on-hand; old observations retained, not destructive | STOCK_SEMANTICS_REQUIRED / STALE_SNAPSHOT |
| Sales | sold>=0 integer, returns=0 in V2 sales; completed sold>0; cancelled rows financially zero; discount <= gross | NEGATIVE_SALES_QTY / INVALID_SALE_STATUS |
| Returns | returns>0 integer; original SKU/currency must match; cumulative linked returns <= remaining sold; no return before original recognition without approved source correction | RETURN_EXCEEDS_SOLD / ORIGINAL_NOT_FOUND |
| Financials | Decimal recompute; discount/tax allocation; original return credit caps; payment/refund allocation and state checks | FINANCIAL_MISMATCH |
| Purchases | Positive type-specific qty; valid PO/receipt references; overreceipt/invoice/return caps; type-aware stock behavior | INVALID_PROCUREMENT_LINK |
| Identity/corrections | Same key/same canonical payload skips; same key/different payload blocks until correction approval | EVENT_PAYLOAD_CONFLICT |
| Coverage | Reject overlapping detail+summary posting, partial snapshots presented as full replacement, or hidden unknown currency/tax basis | OVERLAPPING_COVERAGE |

Empty means unknown. Explicit zero means measured none. Defaults are allowed only if their basis is saved and shown: e.g. INR for a source whose export is contractually INR, or single known store for a verified single-location export. Do not default source stock date to upload date, unknown costs to zero, missing returned units to a guessed sale reversal, or missing size to one-size. Missing optional fields on master update preserve stored values unless the profile explicitly supports clear/null operations. Full replacement is an explicit mode with scope, not a blank-driven side effect.

Canonical identifiers are text, preserving zeros and Unicode; reject control characters. GTIN validates supported length and check digit, while allocation authenticity is separate. Validate HSN/GSTIN formats and applicable registry/configuration checks without inventing a registration. Protect downloadable error reports from spreadsheet formula injection by escaping text that starts with formula-trigger characters; never alter legitimate canonical identifiers silently. Store raw values securely for traceability.

## 5. Monetary basis and reconciliation

All canonical sale/credit/purchase input amounts are positive magnitudes. Purchase returns and customer credits get their negative reporting sign from event type. CSV quantities are never negative. Simple sales uses price before discount excluding tax; discount is total line amount. Whole-order discounts/freight must be allocated once across lines, in paise using deterministic largest remainder with stable line-ID tie-breaker. Store original allocation so partial return reverses the correct amount, not today's discount or MRP.

GST is computed from taxable base using effective classification and jurisdiction components. For inclusive source prices, reverse tax under the configured rate and source rounding policy before canonicalization. Retain source amount, derived canonical amount and rounding delta. Threshold: canonical line mismatch over INR 0.01 blocks by default; known source rounding policy can define a separate approved tolerance. Every nonzero rounding delta remains explicit. File totals reconcile to the sum of accepted canonical groups plus declared excluded/rejected groups. Do not hide a million one-paise differences under a loose file-level tolerance.

Transaction quantity, monetary value, return and refund controls are separate. Sum tender captures/allocations against receivable; pending payments are not captured. Cash refunds cannot exceed refundable settled balance without explicit approved exception. Credit/refund currency must match the original or use an explicit FX adapter. Report outstanding return credits, failed refunds, goodwill credits, credit notes with no physical receipt and physical receipts with pending credit separately.

Repeated order-level payment/refund header values in flattened rows are deduplicated by reference, never added per row. Conflicting repeated values reject the whole posting group. For split payments/multiple refunds use child adapters with schema `(source_system, payment_or_refund_reference, order_or_credit_reference, method, amount, currency, occurred_at, state, allocation_line_reference, allocated_amount)`. These are advanced interfaces, not implied support in the eight simple CSV contracts. Do not serialize mixed tenders into ambiguous text.

Actual reports: Sales `Net Qty/Net Amount` are already net; do not subtract Return Qty/Return Amount again. Map gross and return columns into separate reported measures and verify net equals gross less returns. Gross-profit file contains both tax-inclusive/exclusive cost and both markup/margin: compare like tax bases and weight by totals. Purchase voucher return signs require confirming voucher type and sign convention before positive normalization. A return row already negative is negated once by its typed adapter, never twice. Source blanks remain unknown unless the report definition explicitly makes them zero.

## 6. Idempotency and correction contract

Master upserts use tenant/code and external crosswalk keys with optimistic revisions. Immutable business event key is `(tenant, registered_source, entity_kind, external_event_id, external_line_id)` plus subevent identity where needed. Hash canonical payload and record schema/profile revision. File SHA256 catches exact reupload, but cannot deduplicate overlapping exports. File name, row number, SKU/date or amount hash cannot substitute for immutable transaction identity.

Same identity and payload returns previous successful result. Same identity and changed payload is a conflict, resolved by explicit revision/reversal/replacement with authorization and audit. A corrected master can upsert; a posted stock or financial event cannot be casually overwritten. Duplicate keys with differing values in one file block the affected group. If a source cannot supply stable event IDs, import into an analytical period lane with a declared unique key and replacement scope, or flag fingerprint-based best-effort replay limitations; do not promise exact-once posting.

The existing sales replay implementation is useful but its fallback occurrence keys cannot distinguish two identical genuine transactions across overlapping exports. V2 retains legacy semantics for V1 while requiring stronger IDs for operational posting. A central unpartitioned event registry enforces cross-date dedupe; its insert and all fact writes share a transaction. Unique keys, not a preflight SELECT alone, protect concurrent uploads.

## 7. Partial imports, scaling and rollback

Atomic unit is a coherent document/posting group: an order with all required lines/allocations; a return with credits/refunds/receipts; a PO/receipt/invoice document; a transfer event with both affected legs; an explicitly scoped stock snapshot. Do not accept a refund while dropping its return line or post half an inter-location transfer. Master rows may import independently after referential validation. A snapshot may be partial only when explicitly declared partial; omitted SKUs never become zero.

For tens of thousands of rows: server-side streaming CSV parser, staged rows, vectorized lookup resolution, database COPY into tenant-isolated staging, and set-based validation. Avoid browser-only parsing and ORM row-by-row queries for the full file. For millions: asynchronous durable job, streaming XLSX reader with archive/uncompressed size limits, object storage raw file, chunked staging (start around 10k–50k rows, tune by measurements), set-based validation/indexes, checkpointed posting groups and bounded worker concurrency per tenant. One huge order remains indivisible and may use a dedicated staged database transaction. Never split it arbitrarily at a chunk boundary.

Job progress reports staged/validated/posted/rejected/skipped counts and control totals. Retry only uncommitted groups; use advisory or row locks and uniqueness to avoid duplicate workers. Record source row locators, raw/canonical values, profile revision, error codes, severity and recommended correction. Error CSV includes original row, stable locator and errors, safe for spreadsheet opening. A corrected export replays successful identities without duplication. Apply quotas/backpressure and cancellable staging; cancellation cannot erase already posted groups silently.

Before posting, rollback is transaction abort/staging discard. After posting, a batch has mixed dependencies and may be referenced by later activity: offer a preflight reversal preview and append compensating events in reverse dependency order. Do not DELETE facts or restore an entire tenant snapshot over newer activity. Fiscal closed periods need finance-approved current-period adjustments. Preserve backup/restore as disaster recovery with tested procedures, separate from ordinary import undo. Original source files remain immutable and restricted; retain raw data according to configured policy and access controls.

Performance acceptance starts with a measured agreed benchmark: e.g. 100k-line representative file, bounded memory, no cross-tenant starvation, exact control totals and crash-resume correctness. Million-row throughput targets require measured hardware/database baselines; no invented processing-time promise. Track rows/sec, memory, DB waits, errors, retries and p95 preview/posting latency.

## 8. V1 and V2 coexistence and migration

1. Freeze and document current V1 accepted headers, aliases, defaults, negative-sales rejection, replay semantics and frontend/universal-route differences with contract tests. Keep route/version identification explicit. Do not widen V1 interpretation silently to accept new document types.
2. Add canonical V2 staging/validation behind a feature flag. Explicit schema_version (per row in delivered files) wins; mixed or mismatched entity versions fail. A saved source profile can declare version for external retailer files without the marker. Legacy exact header fingerprints suggest V1; ambiguous detection prompts mapping review rather than guessing.
3. Profile real data for orphan/catch-all parents, duplicate codes, ambiguous sizes, currencies, stale/as_of gaps, negative/clamped stock, overlapping period data and missing source IDs. Quarantine unresolved records with exportable diagnostics. Preserve original IDs and source crosswalks.
4. Backfill product_code from confirmed stable external_id; require mapping if absent. Map product_external_id to parent product; sku_code retains exact identity. Map unit_cost to reference_cost only with confirmed tax/currency basis; unit_price maps to a dated price only after tax-basis review. lead_time_days wins only when lead_time agrees or is empty; conflicting dual values block. Supply item-specific supplier lead times after supplier mapping.
5. Retain warehouse_inventory, forecast_demand and monthly_sales raw in a legacy metadata namespace with deprecation warnings. warehouse_inventory can become an opening snapshot only after SKU/location/as_of/basis confirmation, never a duplicate master-owned balance. monthly_sales needs actual period and definition to become a reported aggregate. forecast_demand needs model/cutoff/horizon metadata or stays legacy annotation. Missing metadata does not justify invented history.
6. Preserve V1 combined sold+returns rows in their legacy summary/event lane. For V2 conversion, create a stable derived return identity and record conversion ownership so the same return cannot also post through returns.csv. If return dates/values/original links are unavailable, retain a labeled aggregate and block operational credit/stock posting. Existing net monetary values must not have returns subtracted twice.
7. Legacy negative sales remain rejected in normal V1 canonical imports. A retailer-specific reviewed transformation may classify a source's negative rows as returns and emit positive returns; it must preserve original row/sign, identify event type and avoid double normalization. This is an explicit adapter, not a change in the no-negative-sales contract.
8. Dual-read/shadow compare derived reports for one pilot tenant. No dual-write decrement of stock. Compare count, quantities, currency, ex-tax values, returns, valuation and opening/closing stock by source/period/location. Do not compare the January–October profit report to October-only sales as if equal scope.
9. Cut over source authority at a reconciled count and watermark. Keep V1 adapter active into the canonical layer with warnings. Maintain old API response shapes/read projections until clients migrate. Publish schema versions and deprecation dates only after measured usage and customer communication. Version transformations independently from database migrations.
10. Migrations use MIGRATION_DATABASE_URL only; runtime remains restricted RLS role. Take and validate backup, rehearse upgrade/rollback, audit RLS and composite FK boundaries. Roll back feature routing where safe; retain append-only posted business history rather than deleting it to emulate the old schema.

## 9. Acceptance scenarios to become implementation tests

These are a specification. They have not been implemented or run against a V2 service.

| Case | Expected result |
|---|---|
| quantity_sold=-1 in sales | Row/group rejected; no facts or movement |
| returns=-1 or returns=1 in V2 sales | Reject; returns.csv is the single physical-return owner |
| Sale 2, then linked return 1, then return 2 | First return accepted; second rejected because only 1 remains returnable |
| Two concurrent returns each claiming last unit | One commits; other conflicts after row lock/constraint validation |
| Refund repeated with same ref and payload | One refund; no extra revenue or inventory reversal |
| Refund 945 after credit 945 | Settlement reduced 945; revenue reduced only by credit, not by refund again |
| Exchange M for L at same price | One M return/credit/receipt, one L sale/issue, net settlement difference zero |
| Cancel unrecognized order | No revenue/COGS/movement; reservations released |
| V1 sold+returns plus V2 equivalent return | Ownership crosswalk blocks duplicate return posting |
| Same event in two files or across date partitions | One event/movement through central identity registry |
| Same event ID changed amount | Explicit payload conflict, no silent overwrite |
| Unrecognized available-only stock | Retain available observation, require physical basis for on-hand; no double reservation subtraction |
| Physical on-hand 3, reserved 4 | Reject/inconsistency state; do not clamp to a healthy available zero |
| PO 10, receipt 6, invoice 6, return 1 | Pending receipt 4; net retained receipt 5; invoice does not add stock; return does not reopen PO |
| Transfer dispatch 5, receive 3, record loss 1 | Source issued 5, destination added 3, transit 1, loss 1; no duplicated physical stock |
| Older snapshot after newer ledger event | Observation retained; balance protected by authority/version/watermark |
| Crash after commit before ACK | Retry returns prior group result, no duplicate events |
| Unknown SKU/cross-tenant product FK | Affected group rejected under RLS and composite FK checks |
| Workbook formulas without cached result | Explicit error/approved calculation workflow; blanks never zero |
| Store/day report with no SKU | Accepted only into reported aggregate lane; SKU forecast unavailable |
