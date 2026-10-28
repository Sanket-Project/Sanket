# ML execution portion of approved forecast refresh design

Execute with strict RED/GREEN/REFACTOR, preserving the existing sample-path batching fix.

1. Add API regression tests for concurrent calls across endpoints and for persistence failure (3–5 minutes). Verify current failures before implementation.
2. Add guard tests for PostgreSQL autocommit session advisory locks, cleanup and distinct tenant keys (3–5 minutes). Verify failures, implement guard, rerun.
3. Move compute and persistence into one guarded synchronous threadpool invocation (3–5 minutes). Verify concurrent requests are rejected while unrelated tenants proceed; cancelling the HTTP task must not release the compute lock.
4. Add refresh UUID replay tests and persisted-result recovery (3–5 minutes). Verify a retry returns the saved result without invoking the model.
5. Run ML tests and review diff for RLS, lock cleanup and existing batching changes (3–5 minutes).
