# Task 24 — upload counters, period mode, accuracy sections

Completed on 26 October 2026. Commit: `db8528b`.

Continued the existing uncommitted accuracy implementation and tests. The previous commit already supplied the upload API options, period selector in Integrations, and shared replay summary. Completed onboarding period selection and honest replay toasts, separate production/backtest accuracy sections, exclusion explanations, and the Monday-cutoff backtest request. Added explicit accuracy-request failure handling and strict calendar-date validation.

Verification:

| Check | Exit | Result |
| --- | --- | --- |
| `npm run typecheck` | 0 | Passed |
| `npm run lint` | 0 | 0 errors, 28 warnings |
| `npm test` | 0 | 147 passed, 32 files |
| `npm run build` | 0 | Passed; bundle chunk-size warning |
| `uv run pytest` | 0 | 508 passed, 110 warnings, 413.66 seconds |
| `git diff --check` | 0 | Clean |

RED/GREEN: onboarding test first failed because period mode was absent; accuracy regression tests first failed because API errors appeared as empty readiness and an impossible date rolled forward. All now pass. Integrations interaction coverage verifies `identity=period` reaches the API and a replay displays `0 new · 459 already imported · 0 corrected`.

Reviewed API types against the backend accuracy response and backtest request; checked the diff for scope, tenant/auth changes, and replay wording. No backend production code changed. Browser E2E, rolling-origin evaluation, and the broader final audit remain tasks 25–27; they are not established by these unit and integration checks.

Full command logs are in this directory. Initial frontend logs retain the diagnosed unused import and missing Card children errors; the final logs supersede them.
