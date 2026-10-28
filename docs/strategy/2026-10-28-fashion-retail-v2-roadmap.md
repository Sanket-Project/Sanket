# Fashion retail V2 strategy and delivery gate

28 October 2026. Status: proposed design; application implementation has not started under this audit.

The completed review package is in [the audit directory](../audit/2026-10-28-retail-v2/README.md). The detailed [prioritized roadmap](../audit/2026-10-28-retail-v2/ANALYTICS_AND_ROADMAP.md) specifies P0/P1/P2 improvements, rationale, complexity, legacy-data impact, dependencies, acceptance criteria, KPI prerequisites and suggested sequencing.

The recommended sequence is:

1. P0: freeze V1 contracts, establish stable tenant/product/SKU identity, explicit stock semantics/authority, safe return ownership, financial basis, event idempotency and qualified historical costing. Operational ledger posting follows a reconciled opening baseline and source-authority cutover.
2. P1: category-governed fashion attributes, multi-location references and pricing, procurement lifecycle, hardened reusable mapping profiles, a backward-compatible pilot and qualified analytics.
3. P2: backtested demand forecasting, explainable replenishment and source-system integrations. More extensive WMS, accounting and ownership modules follow demonstrated business needs.

Design approval must resolve the concrete choices in [ARCHITECTURE.md](../audit/2026-10-28-retail-v2/ARCHITECTURE.md): source authority, sale recognition, cost method, missing-history treatment, original-return exceptions and tax configuration ownership. After approval, enter the repository writing-plans workflow and break the first increment into test-first 2–5 minute tasks with stated verification. The review package and acceptance scenarios provide the input to that plan; the roadmap is not a completed implementation.
