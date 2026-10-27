# SANKET demo checkpoint

Date: 2026-10-27. Scope changed at the user's request to finish the working checkpoint for a demo and hand remaining work to Claude.

## Open the normal app

[Normal local app](http://127.0.0.1:5173) — use your existing workspace sign-in.

The normal stack is running from the current working tree:

- Frontend: loopback port 5173, process 6852 at startup.
- Backend: loopback port 8010, process 18616 at startup.
- ML: loopback port 8001, process 2464 at startup; Chronos CPU model loaded successfully.
- Forecast worker: started by the existing supervised launcher.
- Launcher process: 7708. Keep it running for the demo. Logs are in `tmp/dev-stack/` and `tmp/ai-demo-launcher.*.log`. Verify current ownership before stopping anything; process IDs can change.

The launcher checked current migrations and strict RLS before startup. Application connections remain `sanket_app`; no application superuser connection was introduced.

The configured development database is `sanket_recovered_20261026` on localhost. Before applying additive migrations 0031/0032, a custom-format backup was created and its archive directory validated: `tmp/backups/ai-demo-20261027-before-0031.dump` (1,381,244 bytes). The application database is now at `0032`. Existing application credentials and workspace flags were left unchanged. The backup is local and must not be committed or shared as a demo asset.

## What is ready

Phase 1 import review/remembered formats, onboarding help, confirmed data-quality repairs and product cleanup; Phase 2 decision/alert/anomaly explanations, planning summary and evidence-gated industry advice are implemented. AI remains optional and controlled by the workspace owner under Settings → Workspace → AI. Manual paths remain usable.

The configured backend has no DeepSeek key. Live generation is therefore unavailable until the operator configures `DEEPSEEK_API_KEY` in the backend environment and restarts it. Do not put a key in Vite/frontend configuration. Do not describe mocked responses as live AI.

For a clearly disclosed workflow demonstration, the separate [mocked-AI preview](http://127.0.0.1:5179/workspace/decisions) uses only a disposable synthetic workspace and mocked provider. API: port 50399; fixture launcher process 25144; API process 16496; Vite process 10404 at checkpoint. It is independent of the normal database. The synthetic sign-in is workspace `ai-foundation-smoke`, email `ai-foundation-smoke@example.com`, password `SmokeOnly2026!`; these are public test-only fixture credentials, not real account credentials. External workers and real ML are disabled there, so its forecast-unavailable state is expected. Do not use this preview for real data or represent it as provider evaluation.

A short mocked walkthrough: expand “Show working” on the synthetic decision → “Explain this decision” → inspect linked values and unchanged order → “Get industry advice” → open Alerts → generate summary and inspect missing coverage. Use the normal app for the real-data/ML demo.

## Checks

- Final backend: **902 passed, 3 warnings in 250.75s**, exit 0.
- Frontend before final polling fix: typecheck/lint passed; **291 tests passed**; production build passed.
- Final frontend after the polling fix: `npm run typecheck` and `npm run lint` exit 0; **59 files, 292 tests passed in 70.81s**; `npm run build` exit 0, Vite build **21.93s**. Existing bundle-size warnings remain.
- Local migrations: backup validated, additive upgrade to 0032 successful, startup migration/RLS checks passed.
- Normal app login page rendered in the in-app Browser. Backend health: **ok**; ML health: **ok**; frontend HTTP: **200**. These confirm startup, not a new real-data forecast accuracy evaluation.
- The mocked planning summary remained visible across subsequent polling after the regression fix; source values and the missing-forecast statement were rechecked in the running UI.

No live provider evaluation, production email, hosted deployment, push, PR or merge is claimed. GitHub rejected push with HTTP 403 for the connected account.

## Remaining work for Claude

Use [the complete Claude prompt](2026-10-27-claude-ai-handoff.md). It covers Phase 3 languages/weekly email/ROI PDF and email/supplier drafts, Phase 4 scenario interpretation/read-only Q&A, and remaining visual/live QA. The approved 111-task plan remains the detailed acceptance checklist. Preserve unrelated uncommitted work in this shared checkout.
