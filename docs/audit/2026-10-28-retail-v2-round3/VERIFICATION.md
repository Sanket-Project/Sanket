# Round-three verification record

28 October 2026. Review-only tests, configuration and documentation were added. Application source and client data were not changed.

| Check | Actual result |
|---|---|
| Original 14 + previous 7 probes | 20 passed, 1 failed, 1 warning in 44.37 seconds. Failure is the obsolete empty-catalog analytics fixture; unknown references correctly return 400. |
| New seeded HTTP/read-model probes | 1 passed, 3 failed, 1 warning in 94.72 seconds. Actual output: projection-results.txt. |
| New V2 UI interaction probe | Failed: enabled Import button makes zero v2Confirm calls. Actual output: ui-results.txt. The invocation also included all 324 normal frontend tests, which passed. |
| frontend: npm run typecheck | Exit 0 |
| frontend: npm run lint | Exit 0 |
| frontend: npm test | 323 passed, 1 failed in Forecasts.test.tsx during overlapping frontend verification; 203.99 seconds. |
| Isolated Forecasts.test.tsx rerun | 12 passed in 13.95 seconds. This file also passed in the review-config invocation. The full-run timeout is recorded, not concealed as a clean run. |
| backend: uv run pytest | 1,117 passed, 1 failed, 4 warnings in 536.03 seconds. Failure is Hypothesis FailedHealthCheck for slow input generation in the allocation property test, not a failed allocation invariant. |
| Isolated allocation property rerun | 1 passed in 1.55 seconds. No code changes or suppressed health checks. |
| git diff --check for changed integration application files | Exit 0 |

The normal frontend run and initial review-config run overlapped because the review config merged the normal test include list. That review configuration was narrowed after the run, and only the timed-out normal Forecasts file was rerun. No product code was changed to make a test pass. The UI failure is deterministic component logic and is separate from that timing issue.

## Reproduction commands

From backend, PowerShell:

```powershell
$env:PYTHONPATH = "$PWD;$PWD\tests"
uv run pytest -p conftest ../docs/audit/2026-10-28-retail-v2-verification/test_review_repros.py ../docs/audit/2026-10-28-retail-v2-copilot-review/test_followup_repros.py -q --tb=short
uv run pytest -p conftest ../docs/audit/2026-10-28-retail-v2-round3/test_projection_repros.py -q --tb=short
```

From frontend:

```powershell
npx vitest run --config vitest.retail-review.config.ts review/V2Upload.review.test.tsx
```

Backend HTTP probes create real tenant product/SKU/location fixtures and verify behavior in a disposable migrated PostgreSQL database. The seeded positive projection/retry case passes. The three additional financial/identity cases fail. The UI interaction uses the production component with mocked network responses and a readable File prefix, then clicks Import. It is a component interaction test, not a live browser/E2E claim.

reviewed_sources.json records the reviewed application files. Existing prior review/progress records were not altered. No client database, deployment, production migration or authority cutover was involved.
