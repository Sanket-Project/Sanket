# Management reports and supplier drafts — implementation evidence

Date: 2026-10-27. This report covers Phase 3 R/M tasks only; the parent report
tracks preferences, weekly delivery, whole-project checks, and browser QA.

## Delivered behavior

- `/export/roi.pdf` downloads a current-member, industry-scoped factual ROI PDF
  with `Cache-Control: no-store`. The existing ROI engine owns all amounts,
  nulls, currency groups, periods, basis text, and the three financial tiers.
  No grand total or fabricated realized savings is introduced. Rendering runs
  outside the event loop, uses a bounded engine report, and embeds licensed fonts.
- `/management/roi/preview` provides an editable email and short-lived,
  actor/workspace/period/language/snapshot-bound review token. Sending requires
  explicit confirmation, current owner/admin permission, the same source
  fingerprint, and the shared durable delivery identity. A deterministic PDF
  attachment freezes the reviewed timestamp and supports idempotent replay.
- Supplier previews require an accepted, unexpired purchase-order recommendation
  with an approved quantity. The accepted quantity, current SKU, currency, and
  record version determine the draft. Supplier contact remains absent until the
  user supplies a verified email. The UI offers editable email and copyable
  WhatsApp text; WhatsApp sending is not implemented or claimed.
- Supplier and ROI sends recheck current source eligibility inside the durable
  claim transaction and again through the shared transport's final pre-DATA
  authorization callback. The supplier check locks the current recommendation
  and SKU and rejects an intervening version/quantity change.
- Optional AI summaries select only server-owned facts through the existing
  registry/policy/admission boundary. Disabled AI performs no provider dispatch.
  Missing/unavailable AI leaves the factual artifact available. The supplier
  provider input contains neither recipient details nor SKU names/codes.
- Report, supplier-draft, and email content supports English/Hindi/Telugu/Tamil,
  using the parent's translation catalog and persisted language preference.
  Financial sources remain immutable. Editable text is visibly marked
  user-edited. Reviews reset when scope, period, or language changes.
- Downloads and review/send requests abort on component teardown. A late PDF
  response cannot trigger an automatic download after a context switch.

## Files

- `backend/app/services/management_reports.py`,
  `backend/app/routers/management_reports.py`, `/roi.pdf` in the existing export router.
- `backend/app/assets/fonts/`: original OFL Noto inputs, renamed composite
  SANKET Report Sans derivatives, license, reproducible build script, hash manifest.
- `backend/pyproject.toml` and `backend/uv.lock`: declared
  `reportlab[shaping]>=4.4.0` dependency.
- `ManagementReport.tsx`, `SupplierDraft.tsx`, `ReviewedEmail.tsx`,
  `ArtifactSummary.tsx`, their tests, ROI/decision integration, and readable
  Phase 3/4 task labels in `AISettings.tsx`.
- `reports/`: synthetic artifact-only source fixture, four localized PDFs,
  Poppler page renders, and four supplier draft JSON fixtures.

## RED → GREEN observations

1. Initial service tests failed to import the absent implementation; nine pure
   report/eligibility/PDF tests then passed.
2. Four route tests failed with actual HTTP 404 responses before route wiring;
   authenticated download, confirmation, and foreign-preview cases passed after wiring.
3. PDF bytes differed across repeated renders; invariant PDF metadata and frozen
   reviewed timestamps made repeated renders stable.
4. AI-off and fact-selection tests failed for the absent summary helper; the
   gated helper passed without transmitting contacts or free-form prose.
5. A trusted-origin link test failed against relative email/PDF links; links now
   use only the server-configured application origin and fixed source paths.
6. Visual inspection found missing Latin glyphs in the original Indic fonts.
   Font-run tests exposed unsupported Latin characters. Mixed-font shaping then
   corrupted punctuation/parenthetical words; a complete-paragraph font coverage
   test failed. Composite Latin/Indic fonts resolved that root cause. All four
   PDFs were regenerated and inspected; Latin codes, P90, native scripts, and
   source URLs are readable without tofu or clipping. Source sections stay together.
7. A removed-member test raised an internal ValueError instead of an explicit
   refusal; the boundary now returns HTTP 403 before projecting a report.
8. A regression changed the accepted quantity between the first check and
   delivery claim and observed an incorrect successful dispatch. Same-session
   final eligibility callbacks now refuse the changed version before SMTP DATA.
9. A delayed PDF response after report-context replacement still created an
   object URL/download. The regression now passes with lifecycle cancellation
   and a post-await abort guard.

## Commands and actual results

| Check | Actual result |
| --- | --- |
| `uv run pytest tests/test_management_reports.py -q --tb=short` | 24 passed, 1 existing passlib/Argon2 deprecation warning; final run before the two additional TLS acceptance tests. |
| `uv run pytest tests/test_management_reports.py -q -k actual_local_tls_sink --tb=short` | 2 passed, 24 deselected. Both complete authenticated review/send APIs delivered to a real loopback STARTTLS sink. ROI contained a valid PDF attachment; supplier email contained the approved 37 units, not the recommended 50. Only synthetic recipients were used. |
| `uv run pytest tests/test_management_reports.py -q -k 'inside_delivery_claim or attaches' --tb=short` | 2 passed: intervening supplier mutation refused; report attachment replay did not redispatch. |
| `npm test -- --run src/components/ai/ManagementArtifacts.test.tsx src/components/ai/AISettings.test.tsx src/pages/ROIDashboard.test.tsx src/pages/Decisions.test.tsx` | 4 files, 19 tests passed. Existing React Router future-flag warnings only. |
| `npx eslint` on all changed management components, tests, settings, ROI, and decisions files | Exit 0, no diagnostics. |
| `uv run ruff check app/services/management_reports.py app/routers/management_reports.py tests/test_management_reports.py` | All checks passed after scoped import/format/assertion cleanup. |
| `uv build --wheel --out-dir ../tmp/phase3-wheel` + wheel inspection | Successful; all seven original/derived TTF assets are packaged. |
| `git diff --check` on changed management files | Exit 0; existing line-ending conversion notices only. |
| `npm run typecheck` during integration | Found the temporary root-owned dropdown-review unused React import; root handled this separately. This report does not relabel that invocation as passing. |

Command logs are in `tmp/phase3-reports-*.log`. The parent run owns final full
frontend/backend gates after integration. No commit, PR, hosted deployment,
production SMTP activation, real-recipient send, or live DeepSeek evaluation is
claimed by this report.

## Artifact reconciliation and remaining acceptance boundaries

The PDF fixture is explicitly synthetic and does not write any workspace. Its
approved quantity is 37, baseline 100, unit cost INR 200: working-capital
difference is INR 12,600 and derived carrying cost is INR 362.47 using 25% and
42/365. These are separate measures, never summed. The INR 10,000 revenue
figure comes from the synthetic engine input; realized savings remains null.

English and Tamil fixtures use two pages; Hindi and Telugu use one. Sources
remain clickable, grouped, and readable. Default local artifact links use the
configured localhost application origin; deployment must configure its real
operator-owned origin. PDF rendering/visual checks and component/API tests are
complete for this scope. The parent run records actual in-app desktop/narrow
browser flows and broader degraded-provider coverage; those are not inferred
from unit tests or PDF screenshots here.
