# Claude handoff: finish SANKET AI phases 3 and 4

> Historical handoff: the remaining Phase 3/4 implementation has since been completed locally. See [final verification](../audit/2026-10-27-ai-phases34-final/REPORT.md) before starting any of the tasks below. Real email still requires operator SMTP configuration; no deployment or live-generation quality evaluation is claimed.

Copy the prompt below into Claude Code from `C:\Users\admin\Desktop\Prisma`.

---

Continue the approved SANKET AI build. The user approved all phases with “proceed with the build” and “proceed with the work”, then requested a stable demo checkpoint and this handoff for the remaining work. Do not redesign or restart the completed foundation. Finish the remaining scope end to end, preserving existing data and other agents' work.

Read `AGENTS.md` before any action. In Claude Code, invoke the real installed Superpowers skills required there. Follow the approved design and plan, strict test-driven development, systematic debugging, review, and verification. Existing design/build approval is already recorded; routine implementation does not need another approval request.

Read these authoritative project documents:

- `docs/superpowers/specs/2026-10-27-deepseek-ai-layer-design.md`
- `docs/superpowers/specs/2026-10-27-ai-phases-1-to-4-design.md`
- `docs/superpowers/plans/2026-10-27-ai-phases-1-to-4.md`
- `docs/audit/2026-10-27-ai-phase-1/REPORT.md`
- `docs/audit/2026-10-27-ai-phase-2/REPORT.md`
- `docs/strategy/2026-10-27-ai-demo-checkpoint.md`

## Starting point and completed functionality

The active local branch is `codex/ai-phase-2`, stacked on `codex/ai-phase-1` (`e097f92`). Phase 1 includes the previously uncommitted AI foundation and required migration-chain dependencies 0028/0029. Phase 2 is checkpointed separately; read `git log` for the exact commit. There is no GitHub PR: pushing was rejected with HTTP 403 for the signed-in account `baltejgoud` against `Sanket-Project/Sanket`. Do not silently change accounts, force-push, fork, or claim publication. Continue locally until authorized repository access is available.

Phase 0: task registry, strict contracts, DeepSeek adapter, opt-in workspace permissions, task flags, Redis cache/admission/breaker/deadlines, usage accounting, safe audit, application-role RLS, default-off operation.

Phase 1: bounded CSV/TSV/XLSX structural analysis; duplicate/blank physical headers; merged/multiline headers; date ambiguity review; one-table-at-a-time mocked/model mapping; human confirmation; transactional imports and workspace-confirmed formats; onboarding/catalog helper; source-grounded data-quality explanations and signed repair previews; editable product cleanup with explicit confirmation and duplicate hypotheses only. Remembered formats have admin disable/delete controls. Existing manual import still works with AI disabled.

Phase 2: read-only saved decision explanation; shortage-alert and detected-anomaly explanation; planning brief summary; evidence-gated operational advice for all five actual industry codes (`fashion`, `electronics`, `pharma`, `agrocenter`, `hardware`). Every displayed quantity is rendered from server-owned facts. The model chooses fact IDs and allowed propositions, not prose or numbers. Missing values remain missing. No model-generated cause is asserted. Advice requires a supported recorded attribute, not industry membership alone. The planning brief matches the dashboard's displayed open queue (limit 20) and checks a supplied saved-run ID. The UI clears summaries on source/workspace changes; decision evidence is reachable at narrow widths and by keyboard.

## Shared checkout: preserve unrelated work

The working tree already contains unrelated forecast persistence/worker performance, inventory/location filtering, trends, product schemas, tests, deleted audit/data artifacts, backups, and temporary files. Inspect status/diff before staging. Never `git add .`, reset, stash everything, or delete unknown files.

`backend/app/config.py` has unrelated forecast settings left unstaged. `PlanningBriefDashboard.tsx` and its test have other agents' changes: only the AI import/control/test were staged for Phase 2. The working tree intentionally contains more than the committed AI branch. `backend/app/services/integrations/file_import.py` has unrelated import scalability changes left unstaged. Preserve them. Required migration head is `0032`; recheck before adding a revision.

## Remaining Phase 3 — implement all of it

Follow plan IDs L01–L05, W01–W10, R01–R07, and M01–M06. Nothing in this phase was implemented merely because the registry reserves its task names or the frontend API type mentions them. Settings currently expose only completed Phase 1/2 tasks.

1. Persist per-user `en`, `hi`, `te`, `ta` preference with self-only updates, real RLS tests, and cache invalidation. The existing renderer translates only proposition prefixes; most fact labels and notes remain English. This does **not** count as complete multilingual support. Add reviewed templates with identical factual placeholders/citations. Verify actual Devanagari/Telugu/Tamil glyphs and wrapping in browser and PDF, including narrow and desktop layouts.
2. Replace the localStorage-only weekly notification toggle with server opt-in, IANA timezone, send hour, next-send state, Monday scheduling, and durable tenant/user/week delivery identity. Add TLS SMTP transport with secret config, header validation, no body logging, and synthetic local mail-sink acceptance/failure tests. Recheck current membership, opt-in, role, and AI policy before generation/send. Use scoped recurring jobs and a reviewed scope-preserving restart/bootstrap interface; never copy `session_no_rls` tenant enumeration from the existing WhatsApp worker. Model leases/crashes/retries/ambiguous SMTP acceptance honestly; do not claim exactly-once SMTP. No production-recipient QA sends.
3. Build ROI report from `services/roi.py`'s actual opportunity / estimated-at-approval / observed tiers. Preserve nulls, currencies, periods, evidence, assumptions, and non-additive labels. Add a downloadable `/export/roi.pdf`, no-cache headers, licensed Unicode fonts, off-event-loop bounded rendering, valid source links, snapshot/current-role validation, and a reviewed explicit-confirm email workflow. AI-off/unavailable must still allow a factual report. Do not fabricate realized savings from accepted decisions. Declare required dependencies rather than relying on an agent-only runtime. Render and inspect all four language PDFs; reconcile every displayed amount.
4. Build editable supplier email and WhatsApp **text drafts** only for accepted, unexpired `purchase_order` recommendations. Use accepted/current approved quantity, SKU, currency and current decision version; missing supplier contact stays missing and is not sent to the model. Preview/edit/review, then explicit email-send confirmation through the shared delivery service, with RBAC/idempotency/stale-version checks. Copying WhatsApp text is included; automatic WhatsApp sending is not. Send only synthetic confirmed test-sink messages during QA.

## Remaining Phase 4 — implement all of it

Follow plan IDs S01–S06 and Q01–Q13.

1. Interpret a bounded natural-language scenario into proposed assumptions only. Require matching source spans for every number/sign/unit/conversion; validate existing `ScenarioBody` limits, supported fields, scoped SKU IDs, contradictions, and unresolved duration. Interpretation must never run a simulation. Show an editable preview and require confirmation before invoking the existing deterministic simulation engine. Keep existing sliders/presets usable with AI off. Ground result explanation in returned engine facts; do not recalculate forecasts or invent effects.
2. Build read-only data Q&A through a strict finite API-tool plan: analytics, trends, scoped SKU lookup, inventory, saved forecasts. Reuse real API authorization/filter behavior and current user identity at each step. No SQL, arbitrary URL/endpoints, mutations, exports, sending messages, forecast refresh, or generation. Bound to three steps, one deadline and shared request/token allowances. Reject repeated plans and prompt injection. Preserve missing/stale/coverage states. Return fact-rendered answers with citations or an honest no-data answer. Raw questions/history must not enter Redis/audit; clear chat and discard in-flight results on logout/workspace switch. Add adversarial, viewer, demotion/inactive membership, two-tenant real-RLS, cancellation and actual local-API end-to-end tests.

## Demo and deployment facts

The normal local development database is `sanket_recovered_20261026` on loopback PostgreSQL. A verified custom-format backup was created at `tmp/backups/ai-demo-20261027-before-0031.dump` before additive migrations 0031/0032 were applied. Application credentials stayed unchanged. Do not restore or overwrite it casually. Keep backups, `.env`, prompts, private workbook rows and credentials out of Git.

The configured backend did not have `DEEPSEEK_API_KEY` at the checkpoint. All automated/provider browser evidence uses mocks; no live model-quality evaluation or production email was verified. Check actual runtime/config rather than inventing a key or claiming live generation. Workspace flags and sharing permissions remain opt-in. Do not enable real customer workspaces as QA.

The mocked preview is a disposable, separate workspace on port 5179, API port 50399, with ML/network workers disabled. It is clearly a test workflow, not production data or live-provider behavior. Its process IDs and normal app startup details are in the demo checkpoint document. Do not point the normal frontend at the mocked API. Before stopping a fixture, confirm its current owning process/port and use the authenticated `/_fixture/stop` helper; do not kill unrelated listeners. Testcontainers clean up their own resources.

## Verification and final delivery

For every task, observe the intended RED failure, implement minimally, and observe GREEN. Keep per-phase evidence under `docs/audit/`. Before claiming completion run frontend `npm run typecheck`, `npm run lint`, `npm test`, `npm run build`; backend `uv run pytest`; touched migrations/RLS/Redis concurrency checks; scenario/ML contracts when affected; browser flows with AI disabled, mocked success and degraded states; four-language PDF/UI inspection; staged secret and diff review. Report actual counts and limitations. Existing warning classes include passlib/Argon2 and `datetime.utcnow` deprecations, React Router future flags, and Vite bundle-size warnings.

Review remaining Phase 1/2 QA too: narrow browser and keyboard checks exist, but a separate desktop viewport, comprehensive accessibility review, full degraded-provider UI matrix, and optional live provider evaluation remain unverified. The renderer currently links only the first source in a multi-fact block; review whether all citations should be exposed. Evaluate missing event-specific industry evidence conservatively. Keep phase reports honest about these limits.

Use small phase-owned `codex/` commits and draft PRs when repository write access works, with dependency chain described; attach every created PR to the chat. Do not merge automatically. Complete all remaining features and update the delivery ledger; do not stop at endpoints or mock screenshots alone.

---
