# Approved V2 blocker repairs

User approved 28 October 2026. Execute each task with RED → GREEN → REFACTOR.

1. V2 confirmation (2–5 minutes): add readable-file interaction coverage for
   confirmation, completion callback, errors and viewer blocking. Observe the
   confirmation regression fail, fix the active-mode guard and callback, rerun.
2. Return allocation (2–5 minutes): promote the authenticated over-credit probe;
   require the quantity-proportional discounted value and tax, reserving the
   remainder for the final return. Verify rejection, rollback, valid partials,
   zero-value sales and three-unit rounding.
3. Dated projections and identity (2–5 minutes per test/fix): promote the
   recognition-date and delimiter-collision probes. Project sale and return UUIDs
   separately, preserving gross units and credit-date net revenue. Verify retry,
   lifecycle, concurrent confirmations and period reporting under application RLS.
4. Existing data repair (2–5 minutes per test/fix): add a forward migration that
   rebuilds only V2 history from canonical events, restoring original values and
   missing collided projections. Verify populated upgrade, retry and V1 isolation
   in a disposable database; never rewrite already-applied migrations.
5. Review and completion: inspect the scoped diff, run frontend typecheck, lint,
   tests and backend pytest, and record actual results and deployment limits.

Use manual executing-plans with sequential tasks and separate review of each
task's behavior and diff. No deployment or client-database migration is requested.
