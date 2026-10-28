# Local demo readiness — 26 October 2026

Scope approved by the user: the product opens directly at sign-in; existing sessions
open the dashboard; sign-out returns to sign-in; customer access is provisioned or
invited. Deployment/domain work is deferred. The immediate target is a local demo
on 27 October, followed by real client data import and forecasting.

## Changes

- Removed the marketing entry route and all password/Google signup UI.
- Public password signup and Google workspace creation default to disabled.
  Anonymous sandbox access also defaults to disabled; unknown Google identities
  cannot automatically join the development workspace. Invitations remain tested.
- Added a supervised uv launcher. It starts PostgreSQL AND Redis, checks Docker,
  occupied ports, migration version and application-role RLS, uses the installed ML
  virtual environment, aligns API/ML database and service credentials, fixes the
  frontend API prefix/proxy, preloads Chronos and opens the local sign-in page.
- API defaults to 8010 because 8000 belongs to a separate Sanket Marketing Agent.
  That other process was left untouched. All app services bind loopback.
- Migration-version inspection now reports failure when the version cannot be read.
- Dashboard decision explanations now use recorded reasons; hard-coded weather,
  festival and promotion impacts were removed. Failed ML no longer becomes a
  fabricated decision-derived curve.
- Successful uploads invalidate derived queries, including cached dashboard
  forecasts and sales history, before returning to the workspace.

## Root causes reproduced

Docker Desktop was stopped. PostgreSQL/Redis/ML/frontend were absent on their
normal ports. The old launcher did not start Redis, used ambient Python and
unchecked terminal windows, and pointed the frontend at occupied port 8000.
The local database was bootstrapped by raw SQL without an Alembic version and
lacked current tenant-industry fields/RLS hardening. The previous migration
inspection swallowed the missing version and returned True.

## Database preservation and recovery

The original `sanket` database was retained. A custom-format pg_dump was saved at
`tmp/startup-recovery/before.dump` and restored into `sanket_recovered_20261026`.
Recovery was tested on that clone, not over the original database.

The verified raw-SQL baseline was stamped 0001, migrations 0002–0006 were applied,
and the already-existing inventory table was inspected against 0007 (columns,
constraints, indexes, trigger and RLS policy). Only after that inspection was 0007
stamped; migrations 0008–0024 then applied successfully. This is a one-off recovery
of this specific unversioned local schema, not a general migration recipe.

Both original and recovered copies had 5,280 sales rows, 101,694 units and gross
revenue 12,364,240.5000 before adding new demo data. The recovered application's
role is neither SUPERUSER nor BYPASSRLS; tenants has FORCE ROW LEVEL SECURITY.
Only the ignored local backend/.env DATABASE_URL was switched to the clone.
No production database, cloud deployment or payment provider was changed.

## Real sample journey

See api-evidence.json and data/demo-swecha/manifest.json.

- Isolated fashion test workspace: `swecha-demo`, labelled SYNTHETIC Swecha Demo.
- 12 extended-size clothing SKUs and 24 stock positions across two stores.
- Three samples: steady, seasonal and intermittent demand; 104 training weeks.
- Imported 2,496 training rows, zero rejected rows. Replaying 832 rows inserted
  zero and reported them unchanged. Imported 192 held-out rows separately.
- Real Chronos zero-shot generated 12 series / 144 predictions in 7.76 seconds
  on the initial training-only request. The final forward run starts 26 Oct 2026.
- Eight-week backtest at 31 Aug 2026 excludes sales at/after the cutoff from
  context. Independent evaluation matched all 96 SKU/week predictions to actuals.
- Deliberately invalid dates/negative quantity were rejected with explicit errors.
- Health, deep health, quality, decisions, confidence, sales timeseries,
  integrations, onboarding and inventory endpoints returned HTTP 200.
- Live password/Google signup returned 403 and anonymous sandbox returned 404.
- Local sign-in/logout passed. RLS sees 2,688 own-tenant sales, zero foreign sales,
  and zero sales without tenant context.

| Synthetic cohort | Points | Chronos WAPE | Repeat-last WAPE | Four-week mean WAPE |
| --- | ---: | ---: | ---: | ---: |
| All | 96 | 18.03% | 26.77% | 26.06% |
| Steady | 32 | 7.89% | 15.38% | 7.15% |
| Seasonal | 32 | 20.84% | 27.54% | 42.03% |
| Intermittent | 32 | 97.53% | 128.89% | 116.67% |

The intermittent result is poor and the simple four-week mean wins on steady
sales. No learned routing or new artifact was promoted. Uploaded history is used
by the existing pretrained Chronos model; no customer-specific training claim is
made. Synthetic workflow tests are not Swecha sales accuracy or purchasing advice.

## Website and browser limitation

Chrome navigation timed out, then native Chrome control stopped because it could
not establish the current URL reliably enough to enforce browser policy. No further
browser automation was attempted. Indexed public pages informed the sample's
categories, extended sizing and store names:

- https://swechafashions.com/
- https://swechafashions.com/product/straight-cut-kurthi/
- https://swechafashions.com/best-womens-ethnic-wear-in-uppal-hyderabad-telangana/

React route/component tests and live API tests passed; a live browser click-through
was not verified in this session. Automatic browser-open behavior is unit-tested;
the coordinator service startup itself was executed successfully with real services.

## Running tomorrow

Use data/demo-swecha/README.md for credentials, exact import order and client data
requirements. Start Docker Desktop, then double-click Start_SANKET.bat. Leave its
console open and stop with Ctrl+C. The local app is http://127.0.0.1:5173;
API http://127.0.0.1:8010; ML http://127.0.0.1:8001.

All included samples are synthetic. Use a separate workspace for actual client
sales. Production hosting/auth/secrets and real customer accuracy remain separate
work. Existing local development-secret warnings were not hidden or weakened.

## Review

Manual diff review covered private-route guards, retained invitation/reset flows,
service environment consistency, no process takeover on occupied ports, preserved
original data, derived-query invalidation, and removal of unsupported signals.
No independent reviewer was invoked. Full command outputs are retained beside
this report after final checks complete.
## Final verification

| Check | Actual result |
| --- | --- |
| Frontend `npm run typecheck` | Passed |
| Frontend `npm run lint` | 0 errors, 28 existing warnings |
| Frontend `npm test` | 151 passed, 36 files |
| Backend `uv run pytest --tb=short` | 527 passed, 111 warnings, 358.73 s |
| Final focused private-access/startup tests | 10 passed, 3 warnings |
| ML `.venv/Scripts/python.exe -m pytest -q` | 56 passed, 2 warnings, 25.15 s |
| New Python launcher/tests focused Ruff check | All checks passed |
| `git diff --check` | Passed |
| Changed tracked source UTF-8 validation | Passed |

Warnings were not suppressed. They include existing dependency deprecations,
React Router future notices, an existing backend unawaited AsyncMock warning,
and existing frontend lint warnings. Production build result is recorded in
frontend-build.log; the existing large-chunk warning remains.

The frontend typecheck/lint/test/build sequence was rerun after the final import
cache fix. The direct-entry regression renders the real App router and verifies
that opening / reaches /login. No deployment, push, payment, real external
integration sync or customer communication was performed.

Final production bundle: `npm run build` passed in 43.75 seconds, with the existing
large-chunk warning. Final launcher restart used `--no-open-browser` because
computer/browser control had stopped; the default auto-open function is unit-tested.
A separate empty `swecha-client` workspace is provisioned for the client's dataset;
its local credentials are in data/demo-swecha/README.md. It contains no sample sales.
