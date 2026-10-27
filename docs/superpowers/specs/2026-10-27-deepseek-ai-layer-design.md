# SANKET AI layer and import column mapping

Date: 2026-10-27

Status: design and Phase 0 implementation plan approved by the user on 2026-10-27, with the requirement to use the latest DeepSeek Flash model. Phase 0 verification evidence is in `docs/audit/2026-10-27-ai-foundation/REPORT.md`.

## 1. Scope and delivery order

The immediate product priority is import column mapping: unfamiliar and multilingual headers, irregular workbooks, editable suggestions with confidence, and workspace-specific reuse of confirmed mappings. Forecasts and calculations remain owned by SANKET's existing engines.

The attached AI-layer brief asks for one architecture covering every phase, followed by an approved implementation plan for Phase 0 only. This document provides that architecture and details the first import feature. After design approval, write the Phase 0 plan, obtain approval for that plan, implement and verify Phase 0, and stop for review. The first subsequent feature plan is import mapping, ahead of the other Phase 1 features. Each phase has its own branch/PR and review. Later features described here are architectural scope, not authorization to implement them now.

Do not copy, reset, or commit unrelated local changes. The working tree already contains changes to `backend/app/config.py`, `backend/app/services/integrations/file_import.py`, and import tests. Implementation must preserve those changes and base its tests on the current behavior.

### Decisions from this conversation

- The user delegated data-sharing defaults: use headers only by default for non-pharma workspaces; pharma defaults to sharing disabled. AI itself is off for every workspace until enabled.
- An owner/admin can explicitly opt in to tightly bounded, redacted sample information. Never send customer PII or complete raw transactions.
- Reuse a confirmed format automatically, but retain the **Import** button. Choosing a file does not import it.
- Every new or changed mapping needs human confirmation, regardless of model confidence.
- Use DeepSeek's current Flash serving alias, `deepseek-flash`. As verified against the official catalog on 2026-10-27, it serves DeepSeek-V4.1-Flash-1017. Keep `LLM_MODEL` configurable and do not substitute a legacy or Pro model silently.

## 2. Findings from the current code and Redwine file

Inspected entry points:

- `backend/app/services/integrations/file_import.py`: `parse_table`, `_parse_xlsx`, `_build_header_map`, row mappers, and `import_rows`.
- `backend/app/routers/integrations_hub.py`: `/integrations/upload/analyze` and `/integrations/upload`.
- `frontend/src/pages/Integrations.tsx`: `UploadPanel`.
- `frontend/src/api/integrations.ts`: upload/analyze client methods.
- Existing workspace flags are `IndustryProfile.feature_flags`; general workspace settings are `Tenant.settings`.
- `services/usage.py` accepts the `MeterKind` enum. There is no AI token meter yet.
- `services/audit.py` provides metadata-only audit integration. Redis and HTTPX are already dependencies.

The current analyzer returns headers, an alias mapping, and three sample rows. The UI already permits editing before import. It does not show mapping provenance or confidence, remember formats, or select a sheet/header row. The parser scores first-row alias matches across sheets without considering import kind. The analyze handler has no explicit tenant/user dependencies; the new implementation must require authenticated workspace context before reading settings or invoking AI.

Located sample, inspected without modification:

`_to_delete/qa_artifacts/Redwine_Label_Fashion_Sales_and_Inventory_Record (1).xlsx`

SHA-256: `6d3c3ce4fcd7f0ee94aaa111f4632bd510c997449c0748d607206d03f1a143d6`

| Sheet | Physical rows | Columns | Relevant observations |
| --- | ---: | ---: | --- |
| Executive Summary | 14 | 8 | Empty first row, merged dashboard cells, summary formulas. Not a data table. |
| Sales Ledger | 501 | 15 | Header in row 1, 500 detail rows, nine recognized alias fields. |
| Warehouse Inventory | 151 | 13 | Header in row 1, 150 detail rows, four recognized alias fields. |

The existing parser selects `Sales Ledger` regardless of whether the requested import is sales or inventory. For sales it misses `Unit Retail Price` and `Fulfillment Warehouse`. For inventory it misses `Stock On Hand (Qty)` and `Warehouse Code`, among others. This demonstrates that solving semantic aliases alone would leave inventory imports pointed at the wrong table.

All 1,500 formulas in Sales Ledger and all 300 formulas in Warehouse Inventory lack cached values in this file. The parser currently uses `data_only=True`, so those cells are missing values. Do not claim to have read their computed results. Existing sales mapping can derive revenue from quantity and unit price; this remains deterministic and must be identified as a calculation, not a spreadsheet value. Mapping does not introduce a general Excel formula evaluator.

Baseline command: `cd backend; uv run pytest tests/test_file_import.py -q`

Observed output: `45 passed in 1.26s`. This tests the current importer, not the proposed feature.

## 3. Alternatives and chosen approach

1. **Extend aliases only.** Cheap and deterministic, but cannot cover arbitrary languages and unknown business labels. It also does not solve layout discovery.
2. **Send the whole workbook to an LLM.** Gives the model more context, but violates minimization, increases cost, and lets model decisions affect too much of the import.
3. **Local structure detection, saved profiles, alias matching, then bounded AI suggestions. Recommended.** The server owns parsing, validation, calculations, exclusions, and writes. The model selects from supplied column/table identifiers and allowed field names. Human approval is the boundary between suggestions and a new import format.

No model call is necessary when a saved profile passes validation or all relevant columns have deterministic mappings. Trigger AI when a relevant column is unresolved, required coverage is missing, or a plausible layout is ambiguous. Optional columns matter too: Redwine's missing unit price must be eligible for a suggestion even though sales quantity and date already match aliases. Ignore clearly empty/decorative columns locally; allow an explicit retry/request for unresolved columns.

## 4. Shared AI foundation: Phase 0

### Provider boundary

Create `backend/app/services/llm/` with small modules for configuration/client, policy, validated contracts, and request orchestration. Use the existing async HTTPX dependency to call an OpenAI-compatible chat-completions interface, rather than adding a provider SDK. DeepSeek is the initial provider. `LLM_BASE_URL`, `LLM_MODEL`, and `DEEPSEEK_API_KEY` come from server configuration.

Verified provider defaults on 2026-10-27: `LLM_BASE_URL=https://api.deepseek.com`, `LLM_MODEL=deepseek-flash`, using `/chat/completions`. The official [model catalog](https://api-docs.deepseek.com/quick_start/pricing) identifies the current backing release as **DeepSeek-V4.1-Flash-1017**. Use the documented current alias so later Flash serving upgrades do not require code changes; record the verification date and any version reported by the API rather than claiming the alias pins an immutable release. Recheck the catalog before implementation and release, and invalidate AI caches when a known serving revision changes. Do not use retired `deepseek-v4-flash` aliases as the configured default.

For the bounded mapping task, explicitly send `thinking: {"type": "disabled"}` rather than inheriting the provider's default thinking behavior. The documented [thinking-mode switch](https://api-docs.deepseek.com/guides/thinking_mode/) supports this on the current Flash model. Set `response_format: {"type": "json_object"}`, include a JSON example in the task's system prompt, and cap output tokens according to the [JSON-output guide](https://api-docs.deepseek.com/guides/json_mode). JSON mode does not enforce SANKET's schema: reject empty, truncated, or invalid responses through server validation. Isolate DeepSeek-specific request options behind configuration/adapter capabilities so another compatible provider can be selected without changing business code.

Treat the key as a secret type. Never return it to the frontend, serialize it in settings, log authorization headers, or log provider response bodies on failures. Add empty/example configuration entries only. A workspace has no provider URL override: only server operators configure outbound destinations.

All calls enter through an orchestrator requiring verified workspace ID, actor, industry, task, schema version, and a bounded input contract. Check feature flags, sharing policy, rate/cost allowance, and cache before making a request. Recheck policy before returning cached output. No generic endpoint accepts arbitrary prompts.

### Workspace flags and sharing policy

Use the existing industry profile's `feature_flags["ai_enabled"]`, default false, plus task flags such as `ai_import_mapping`, also false by default. Preserve all existing flags. Store the typed `ai.data_sharing_level` in workspace settings with values:

| Level | Outbound data |
| --- | --- |
| disabled | No AI requests. This is the default sharing level for pharma. |
| headers_only | Sanitized column labels, local column/table IDs, allowed fields, and bounded structural/type hints. No cell values. Default for other industries. |
| redacted_samples | The above plus up to three projected/redacted examples per selected candidate table. No complete transaction rows. |

Only owners/admins can enable AI or change sharing. Audit policy changes. A Phase 0 settings service/schema can be exercised internally and by tests; its customer-facing controls arrive with the import feature. There is no customer-facing AI UI in Phase 0.

Redacted examples replace order/customer/SKU identifiers with local tokens, remove names/contact/address/payment/free-text notes, and use type or format hints instead of exact sales quantities, prices, and dates. Product names are allowed by the brief, but include them only when explicitly identified as product-name fields and free of detected PII. Unknown columns contribute type hints, not unreviewed string values. Sanitize headers containing obvious contact information too. If safe projection is uncertain, omit values and use headers only; disclose that policy may reduce suggestion quality. Redaction is an allowlist, not a promise that a denylist catches every kind of PII.

### Contracts and factual integrity

Validate provider output with strict Pydantic schemas: forbid extra keys, bound lengths/collection sizes, reject unknown enums, and validate every referenced input ID. Invalid JSON/schema output is unavailable, never repaired into plausible facts.

For mapping, the model returns only supplied table/column IDs, canonical field enums or ignore, confidence enums, and bounded reason enums. It cannot emit transformed data, formula results, SQL, or arbitrary explanatory prose. Confidence is **High / Medium / Low**, explicitly labeled as a model estimate, not a calibrated percentage. An unresolved column displays **Unknown**. There is no invented numeric confidence.

For later narrative tasks, provide a typed fact ledger with source IDs, values, units, time windows, and API links. Numeric output must reference an existing fact; the server renders its value and source. Reject unbound numeric claims, changed units/time windows, and computed results. Any free text also undergoes numeric/provenance validation; if that cannot establish grounding, do not display it. Quantitative sentences should use server-rendered fact references/templates rather than trusting free-form prose, including spelled-out quantities. The model never supplies forecasts or performs arithmetic.

### Reliability, caching, limits, and observability

- Provisional import budget: one end-to-end AI deadline of 15 seconds; at most one retry for transient connection/429/5xx errors with jittered backoff and remaining-deadline checks. No retry for invalid output or authentication/config errors. Tune with the opt-in eval.
- Circuit breaker per provider/model: open after five qualifying consecutive failures, cool down for 60 seconds, then permit one half-open probe. Use shared state across workers.
- Cache validated results for 24 hours in Redis. Key by workspace, task, effective sharing policy, provider/model, prompt/schema version, and a digest of the exact minimized payload. Never cache raw files or unredacted rows. Add request deduplication for concurrent identical work.
- Atomic Redis workspace limits start at 10 requests/minute and 100 requests/day, configurable by operators. Add configurable per-task input/output caps and a workspace token allowance. Missing billing quotas must not mean unlimited AI usage.
- If shared cache/limit infrastructure is unavailable, disable AI suggestions with an unavailable state; local parsing/manual import continues. Do not fall back to unbounded calls from every worker.
- Extend `MeterKind` and its PostgreSQL enum for AI input/output tokens. Record actual returned usage via `services/usage.py`, with idempotency per provider attempt. Cache hits consume no provider tokens. Missing token usage is recorded as unknown, not zero; enforce conservative reservations for limits until reconciled. Do not invent currency costs without configured, versioned prices.
- Write call attempts/outcomes/cache hits through `services/audit.py` using request ID, task, model, latency, token counts if known, cache status, schema version, policy level, and safe error codes. No prompt, cell, filename, product, or generated text in logs. Meter/audit failures must be isolated from database transactions so swallowed SQL errors cannot poison a later business write; use separate scoped transactions and test the failure paths. If required recording cannot be established, stop further AI dispatch until healthy and report the condition.
- Disable request/response-body logging in the provider transport. Isolate untrusted uploads in JSON user-data blocks; system instructions prohibit following embedded instructions. No tools or action execution are available to the mapping model.

## 5. Import structure and preview

### Local table discovery

Introduce a structured parser result alongside the legacy `(headers, records)` adapter. Keep current callers working; migrate analyze and confirmed import together. Both must use the same selected table specification, not independent guesses.

For CSV/TSV and Excel, inspect a bounded leading region for likely headers. For Excel, enumerate sheets and consider one- or multi-row headers, known aliases, text-to-data transitions, populated widths, merge ranges, and following-row type consistency. Rank candidates by the requested import kind. Non-English headers must still produce candidates through structural evidence when alias score is zero. Uncertain candidates remain selectable rather than silently choosing the first sheet. Permit a manual header-row selection beyond the discovery scan.

Provisional resource bounds: existing 10 MiB compressed upload limit; 100 MiB expanded ZIP limit; 20 sheets; 200 columns; 1,000,000 examined cells; automatic header search in the first 100 rows per sheet. Validate before expensive work where possible. Exceeding a limit produces a clear error or requests a smaller export; never silently truncate an import. Run blocking workbook parsing off the async event loop.

Each table candidate includes a server-issued ID, sheet name/index, header row span, physical column IDs, original labels, disambiguated display labels, source row numbers, merge information, local mapping coverage, and warnings. Duplicate/blank headers retain distinct column IDs. Do not put row dictionaries under duplicate text keys and lose cells. Normalize Unicode for comparison while retaining the original header for display; do not strip Hindi combining marks as a substitute for semantic matching.

Propagate merged header labels only inside their actual merge spans to form a composite header. Skip merged title blocks as headings. Never forward-fill quantities, dates, or identifiers through merged data cells. Rows whose identity depends on a merged data cell require a visible warning/manual resolution; do not manufacture observations.

Blank rows, repeated header rows, and confidently identified subtotal/grand-total rows are classified locally using their position, labels, formula/merge evidence, and missing detail identity. A product merely containing the word "Total" is still a detail row. Ambiguous possible summaries need review before import. Provide count, reason, physical row number, and preview for exclusions. The model may flag bounded row IDs for review but cannot silently drop them. Recompute row exclusions on every new file; never save absolute excluded-row numbers as a reusable rule.

For multiple data sheets, expose every candidate and support an explicit selection of one or more compatible tables for the chosen import kind. Map and preview each independently. Import a selection in one atomic transaction after all selected tables validate; never merge unrelated sales and inventory tables in one operation. A later inventory import can select a different table in the same workbook. Existing replay-safe sales identity remains in force across selected tables.

### Formula handling

Read cached values and separately detect formulas in the selected region. Do not execute workbook macros or externally linked formulas. Report missing cached values with source cell locations. Required fields with no usable value block or fail their rows. Optional missing fields remain missing. Deterministic existing conversions and derived revenue remain available and are identified in the preview. Never send formulas to the LLM to calculate them.

### Mapping resolution

Resolve each selected table in this order:

1. Exact compatible workspace-confirmed profile.
2. Existing deterministic aliases for that import kind.
3. AI suggestions for unresolved relevant columns or ambiguous candidate layouts, when allowed.
4. Manual selection for anything unresolved or AI-unavailable.

The model can select only supplied candidates and physical column IDs. Validate one-to-one field assignments, field applicability by kind, required coverage, and compatibility with local value types. Never overwrite a saved or deterministic assignment without showing a conflict for review. Low confidence is always visible, and high confidence never authorizes an import.

Use a shared field registry for backend validation and frontend choices. Offer only fields the corresponding row mapper actually persists. For example, the current inventory mapper does not persist reorder thresholds even though an alias exists; show `Safety/Reorder Threshold` as unsupported/ignored rather than pretending it updates a threshold. Adding cost/reorder storage is a separate approved change. Preserve existing supported but currently hidden fields, such as sales warehouse, returns, stockout indicators, line ID, and product size/color, in the mapping UI.

## 6. Confirmation and format memory

### API contract

Extend `/integrations/upload/analyze` with verified tenant/user/industry context and optional explicit table/header choices. Preserve the current response fields for ordinary unique headers, and add a typed structured response for the enhanced UI:

- analysis ID and expiration, file digest, parser/schema version;
- selected tables and all selectable candidates;
- per-column assignment, provenance (`alias`, `saved`, `ai`, `manual`, `unmapped`), estimated confidence or unknown, and reason code;
- exact local sample preview, row exclusions, missing required fields, and formula/layout warnings;
- AI state (`disabled`, `policy_blocked`, `available`, `unavailable`, `rate_limited`), and saved-profile match status.

Local samples shown to the authorized user are distinct from the minimized provider payload. No raw upload is retained by the AI cache. Bind analysis to workspace, file digest, kind, selected table descriptors, and parser version using an opaque expiring server-side record. Changing a selection invalidates the old analysis and requires reanalysis. Requests from another workspace, expired analyses, or changed file bytes are rejected.

The confirm/import request sends the original file, analysis ID, explicit final assignments/exclusions, identity/currency options, and whether to remember the format. Validate every field against the selected file before writing. Validation must occur after resolving column IDs; do not count a mapping to a nonexistent header as required coverage. Reject unknown fields, duplicate assignments, and tampered/foreign profile IDs.

Keep the legacy manual import contract functional for existing clients, under the same strict mapping validation. It must never invoke AI or use a suggestion as confirmed data. The enhanced UI always sends the structured analysis contract for nontrivial layouts. Analyze has no domain-data writes; it may create an ephemeral analysis record and record AI usage/audit metadata.

### User experience

Stay in the current UploadPanel and follow `frontend/DESIGN.md` and its icon module. Display, in order:

1. Import kind and file.
2. Table/sheet and header-row selection, with uncertainty visible.
3. Local preview with physical row numbers and exclusion review.
4. A mapping row for every source column: original header, a few local example cells, target-field selector including Ignore, confidence, and provenance. Label AI suggestions **AI-generated**. Use text as well as color; attach accessible labels to selectors and inline errors.
5. Required-field/conflict summary, formula warnings, and existing sales identity/currency controls.
6. A checked **Remember this format for this workspace** option, followed by **Confirm and import** for a new/edited format, or **Import** for an unchanged saved format.

Human edits clear the previous model-confidence display for that assignment. A saved assignment shows **Confirmed by your workspace**, not a probability. AI failures show **AI mapping unavailable — map columns manually** with a safe reason and optional explicit retry. Preserve all local preview/editing controls. Ignore or exclusion decisions are included in the final confirmation.

With a matching saved format, fill assignments automatically, identify the saved profile used, skip a compulsory mapping review, and retain the Import button. Users can expand/edit the mapping. An unmatched layout, missing required field, type drift, new source column, or ambiguous profile sends the user back to review. Workspace switching, changing kind/file/sheet, or a late analyze response must not reapply another selection's state. Disable double submission and preserve visible errors.

### Storage and reuse

Add an `import_mapping_profiles` table with tenant ID, industry, import kind, profile ID/version, user-visible name, structural fingerprint, table descriptors, canonical field assignments by stable column position/label path, reusable local exclusion policy, sales identity/currency choices, creator/updater, and timestamps. Do not store sample data, whole files, absolute source data-row exclusions, or unconfirmed model output.

Enable and FORCE PostgreSQL RLS with the repository's tenant-GUC policy on this table, grant only application-role access, and use `db.session(str(tenant_id))`. Migrations alone use `MIGRATION_DATABASE_URL`. Add a tenant-scoped unique key on kind/industry/fingerprint/version as appropriate and optimistic version checks for edits.

The fingerprint describes ordered normalized header paths, duplicate positions, import kind, selected table roles, header structure, and parser version. It excludes filename, sample values, totals, changing row counts, and title/notes content. Header offsets may move if the same unique structure is rediscovered; changed labels/order/merged structure need review in the first version. Conservative matching is preferable to applying a plausible but wrong mapping. Type-compatibility checks run on every file even when the fingerprint matches. Reuse saved identity/currency choices visibly, with existing currency mismatch validation intact.

Save only after explicit confirmation and successful import in the same transaction. Validation failures, rolled-back writes, and a zero-accepted-row result do not create a trusted profile. Do not overwrite a profile from another concurrent confirmation silently. Allow users with import permission to apply profiles; owners/admins manage disabling/deleting profiles. Saved mappings continue to work with AI disabled because they are human-approved configuration.

## 7. Redwine acceptance criteria and test strategy

During implementation, add a stable test fixture from the located workbook without moving/restoring deleted working-tree paths. Prefer a structural/minimal fixture for CI and an optional local path to the exact workbook for the real-file regression. Do not commit private source records without confirming their fixture suitability. Pin the exact workbook hash in local acceptance evidence.

### Exact-file cases

- Sales selects `Sales Ledger`, never Executive Summary or Warehouse Inventory; analyzes 500 detail rows.
- Inventory selects `Warehouse Inventory`, never Sales Ledger; analyzes 150 detail rows.
- Mock suggestions map `Unit Retail Price` to `price` and `Fulfillment Warehouse` to `warehouse` for sales; `Stock On Hand (Qty)` to `available` and `Warehouse Code` to `warehouse` for inventory.
- Unmapped/unsupported cost, profitability, and threshold columns are visible; no invented field writes.
- Report formula caches as missing. With confirmed unit price and quantity, gross revenue matches the existing mapper's deterministic multiplication; inventory asset-value/status formulas are not fabricated.
- Analyze creates no products, SKUs, sales, or stock. Confirm/import writes only the selected table(s). Test imported records against the selected source with existing validation/replay behavior, not just a claimed total of 500/150 successful imports.
- Remember sales and inventory profiles separately in workspace A. Re-upload uses them with no provider call and still requires the Import button. Workspace B gets neither profile.

### Additional mocked fixtures

- `Qty Sold (Pcs)`, unknown abbreviations, Hindi and at least one additional non-English language.
- Title and notes rows; a delayed header; merged and multi-row headers; blank and duplicate headers; multiple sheets and multiple selected compatible data tables.
- Repeated headers, interspersed subtotals/grand totals, a real SKU/product named Total, genuine zero-sales rows, and ambiguous summary rows requiring review.
- Changed column order, missing/extra columns, changed table/type structure, changed filenames, moved title/header offsets, and overlapping saved profiles.
- Invalid JSON, unknown fields/columns, repeated assignments, invalid confidence, oversized output, prompt injection in headers/cells, policy changes, missing key, timeout, circuit opening/recovery, rate limits, cache isolation, and Redis failure.
- Real PostgreSQL RLS tests under a non-superuser application role: foreign-profile reads/updates/deletes and foreign/forged analysis IDs fail. In-memory mocks alone do not establish tenant isolation.
- Meter/audit idempotency, retries with actual usage, absent usage, failed audit transactions, canceled requests, and policy enforcement on cached output.
- Frontend: human edits, missing fields, exclusions, saved mapping reuse, change-file/kind/workspace races, unavailable AI, stale analysis, duplicate submits, and keyboard/small-screen behavior.

Use strict TDD: add each failing test, observe the intended failure, add the smallest implementation, then refactor while green. Mock all provider calls in unit/integration/E2E tests. Add a separate opt-in real-provider eval that uses non-sensitive fixtures, refuses disabled sharing, caps cost, and reports structural selection/mapping accuracy and confidence consistency. A mock result on Redwine does not establish real DeepSeek quality; the opt-in eval must be run before claiming that quality was verified.

Required completion checks for each implementation phase:

- Frontend: `npm run typecheck`, `npm run lint`, `npm test`.
- Backend: `uv run pytest`, plus focused parser/provider/RLS tests and migration upgrade/downgrade checks for touched schema.
- Run the app with AI off and exercise the existing manual upload. For the import phase, also exercise new confirmation and saved reuse in the running UI.
- Systematically review the diff, report exact output and any failures/skips, and request review before merging.

These full checks have not been run for this design-only change. No new production code or tests have been written.

## 8. Architecture for later phases

All later features reuse the same flags, sharing policy, fact contracts, audit/metering, cache, limits, and honest unavailable state. Each gets its own approved plan and tests. Do not add empty UI panels or placeholder summaries in advance.

| Phase | Feature | Grounded input and action boundary |
| --- | --- | --- |
| 1 | Import mapping, first | This document's bounded table/column selection and human-confirmed import. |
| 1 | Onboarding helper | Locally calculated upload coverage and the actual connector catalog. Coverage counts/months/store counts come from the server. Connector availability must reflect the catalog, not a hard-coded claim that every connector works. |
| 1 | Data-quality explanations | Existing `data_quality` findings and allowed repair operations. Describe proposed changes, preview affected records, require confirmation, and execute existing validated code. |
| 1 | Product cleanup | Policy-approved product names and allowed industry attributes from `fashion_sizes.py`/industry context. Validate suggested attributes/categories; duplicate candidates refer to existing SKU IDs through `sales_identity.py`. Confirm before changes. |
| 2 | Decision explanations | `signal_evidence.py` and existing transfer/allocation/reorder decisions with source-linked fact IDs. No new decision quantities. |
| 2 | Alerts/anomalies | Existing anomaly, shortage, signal, and data-gap evidence. A likely cause is labeled a hypothesis; insufficient evidence stays explicit. |
| 2 | Planning brief | Current PlanningBriefDashboard calculations, decision IDs, and fact links. Place an AI-generated narrative above the unchanged source metrics. |
| 2 | Industry wording | Use workspace industry context and archetype registry: expiry, harvest/season, end-of-season stock, or model launches only when supported by supplied evidence. Never change the locked workspace industry. |
| 3 | Weekly summary | Opt-in notification settings; Monday in the chosen workspace timezone; send through existing approved notification delivery. AI drafts only from the current fact ledger. Disabled/missing AI yields existing factual notification behavior, never invented prose. WhatsApp integration is deferred until a provider/workflow is approved. |
| 3 | ROI report | Existing ROI/financial calculations and export path. Produce a source-linked PDF/email draft; explicit human review and send action. The model does not calculate savings. |
| 3 | Regional languages | User setting for English, Hindi, Telugu, Tamil. Translate narrative/labels, preserve source IDs, units, values, and provenance. Validate again after translation. |
| 3 | PO/supplier drafts | Only an already-approved reorder and known supplier data. Require edit/review/send confirmation using existing authorized delivery. A generated draft never sends itself. |
| 4 | Natural-language scenarios | Strict schema maps text to allowed existing scenario-engine parameters. Show the parsed assumptions, require confirmation, run that engine, then explain returned facts. |
| 4 | Data Q&A | Read-only allowlisted tools call existing analytics/trends/SKU/inventory/forecast service APIs under the requesting user's role and workspace. No SQL generation/execution, arbitrary URLs, or cross-workspace context. Bound tool steps and tokens; answer unavailable when no evidence exists. |

## 9. Approval checkpoint

The user approved this design on 2026-10-27 and required the latest DeepSeek Flash model. Prepare the **Phase 0 only** plan as 2–5 minute tasks with verification per task, obtain plan approval, and execute it with TDD. Stop after Phase 0 verification for review; import mapping is the next planned feature.

This checkpoint follows the attached brief's explicit instruction: **"Do NOT write code before the spec and plan are approved by me."** It is not an additional approval policy inferred by the agent.
