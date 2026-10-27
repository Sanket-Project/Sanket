# Remaining AI phases: implementation design addendum

Date: 2026-10-27

Status: approved by the user on 2026-10-27 ("proceed with the build"). Implementation evidence is tracked separately.

Related documents:

- [Approved architecture and import design](2026-10-27-deepseek-ai-layer-design.md).
- [Phase 0 evidence](../../audit/2026-10-27-ai-foundation/REPORT.md).
- [Remaining implementation plan](../plans/2026-10-27-ai-phases-1-to-4.md).

## Scope and authorization

The user now requests completion of all phases. Deliver all fourteen remaining features in Phase 1, Phase 2, Phase 3, and Phase 4, with import mapping first. Phase 0 exists in the shared checkout. Preserve existing work, including unrelated uncommitted changes.

The approved architecture remains the baseline. This addendum resolves implementation details that it left open. The original brief explicitly requires approval of the spec and plan before application code. The new request establishes the full delivery scope; this document does not label a newly written plan approved. Seek one approval of this addendum and the linked plan, then execute the complete scope with sequential phase verification. Do not merge or enable production features implicitly.

## Findings that affect implementation

These are observations of the checkout on this date, not claims about completed future features:

| Area | Current implementation | Required work |
| --- | --- | --- |
| AI foundation | `contracts.py`, `client.py`, `service.py`, `state.py`, `policy.py`, and `telemetry.py` are specialized to column mapping. Task name/schema are hard-coded in cache and telemetry. | Generalize through a private typed task registry without weakening mapping validation. |
| Imports | Analyze is first-row oriented and lacks explicit workspace/user dependencies; upload reparses independently. Integrations and onboarding have separate mapping forms. | Share one analysis/confirmation contract and one UI; bind preview and writes to the same file and selection. |
| Data quality | `/data-quality/fix` supports deduplication and dropping future/negative sales, with dry-run support. | Explain only real findings, preserve existing confirmation, add an explicit date interpretation preview before accepting ambiguous imports. |
| Notification preferences | `Settings.tsx` stores `weekly_digest` in browser local storage. | Persist per-user opt-in on the server. A browser toggle is not delivery configuration. |
| Delivery | WhatsApp provider/configuration exists. No email sender was found in application code or declared dependencies. | Add a configured email transport and durable delivery records. WhatsApp weekly delivery remains deferred as in the approved architecture. |
| Exports | The export router serves CSV and forecast XLSX; no ROI PDF endpoint was found. | Add a real source-linked PDF artifact and download path. |
| Scenarios | `ScenarioBody` already bounds physical inputs, and the existing simulator computes results. | Parse assumptions into this contract, then require confirmation before simulation. |
| ROI | Existing service separates modeled opportunities and approvals from realized savings that cannot yet be measured. | Preserve those distinctions in every narrative, export, and email. |

## Shared task boundary

Introduce a server-owned task registry. Each entry owns its task name, schema and prompt versions, strict input/output models, data projector, validator, feature flag, and allowed roles. Client requests select known tasks through feature-specific routes, never arbitrary prompts, models, URLs, SQL, or tool definitions.

Retain the mapping service's public behavior through a compatibility adapter. Parameterize cache identity, policy lookup, and safe telemetry with the actual task/version. Include language, actor authorization scope when applicable, and source snapshot identity in cache keys. Cache hits must recheck current workspace policy and access to every referenced source. Shared token limits remain workspace-wide.

Add privacy settings without silently broadening `headers_only`:

- Retain existing sharing levels and their defaults.
- Add `allow_aggregate_context: false` and `allow_product_names: false` in workspace AI settings. Owner/admin must explicitly enable them. `sharing=disabled` overrides both.
- Aggregate context permits approved, bounded engine facts, safe catalog descriptions, and screened user questions. It never permits transaction rows, customer contacts, supplier recipient details, or arbitrary document contents.
- Product cleanup requires explicit product-name permission. The server supplies opaque product/SKU IDs and a bounded, screened name; model output cannot include contact data.
- Pharma retains disabled sharing by default. No pharmaceutical safety, dosage, or clinical advice is generated.

Every task checks its own flag, the master flag, role, workspace industry, current membership, and the required sharing permission before loading/sending AI context. The settings UI explains each permission and its data categories. Existing manual features work without them.

## Grounded narrative contract

The server builds a fact ledger from existing engines. A fact contains an opaque ID, typed value or explicit missing state, unit/currency, period, source route/entity, source revision/run ID, and observed timestamp. Source links are generated from known routes and scoped IDs. The model cannot supply URLs, values, quantities, dates, or calculations.

Use a finite proposition registry with localized sentence templates. A validated narrative selects proposition IDs, fact IDs, approved qualifiers, and ordering. The server renders numbers, periods, units, and source links. For example, the model can select the existing stock-cover-versus-lead-time proposition; it cannot invent an order quantity or claim that low cover caused a demand drop.

Do not rely on a digit blacklist for factual integrity: spelled-out numbers and causal claims need validation too. New propositions must have explicit evidence predicates. Unconstrained prose is not accepted as the final answer. This is less expressive than arbitrary generated copy, but makes quantitative and causal grounding enforceable across all four languages. Label displayed results **AI-generated** because selection and ordering are model-assisted. Deterministic fallback content retains its existing label and is never presented as model output.

Narratives expose bounded structured blocks with source links, missing-data blocks, and separately labeled hypotheses. Missing facts stay missing. AI errors display `AI summary unavailable` alongside the existing source UI. Render as text/components; never execute model HTML or Markdown links.

## Phase 1 product boundaries

The approved import design controls workbook discovery, physical column IDs, formula-cache warnings, exclusions, multi-table selection, analysis binding, and successful-import-only format memory. Store confirmed profiles in a dedicated tenant-owned RLS table with revisions and uniqueness over workspace/kind/fingerprint. Do not store raw sample rows. Use short-lived workspace/actor-bound analysis metadata and file digest; reupload bytes for import and reject digest/selection changes. Keep raw files out of Redis, audit, and permanent profiles.

Onboarding reads actual upload coverage and the real connector registry, including planned/requested/live status. A connector answer can link to an existing setup flow, but cannot claim a planned adapter syncs data.

Data-quality suggestions refer to an allowlisted finding and fix action. Preview affected rows/counts from existing validated code. Ambiguous date formats require choosing a displayed interpretation before import; never rewrite stored dates by guessing. Confirmed mutations revalidate findings, scope, permission, and record versions, and audit atomically. Destructive repairs remain clearly described and require explicit confirmation.

Product cleanup produces per-field diffs with original values, proposed values, evidence, and an explicit unknown state. Use existing supported attribute vocabulary. Duplicate detection returns pairs of existing SKU IDs for review and never merges sales/SKUs automatically. Confirmed field patches use an allowlist, optimistic concurrency, and transactional audit. Do not fabricate a supplier directory or SKU identity rule.

## Phase 2 product boundaries

Decision explanations reuse signal evidence, planning readiness, stock/location coverage, and the original recommendation. They cannot change recommendation quantities or approve actions. Alert hypotheses distinguish missing ingestion/coverage from measured demand changes. The planning summary uses the current dashboard snapshot and disappears or refreshes when filters/source revision change. Industry wording uses the locked workspace industry and evidence predicates; industry alone cannot establish an expiry, harvest, markdown, or launch risk.

## Phase 3 product boundaries

Add per-user preferences for `en`, `hi`, `te`, and `ta`, with English the default. Persist these server-side under the authenticated user, using an additive migration for a preference JSON field if none exists at execution time. Preserve other settings. Localize templates, UI labels, units/date formatting, and generated ordering; factual values and provenance remain server-owned. Bundle a Unicode font licensed for redistribution with Devanagari, Telugu, and Tamil coverage for PDF rendering and inspect every script visually.

Weekly email is opt-in per active user, Monday at 08:00 in the selected valid IANA timezone, default `Asia/Kolkata`. Show the timezone and next delivery. Membership/AI policy/opt-in are rechecked at send time. Recipient addresses come from authenticated user records, never the LLM or a cross-workspace request. Add an SMTP transport using TLS, operator-configured host/from credentials, no arbitrary client-supplied transport. A missing transport returns a delivery-unavailable state and cannot count as sent. Test against a local mail sink. A workspace opt-out or disabled AI must not trigger model calls.

Use durable delivery rows, a unique tenant/user/local-week key, and leased attempts to prevent overlapping workers dispatching the same weekly email. Plain SMTP cannot guarantee exactly-once delivery across a crash after acceptance: mark ambiguous acceptance for operator review rather than automatically resending. Workers process tenant scopes without adding an RLS bypass or a superuser connection. Use the existing queue with tenant-scoped scheduled jobs; any dispatcher that enumerates due work needs an explicitly reviewed narrow database interface rather than `session_no_rls()`.

ROI PDFs show snapshot date, selected period, currency, assumptions, realized-versus-modeled status, and clickable source links. Add ReportLab as a declared application dependency, license-check bundled fonts, and keep rendering off the event loop. Emailing a report is a preview/edit/confirm action. Weekly summary opt-in authorizes that recurring weekly message only; it does not authorize report or supplier sends.

PO/supplier drafts require an already-accepted, unexpired purchase-order recommendation. Resolve quantities/SKU/currency from that decision. No supplier address is inferred from brand/vendor labels. Users enter or select verified recipient details in the review form; these details are attached locally after generation. Offer an editable email draft and copyable WhatsApp text. Email send needs explicit confirmation and fresh authorization. WhatsApp text is not auto-sent, and no new WhatsApp provider is introduced. Mark edits as user-edited; do not describe user-added numbers as engine-verified figures.

## Phase 4 product boundaries

Scenario parsing accepts bounded text and proposes existing `ScenarioBody` fields only. Numeric assumptions need exact spans in the user's text; deterministic conversion handles supported percentage and day/week units. A phrase such as “the monsoon is late” without a duration or a supported lever remains an unresolved assumption for the user. Never substitute a guessed delay. The UI shows assumptions, sources, unsupported terms, and an explicit Run simulation action. Only the existing simulator computes outcomes.

Data Q&A uses server-mediated read-only tools for analytics, trends, SKU lookup, inventory, and saved forecasts. Implement strict `ToolPlan` JSON with allowlisted operation names and bounded arguments. The server applies the same authentication, RBAC, industry, and validation dependencies as the existing APIs; no worker service account broadens the caller's access. Limit each question to three tool steps, the existing overall deadline, and one bounded reply. Native provider tool execution is not necessary: validated structured tool plans give the application control while leaving the provider transport's tool-call rejection intact.

The answer is rendered from the resulting fact ledger, with source links. Unknown tools, arbitrary endpoints/SQL, foreign IDs, unsupported filters, prompt injection, expired membership, empty evidence, and unavailable tools yield a clear refusal or missing-data answer. Never trigger forecast refreshes, repairs, exports, or messages from the chat. Default chat history is memory-only per workspace/user; clear it on workspace switch/logout. Do not persist raw questions or returned business records in audit/cache.

## Approval and completion criteria

Approval of this addendum and the linked plan authorizes implementation through all four remaining phases, including the described additive schemas/dependencies and test-only transport fixtures. Each phase remains independently reviewable on a `codex/` branch/PR. Do not claim a PR exists until created; attach each created PR to this chat. Keep features off by default and do not activate production email or send real customer messages as verification.

Completion requires all fourteen feature acceptance cases, fresh full frontend/backend checks, real PostgreSQL RLS/migration checks, Redis concurrency checks for changed state code, and running-app verification with mocked AI both enabled and disabled. Run the existing opt-in live eval only with explicit live-call authorization and approved non-sensitive fixtures; mock acceptance does not establish real DeepSeek mapping quality. Record missing credentials/provider access as an unverified live capability, not a passing result.
