# Phase 2 working checkpoint

Date: 2026-10-27. The user requested a stable demo checkpoint and a Claude prompt for the remaining work. Phase 3/4 implementation is deferred to that handoff.

## Implemented

- Saved-decision explanation projects frozen quantities, confidence, stock cover, demand bands, lead time, economics, location identifiers and source time. Missing money is not replaced with zero. Expired/foreign decisions are rejected.
- Shortage alerts and existing anomaly detection expose recorded values and explicit coverage/cause gaps. A missing feed is not described as a measured demand drop; no unsupported cause is asserted.
- Planning summary uses the same displayed open queue (limit 20), current saved-run identity, source totals and data-quality report. A supplied mismatched run is rejected. It does not run forecasts.
- Operational advice requires supported recorded constraints for fashion, electronics, pharma, agrocenter or hardware. Industry membership alone does not justify expiry, harvest, markdown, launch, clinical or dosage claims.
- Optional UI controls exist in decision details, alerts, the anomaly log and the planning brief. Workspace/source changes clear old answers. The existing decision details control is now reachable at narrow widths. Repeated polling with identical source content retains a current summary.

The provider selects strict fact IDs and proposition types; the server renders displayed factual text, values, periods and local source links. Existing decision execution remains separate and requires its existing explicit actions. Workspace master/task/sharing permissions default off.

## TDD evidence

| Behavior | Observed RED | GREEN |
| --- | --- | --- |
| Decision, alert, industry and planning facts/routes | 14 failures: missing projection module, unsupported contexts, rejected task routes | 14 passed. |
| Current-run binding and anomaly source | 2 failures: unsupported run argument and source context | 16 explanation tests passed. |
| Additional recorded industry constraints | 4 failures: advice absent outside fashion | 20 explanation tests passed, including all five industry codes. |
| UI placement/settings | 3 failures: missing explanation blocks and task controls | Focused six-file batch: 36 passed. |
| Alert/anomaly UI | 2 failures: missing explanation controls | Included in the focused green batch; fixture selection and exact acknowledgment label corrected. |
| Source revision remount | Failed old-source clearing/forwarded-run assertion | Included in the green summary tests. |
| Correct dashboard source link and period | One frontend link failure and one backend missing-period failure | Summary/decision UI: 13 passed; evidence/facts backend: 28 passed. |
| Narrow decision access and distinct labels | Hidden-control assertion and absent-label assertion failed | Decision tests passed; browser keyboard flow verified. |
| Polling identical source content | Summary disappeared after batched query observer refresh | Final frontend: 292 tests passed; running summary remained visible after polling. |

## Verification

- Backend final `uv run pytest`: **902 passed, 3 warnings in 250.75s**, exit 0. This includes the final four industry predicate additions and the period regression. Earlier full runs passed 897 and 898 tests before those additions.
- Frontend full typecheck/lint: exit 0; full `npm test`: **59 files, 291 passed in 106.44s** before the final polling regression. The final frontend typecheck/lint/test/build rerun is recorded in the demo checkpoint after it completes.
- Focused dashboard tests after the initial source integration: **14 passed in 7.71s**. The final polling regression adds one test.
- Initial production `npm run build`: exit 0, Vite build 43.51s. Bundle-size warnings remain; no source maps are emitted. Final build is recorded in the demo checkpoint.
- Final frontend after polling fix: typecheck/lint exit 0; **59 files, 292 tests passed in 70.81s**; production build exit 0, **21.93s**. No pending verification job remains.
- `git diff --cached --check`: exit 0. Phase-owned staging excludes other agents' overlapping dashboard and forecast changes.
- All provider outputs in tests are mocked; no live-provider quality claim.

Known warnings: Argon2/passlib version deprecation, existing `datetime.utcnow` deprecations, React Router future flags, Vite large chunks. No warning was suppressed for this checkpoint.

## Running browser evidence

The separate disposable workspace used the application database role, strict tenant RLS, a mocked provider, and disabled external workers/ML inference.

- Decision “Show working” opened by keyboard. “Explain this decision” produced source-linked **60 recommended units**, **100 baseline units**, **72% confidence**, **4.5 days cover**, **14 days lead time**, **80 median demand**, **100 upper demand**, and **20 recorded stock**. The editable order remained 60 and was not accepted. [Screenshot](decision-evidence.png).
- Fashion advice referred to a recorded season and suggested reviewing the selling window; it did not claim a markdown or event.
- Alert output kept risk **0.7** and median demand **80**, explicitly marked absent stock coverage and other missing values, and distinguished a data gap from measured demand loss. Acknowledge/Resolve remained separate. [Screenshot](alert-data-gap.png).
- Planning summary reconciled **1 order**, **60 units**, **0 critical decisions**, **30000 INR modeled revenue**, and **5 data findings**; it explicitly reported the missing current forecast. The first capture revealed a poll-cleared summary; after the regression fix, a fresh capture verifies the summary remained visible across subsequent polling. [Final screenshot](planning-brief-evidence.png).
- The normal local app started with migration 0032 and strict RLS checks; backend/ML health returned `ok`, frontend returned HTTP 200. [Normal login page](normal-app-login.png). This is startup evidence; real account sign-in/business flows were not repeated on the normal database.

Narrow browser and keyboard evidence exists. Separate desktop viewport inspection, full degraded-provider UI matrix, comprehensive accessibility testing and live-provider evaluation remain limitations. The normal app's real ML service was started and its model loaded, but no new real forecast accuracy evaluation was performed.

## Scope and release

Phase 1 local commit: `e097f92` on `codex/ai-phase-1`. Phase 2 branch: `codex/ai-phase-2`; read Git history for its final checkpoint commit. GitHub push was denied (HTTP 403); no PR exists and nothing was merged. Do not imply hosted deployment.

Phase 3 (persisted languages, weekly email, ROI PDF/email, supplier drafts) and Phase 4 (natural-language scenarios, read-only Q&A) are not implemented. Reserved task names and API types do not change that status. See the Claude handoff and approved plan.
