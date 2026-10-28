# AI phases 3–4 and dropdown completion verification

Date: 2026-10-27. Local checkout: `codex/ai-phase-2`. Existing unrelated changes were preserved. This report supplements the phase-owned reports, rather than claiming their historical results as a fresh combined run.

## Delivered scope

- Shared single-select arrow spacing and themed native pickers in supported browsers; browser-native accessible fallback on older engines. Searchable menus anchor to the trigger, respect actual scroll boundaries, and keep label/helper text outside the popup anchor.
- Phase 3: self-owned persisted English/Hindi/Telugu/Tamil summary preferences; opt-in timezone-aware weekly email with durable scoped jobs, recoverable claims, bounded retries, idempotency and final eligibility checks; actual ROI PDF downloads and reviewed email; accepted/unexpired purchase-order supplier email and copyable WhatsApp drafts.
- Phase 4: exact-span numeric scenario proposals followed by explicit review/apply/run; deterministic simulation results; finite authorized read-only Q&A across sales, inventory, trends, catalogue and saved forecast sources. Chat questions are ephemeral; identity changes discard previous results.
- Localized fact labels, units, statuses, financial basis disclosures and generated summaries preserve original numbers, timestamps, currencies and citations. Multi-fact summaries expose every safe citation.

## Investigation and review

Observed RED/GREEN regressions covered trigger-versus-label anchoring, content-sized main versus scroll surface, disabled select cursor specificity, saved locale changes, every-source citations, localized periods, and incomplete saved purchase-order inputs. Expanding a decision with absent MOQ previously threw; it now shows the available recorded fields and an explicit incomplete-derivation state.

Cross-review additionally closed stale weekly schedules, leased pre-dispatch recovery, policy/opt-in revocation at dispatch, changed supplier decisions between preview and send, exact named Q&A periods, saved-forecast quantity projection, cancelled old-context downloads, and Indic/Latin PDF glyph collisions. Modified composite fonts have distinct family names, licenses and a reproducible build script.

A running-browser scenario check exposed a development StrictMode observer lifecycle defect in the pre-existing initial auto-run. The StrictMode regression reproduced a returned result with a permanently disabled action; the initial dispatch now waits for the committed effect and cancels probe cleanup.

## Browser and artifact evidence

An isolated PostgreSQL/Redis fixture with a scoped application role, synthetic owner/data and mocked provider was used on frontend 5181/API 50409. No customer workspace was enabled for QA. SMTP was disabled in the browser fixture.

- Q&A returned the actual synthetic 500 available units, source links and the explicit unknown-unrecorded-stock disclosure.
- Scenario interpretation proposed demand +20% and lead time +14 days from the exact two-week source text; applying proposals clears an unrelated preset outage. After the StrictMode fix, the browser explicitly ran these reviewed assumptions and received the actual engine result (final stock 356 versus baseline 380 units).
- The actual settings dropdown used the themed picker. Saved Hindi, Telugu and Tamil preferences each produced native-script fact labels/units with the same 500-unit evidence; scripts and source links were visually checked. Tamil wrapping was also inspected at a measured 375-pixel viewport. Switching language cleared the previous chat.
- Latest Hindi, Telugu and Tamil PDF page PNGs were inspected: readable shaped text, P90 and INR tokens, punctuation and Latin source URLs. Financial figures remain separated into opportunities, approval estimates and observed outcomes; unavailable realized savings are not invented.
- The actual accepted-order UI produced an editable 60-unit supplier draft, blank recipient field and unchecked send confirmation. The ROI preview kept tiers separate; its PDF downloaded through the browser. The downloaded two-page artifact retained the actual 1,600.00 approval estimate and unavailable-realized-savings disclosure.
- Separate real loopback STARTTLS sink tests exercised weekly dispatch, reviewed ROI PDF attachment and the accepted supplier quantity. No external recipient was used.

Screenshots are in this directory and `../2026-10-27-dropdown-controls/`. Detailed PDF/supplier evidence is in `../2026-10-27-ai-phase-3/reports/`.

## Local activation

The supplied provider key was copied to ignored `backend/.env`, never to frontend code; its source text file is also ignored. DeepSeek GET /models authenticated with HTTP 200 and included the configured model. This is credential/model-availability verification, not live generation-quality evaluation.

A custom-format local database backup was created and its archive list validated before additive migrations 0034/0035. The application database is at 0035 and strict RLS startup validation passed. The normal local stack was restarted; frontend 5173, API 8010 and ML 8001 each returned HTTP 200. New routes were confirmed in the actual API schema.

## Operational limits

Email requires operator SMTP configuration. Weekly AI requires the workspace task/aggregate permissions and per-user opt-in. Existing workspaces were not silently opted in. Persistent ARQ survives worker restart; complete Redis data loss requires authenticated member-scoped recovery. SMTP acceptance ambiguity is held for review, not automatically resent. Model acceptance uses mocked provider fixtures; no real-data or live-generation quality claim is made. No hosted deployment, push, PR or merge is claimed.

## Combined verification

The earlier combined backend run passed 1061 tests but hit an existing Hypothesis input-generation speed health check in allocation; the isolated allocation suite passed all nine tests. The failure was an input-generation timing threshold, not an allocation invariant failure, and no production allocation code or test threshold was weakened.


Final frozen-source verification (all exit 0):

| Check | Actual result |
| --- | --- |
| `frontend: npm run typecheck` | Passed |
| `frontend: npm run lint` | Passed; zero errors/warnings |
| `frontend: npm test` | 66 files, 322 tests passed; 95.28 seconds |
| `frontend: npm run build` | Passed; Vite build 17.05 seconds; existing >500 kB chunk warnings |
| `frontend: npx playwright test e2e/dropdown-theme.spec.ts --workers=1` | 2 passed, 6.6 seconds; light/dark pickers, arrow spacing, keyboard selection, disabled cursor and 375px layout |
| `backend: uv run pytest` with provider key disabled for tests | 1065 passed, 263.03 seconds; 4 warnings |
| Localized labels/periods/citations and supplier approval labels | 11 focused localization cases passed |
| Actual browser PDF extraction | 2 pages; actual 1,600.00 approval estimate and unavailable realized-savings disclosure preserved |
| Built credential scan | Actual provider key absent from all 82 generated JavaScript files |
| Diff integrity | `git diff --check` passed |

The final backend warnings were Argon2 version lookup deprecation, two `datetime.utcnow` deprecations, and an SQLAlchemy connection garbage-collection warning in an existing health test. No tests were skipped, no health-check threshold was relaxed, and no allocation production code was changed. Detailed local logs: `tmp/ai-phases34-verified-frontend.log` and `tmp/ai-phases34-verified-backend.log`.

After browser QA, the isolated API/Vite fixtures were stopped and their containers cleaned up; normal application services were preserved. A final normal-stack restart loads the last locale catalog change. SMTP remains unconfigured; no external email was sent.
