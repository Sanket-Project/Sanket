# Verification record

Review date: 28 October 2026. Application code unchanged by this review.

## Completed checks

| Command / scope | Actual result |
|---|---|
| frontend: npm run typecheck | Exit 0 |
| frontend: npm run lint | Exit 0 |
| frontend: npm test | Exit 0; 66 files, 324 tests passed in 212.93 seconds |
| Review probes, explicit command below | Exit 1; 14 failed in 35.55 seconds, exposing the missing required behaviors in REPORT.md |
| backend: uv run pytest | Exit 0; 1,116 passed, 4 warnings in 525.94 seconds; includes all 46 new V1/V2 tests |

Frontend emitted React Router future-flag warnings. Backend warnings covered argon2 version access, two datetime.utcnow deprecations and one SQLAlchemy connection-cleanup warning. The full backend suite is separate from the new review probes. A passing existing suite does not cancel failures in additional required scenarios.

## Reproduce the review findings

From C:\Users\admin\Desktop\Prisma\backend, PowerShell:

```powershell
$env:PYTHONPATH = "$PWD;$PWD\tests"
uv run pytest -p conftest ../docs/audit/2026-10-28-retail-v2-verification/test_review_repros.py -q --tb=short
```

The final run contains 14 probes: duplicate headers, extra cells, missing timezone, negative incoming quantities, duplicate default variants, incorrect sale tax, valid native numeric zero, returns-only profitability, mismatched return original terms, draft/rejected return effects, cross-tenant return FK, partial group effects, and concurrent identical registry events. Each failed against the reviewed code. Exact errors and summary are in probe-results.txt.

Database cases use backend/tests/conftest.py through `-p conftest`: a disposable PostgreSQL container, actual migrations, and a Database connected as sanket_app. They do not use a client database. Raw UUIDs and rows in failure output are synthetic test fixtures.

Three probe runs occurred as coverage expanded: 11 failures, then 13 failures after atomicity/concurrency cases, then 14 failures after the returns-only period case. probe-results.txt contains the final 14-case run. No fixes were attempted and no unchanged probe was rerun without expanded coverage.

## Boundaries

No browser/E2E test, production database query, production migration, downgrade rehearsal, deployment or application fix was performed. The new tests live under docs/audit and are not part of normal backend testpaths. Existing plan/progress documents were left untouched so their original claims remain reviewable.

reviewed_sources.json records SHA256 for the reviewed V2 modules, migration and upload router. REPORT.md separates reproducible failures from static missing-capability findings. Historical RED-before-GREEN discipline and preservation of every earlier unrelated file cannot be established from a pasted activity log alone; no such assurance is claimed here.
