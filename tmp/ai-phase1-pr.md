Add workspace-controlled AI assistance for import mapping, onboarding, data-quality review, and product cleanup. Users review source evidence and explicitly confirm changes; disabled or unavailable AI leaves manual workflows usable. Remembered import formats are scoped to the workspace and preserve physical spreadsheet columns and date choices.

This checkpoint includes the previously uncommitted AI foundation and required migration-chain dependencies 0028/0029. It excludes the shared checkout's unrelated forecast and inventory source changes. All AI flags default off; application access remains subject to PostgreSQL RLS.

Validation: frontend typecheck/lint passed; 58 frontend files / 284 tests passed. Backend: 881 passed, 3 warnings in 253.18s. Disposable application-role RLS, repair-role permissions, audit rollback, exact Redwine workbook reconciliation, and mocked-provider browser import/reuse checks passed. See docs/audit/2026-10-27-ai-phase-1/REPORT.md.

Limitations: no live provider quality evaluation or production enablement; browser screenshots cover the narrow pane, with separate desktop/complete keyboard visual QA still outstanding. Phases 2–4 are subsequent changes. Do not merge automatically.
