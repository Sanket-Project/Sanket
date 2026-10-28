# Fashion Retail V2 Implementation Plan (P0 Baseline)

Approved baseline: `docs/audit/2026-10-28-retail-v2/` and `docs/strategy/2026-10-28-fashion-retail-v2-roadmap.md`.
Following AGENTS.md §3 manual workflow (Superpowers not installed in environment).
Strict RED → GREEN → REFACTOR discipline for every task.
Preserves all existing untracked workspace files, V1 backward-compatibility, and RLS tenant isolation.

---

## Architecture and Core Design Decisions

1. **V1 Backward Compatibility**: Existing V1 routes (`/integrations/upload`, `/upload/analyze`, `/import/plan`, etc.) remain fully functional for legacy files. Contract tests freeze V1 behavior (e.g., negative sales rejection, legacy combined returns field, name slugification, available stock clamping).
2. **V2 Canonical Contracts**: 8 typed CSV schemas with explicit version markers (`retail_v2.0.*`). V2 enforces strict data integrity:
   - `retail_v2.0.products`: Style master with required `product_code`, `product_name`, `category_code`. No quantities or forecast scalars.
   - `retail_v2.0.skus`: Sellable variant with required `sku_code`, `product_code` (existing valid parent required; no orphans), `currency` (INR required in samples; no silent USD default). Unique variant option signatures.
   - `retail_v2.0.inventory`: Snapshot contract with `as_of` timestamp required, non-negative disjoint buckets (`on_hand_qty >= reserved_qty + damaged_qty + quarantine_qty`), explicit source authority. No silent clamping.
   - `retail_v2.0.sales`: Completed sales with `quantity_sold > 0`, cancelled with `quantity_sold = 0` and zero financial values. Strict `returns = 0`. Ex-tax unit price, line discount, tax computation.
   - `retail_v2.0.returns`: Single return owner with `returns > 0`, linked to original transaction `(original_source_system, original_transaction_id, original_order_line_id)`. Cumulative return <= recognized sold units. Concurrent return locking.
   - `retail_v2.0.purchases`: Document-type-aware (`purchase_order`, `goods_receipt`, `supplier_invoice`, `purchase_return`). PO commitment does not add physical stock; goods receipt adds stock once; invoice changes payables only.
   - `retail_v2.0.suppliers`: Master for procurement counterparties.
   - `retail_v2.0.locations`: Store/warehouse master with timezone and fulfillment flags.
3. **Event Identity Registry & Deduplication**: Central `event_identity_registry` table scoped by `(tenant_id, source_system, entity_kind, external_event_id, event_line_id)` with payload hash. Exact replay is idempotent; conflicting payload blocks (`EVENT_PAYLOAD_CONFLICT`).
4. **Financial Arithmetic**: Decimal half-up in paise, deterministic largest-remainder line discount allocation, ex-tax base, explicit tax rates. Credits reduce revenue once; refunds change settlement, not revenue again.
5. **Historical Costing**: Historical issue cost from receipt valuation; returns reverse original issue COGS. Missing cost history marks GP as qualified/unavailable, never fabricated zero-cost.

---

## Detailed Task Breakdown (2–5 Minute Tasks)

### Increment 1: Freeze V1 Behavior with Contract Tests (P0-01)
- [ ] **Task 1.1**: Create `backend/tests/test_v1_import_contracts.py` with failing tests capturing frozen V1 invariants:
  - V1 sales mapper: allows legacy combined `returns` field (non-negative), rejects `quantity < 0` and `returns < 0`, derives gross/net revenue, allows name fallback slugification.
  - V1 inventory mapper: maps `available_stock` / `current_stock` into `on_hand_units`, defaults `location="default"`, silently clamps negative on_hand to 0.
  - V1 products mapper: allows `sku` or `name` without category (defaults to "Uncategorized").
  - V1 replay protection: verifies `sales_identity.py` transaction/period keys.
  - *Verification command*: `uv run pytest tests/test_v1_import_contracts.py` (RED -> observe behavior).
- [ ] **Task 1.2**: Ensure all V1 contract tests pass and establish the frozen reference baseline.
  - *Verification command*: `uv run pytest tests/test_v1_import_contracts.py` (GREEN).

### Increment 2: V2 Contract Schemas & Strict Validation Engine (P0-01, P0-02, P0-03, P0-04, P0-05)
- [ ] **Task 2.1**: Implement `backend/app/services/integrations/v2/contracts.py`:
  - Define schema version constants and column specifications for the 8 V2 contracts.
  - Implement `detect_v2_schema(headers, sample_row=None)` function.
  - Implement CSV parser with RFC-style quoting, UTF-8 BOM tolerance, and formula injection escaping on export.
  - *Verification command*: `uv run pytest tests/test_v2_contracts.py` (unit test pure schema detection).
- [ ] **Task 2.2**: Implement V2 Product & SKU validation (`backend/app/services/integrations/v2/catalog.py`):
  - Product validation: `product_code` required, `category_code` required, `status` enum, rejection of stock/forecast scalars on master.
  - SKU validation: `sku_code` required, `product_code` required, valid parent lookup, option signature validation `(color_code, size_code, size_system)`, currency validation.
  - Cross-tenant reference prevention.
  - *Verification command*: `uv run pytest tests/test_v2_catalog_validation.py`.
- [ ] **Task 2.3**: Implement V2 Inventory Semantics & Snapshot Validation (`backend/app/services/integrations/v2/inventory.py`):
  - Snapshot contract validation: `snapshot_id`, `as_of` timestamp required with timezone offset.
  - Non-negative disjoint bucket check: `on_hand_qty >= reserved_qty + damaged_qty + quarantine_qty`.
  - Rejection of negative stock (no silent clamping!).
  - Rejection of available-only stock mapping as physical on-hand without explicit conversion.
  - Stale snapshot detection: older snapshot cannot overwrite newer balances.
  - *Verification command*: `uv run pytest tests/test_v2_inventory_semantics.py`.
- [ ] **Task 2.4**: Implement V2 Sales & Returns Canonical Engine (`backend/app/services/integrations/v2/sales_returns.py`):
  - Sales validation: `quantity_sold >= 0`, completed `quantity_sold > 0`, cancelled `quantity_sold = 0` and zero financial values.
  - Strict rule: `returns == 0` on V2 sales rows.
  - Returns validation: `returns > 0`, original sale transaction link required `(original_source_system, original_transaction_id, original_order_line_id)`.
  - Decimal financial calculations: gross, line discount, taxable value, tax components, paise allocation.
  - Single return owner enforcement: cannot count same return through V1 and V2.
  - *Verification command*: `uv run pytest tests/test_v2_sales_returns_contracts.py`.

### Increment 3: Database Migration, Event Identity Registry, and Posting Groups (P0-06)
- [ ] **Task 3.1**: Create Alembic migration `0036_retail_v2_foundation.py`:
  - Table `event_identity_registry`: `(tenant_id, source_system, entity_kind, external_event_id, event_line_id)` UNIQUE, `payload_hash`, `target_id`, `status`.
  - Table `stock_authorities`: `(tenant_id, location_code, source_system)` authority mode, effective_from/to.
  - Table `v2_sales_events`: recognized sale lines with tenant, order, line, quantities, and financial fields.
  - Table `v2_return_events`: linked return lines with original sale event FK, disposition, credit, refund fields.
  - Table `v2_inventory_snapshots`: external snapshot audit and position header/lines.
  - FORCE RLS on all new tables with tenant isolation policies. Grant permissions to `sanket_app`.
  - *Verification command*: Test migration upgrade and downgrade in test database.
- [ ] **Task 3.2**: Implement `EventRegistryService` (`backend/app/services/integrations/v2/event_registry.py`):
  - Idempotent deduplication: exact same payload returns existing event outcome without writing new facts.
  - Conflicting payload under same key raises `EVENT_PAYLOAD_CONFLICT`.
  - Atomic posting groups: all lines of an order / return commit or abort together.
  - Safe post-commit retry handling (crash-before-ACK).
  - Cumulative return tracking: check `sum(approved_returns) <= sold_qty` for the linked original order line. Concurrent return locking via `with_for_update()`.
  - *Verification command*: `uv run pytest tests/test_v2_event_registry.py`.

### Increment 4: Historical Costing & Qualified Profitability (P0-07)
- [ ] **Task 4.1**: Implement Historical Valuation & Profitability Engine (`backend/app/services/integrations/v2/valuation.py`):
  - Historical issue cost tracking; never fall back to current catalog cost for historical sales.
  - Return reverses original issue COGS (if restocked) or records loss (if damaged).
  - Missing cost history qualifies gross profit as unavailable/qualified rather than zero-cost.
  - Summed gross profit divided by summed ex-tax revenue for gross margin %; separate markup formula. Negative gross profit preserved.
  - *Verification command*: `uv run pytest tests/test_v2_valuation_profitability.py`.

### Increment 5: End-to-End Ingestion, V2 Sample Verification, and System Health
- [ ] **Task 5.1**: Integrate V2 parser and validator into the smart import and file upload routers:
  - Support automatic routing for V2 files when `schema_version` matches `retail_v2.0.*`.
  - Return clear, actionable diagnostics on invalid rows, schema mismatches, and conflicts.
  - *Verification command*: `uv run pytest tests/test_v2_import_pipeline.py`.
- [ ] **Task 5.2**: Reconcile sample files from `docs/audit/2026-10-28-retail-v2/samples/`:
  - Run full verification against `products_v2_SAMPLE_ONLY.csv`, `skus_v2_SAMPLE_ONLY.csv`, `inventory_v2_SAMPLE_ONLY.csv`, `sales_v2_SAMPLE_ONLY.csv`, `returns_v2_SAMPLE_ONLY.csv`.
  - Verify exact kurti sample math: sell 2 kurtis @ INR 1,800 ex-tax (after INR 200 discount) + INR 90 GST = INR 1,890. Return 1 kurti @ INR 900 + INR 45 GST = INR 945 refund. Retained revenue INR 900, COGS INR 600, GP INR 300, margin 33.3333%.
  - *Verification command*: `uv run pytest tests/test_v2_sample_reconciliation.py`.
- [ ] **Task 5.3**: Full repository verification:
  - Backend: `uv run pytest`
  - Frontend: `npm run typecheck && npm run lint && npm test`
  - Record diff, commands, and results in progress document.
