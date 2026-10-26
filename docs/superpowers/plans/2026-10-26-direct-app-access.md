# Direct app access and startup recovery

Approved: app opens at sign-in, authenticated users enter the workspace, sign-out
returns to sign-in. Accounts are provisioned by the operator or invitation;
no public signup. Marketing remains on the separate Sanket website.

Execute sequentially, using RED → GREEN → REFACTOR for each behavior.

1. (5 min) Add sign-in-only and root-route regression tests; observe failures.
   Remove signup UI and marketing entry route; retain recovery and invitation.
   Verify targeted Vitest and typecheck.
2. (5 min) Test default-disabled password/Google signup, sandbox and automatic
   provisioning. Gate those paths server-side; preserve explicitly enabled legacy
   tests and invited users. Verify auth and invitation tests.
3. (5 min) Reproduce launcher failures: unavailable Docker, missing Redis,
   occupied API port, runtime/env selection and ML authentication. Add startup
   regression checks, then fix the identified causes. Verify real service health.
4. (5 min) Provision a clearly labelled isolated local test account through the
   application role. Verify password sign-in, session and tenant isolation.
   Production Firebase provisioning requires the configured target environment.
5. (5 min) Run frontend typecheck/lint/tests, backend pytest, ML pytest and build.
   Review diff and document actual outputs and outstanding production gates.
6. (5 min) Inspect available datasets and training entry points. Establish data
   provenance and temporal holdout before training; do not promote synthetic
   evaluation results or unvalidated artifacts to production.

Initial evidence: Docker daemon stopped; port 8000 is a separate Marketing Agent;
launcher starts no Redis; ML unit suite 56 passed. Backend before Docker startup:
314 passed / 203 fixture errors (Docker unavailable). No source edits yet.
