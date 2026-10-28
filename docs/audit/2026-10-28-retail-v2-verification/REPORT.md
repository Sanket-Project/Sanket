# Independent verification of the claimed V2 P0 baseline

28 October 2026. Verdict: **partial backend foundations exist; P0 completion and production readiness are not verified and should not be claimed.** Application source was reviewed without modification. Review-only regression probes and their output are saved alongside this report.

The attached execution summary accurately names newly created files and several narrow behaviors. It overstates end-to-end integration, catalog referential integrity, inventory authority, financial reconciliation, atomic posting and historical costing. Existing tests can pass while the missing cases below remain defective.

## Findings, ordered by impact

### 1. [P1] Enforce tenant scope in the return-to-sale foreign key

Location: backend/alembic/versions/0036_retail_v2_foundation.py:104.

The FK is `sale_event_id REFERENCES v2_sales_events(id)` without tenant_id. RLS checks the tenant of the inserted return row, but does not make this relationship tenant-safe. In a disposable migrated database, using the non-superuser application-role fixture, tenant B successfully inserted a return whose sale_event_id belongs to tenant A. The probe deliberately supplies the known sale UUID; it does not demonstrate reading tenant A's sale or a public endpoint exploit. It demonstrates the missing database integrity boundary required by the design.

Required correction: a unique referenced `(tenant_id,id)` key and composite FK, with explicit cross-tenant regression coverage. Add equivalent protections to catalog/location references introduced by V2. Do not claim FORCE RLS alone proves relational tenant isolation.

Probe: `test_cross_tenant_return_fk_is_rejected`.

### 2. [P1] Do not post draft or rejected returns

Location: backend/app/services/integrations/v2/event_registry.py:196–309.

The validator allows approved/draft/rejected. post_return_event ignores that lifecycle when registering identity, updating cumulative_returned_qty and inserting the return; its result reports status approved regardless of input. Reproductions show both a draft and a rejected return consume one sold unit. This can exhaust the returnable balance without a valid approved return and makes a subsequent approval conflict with the original hashed draft payload.

Required correction: gate financial/stock/return-cap effects on the approved transition and define draft/rejection storage and later approval identities explicitly.

Probes: `test_return_posting_enforces_original_and_status[draft]` and `[rejected]`.

### 3. [P1] Validate the return against original merchandise, currency and credit limits

Location: backend/app/services/integrations/v2/event_registry.py:210–245.

The locked original query selects only id, quantity_sold and cumulative_returned_qty. It never compares SKU, currency, tax classification, original price/discount/tax allocations or event dates. A one-unit return referencing the sample sale was accepted with SKU NOT-THE-SOLD-SKU, USD currency, ex-tax credit 999999 and tax 9999. Its quantity remains within two sold units, so the only cap succeeds.

Required correction: load the original immutable terms and validate item/currency/date and remaining credit/tax allocations while holding the lock. Physical return location may legitimately differ from selling location and should not be forced equal. Validate refunds separately against approved credit and captured settlement balances.

Probe: `test_return_posting_enforces_original_and_status[wrong_sku_currency_value]`.

### 4. [P1] Make concurrent duplicate registration return the existing outcome

Location: backend/app/services/integrations/v2/event_registry.py:69–113.

Registration performs SELECT then INSERT. Two transactions can both see no identity. The second blocks on the unique constraint until the first commits, then raises IntegrityError/UniqueViolationError instead of returning an idempotent duplicate. The constraint prevents two committed copies, but the advertised concurrent retry behavior is not implemented. The reproduction coordinates two real application-role transactions at INSERT, not a sequential replay.

Required correction: implement a concurrency-safe insert/conflict/read protocol, compare canonical payload on conflict and return the committed identity/result. Preserve same-key/different-payload conflicts. Test overlapping concurrent uploads and commit-before-ACK retries.

Probe: `test_concurrent_identical_registry_events_are_idempotent`.

### 5. [P1] Provide a real atomic boundary for a posting group

Location: backend/app/services/integrations/v2/event_registry.py:115–188.

post_sales_group does not create a transaction/savepoint boundary. Given a valid sale followed by the same identity with conflicting payload, the first sale remains in the caller's transaction after the raised ValidationError. A partial-import caller that catches that business error and continues can commit half a failed group. The existing Database.session wrapper rolls back if the exception escapes; it does not protect callers that catch errors to continue other groups. Therefore atomicity is conditional on caller behavior, not guaranteed by this service.

Return registration also precedes original-link and quantity validation, so a caught validation error can leave a registered identity without its return fact. A later retry can be incorrectly skipped if that outer transaction is committed.

Required correction: an explicit caller posting-group transaction contract, enforced through transaction/savepoint ownership, plus a test that a failed group leaves no partial facts or committed identity while another valid group may proceed.

Probe: `test_failed_posting_group_leaves_no_partial_sale`.

### 6. [P1] Reconcile tax and other monetary values instead of trusting them

Location: backend/app/services/integrations/v2/sales_returns.py:187–211.

The sale validator calculates gross/net, but merely checks that supplied tax is nonnegative. Replacing the sample's INR 90 tax with INR 999999 is accepted, although the same row declares INR 1800 taxable value at 5%. customer_charge then includes the invalid tax. Tax rate/classification effective-date validation, jurisdiction components, cancellation tax-zero checks, payment/refund caps and allocation rules are not implemented by the presented code.

Required correction: validate original source/canonical financial basis and reconcile line amounts under approved tax/rounding policy. Separate validation of the supplied illustrative rate from claiming its statutory applicability. Do not enable fiscal posting with unverified tax configuration.

Probe: `test_sale_tax_mismatch_is_rejected`.

### 7. [P1] Stop CSV parsing from silently losing cells

Location: backend/app/services/integrations/v2/contracts.py:235–251.

Duplicate headers are turned into dictionary keys and overwrite earlier cells. Rows with more cells than headers are truncated; short rows are silently padded. For example, `sku_code,sku_code / FIRST,SECOND` retains only SECOND, and `sku_code / SKU-1,LOST-CELL` silently discards the second cell. This is incompatible with strict row-level validation and an auditable importer.

Schema detection also trusts a supported marker from a single sample row without validating every row's marker or header/entity compatibility. The test named test_v2_template_headers_match_data_dictionary only checks the first header and a minimum column count; it does not actually compare the dictionary or requiredness/type rules.

Required correction: detect raw/normalized duplicate headers, reject bad row widths, validate all schema markers, and test the actual dictionary contract. Preserve source locators and raw values for actionable errors.

Probes: `test_duplicate_csv_headers_are_rejected`, `test_extra_csv_cells_are_rejected`.

### 8. [P1] Enforce timezone and all inventory quantity constraints

Locations: backend/app/services/integrations/v2/inventory.py:73,103–104.

datetime.fromisoformat accepts a timezone-free timestamp and the validator never rejects it, contrary to the claimed mandatory offset behavior. It also parses in_transit_qty and open_po_qty without nonnegative checks. A snapshot with naive as_of, transit -5 and open PO -7 is accepted by the pure validator. Database constraints reject negative incoming values if an insert is later attempted, but cannot substitute for row-level validation. The timestamp can be silently interpreted through database/session timezone or fail when compared with aware dates.

The stale snapshot helper is not connected to a persistent snapshot/projection update, and stock_authorities has no active consumer or non-overlap enforcement. Its uniqueness permits external_snapshot and internal_ledger rows for the same scope to coexist. No operational movement ledger, authority cutover or balance reconstruction was implemented.

Required correction: validate offsets, finite/integer/range constraints and every bucket; implement and test the authoritative persisted update path before claiming inventory authority complete.

Probes: `test_naive_inventory_timestamp_is_rejected`, `test_negative_incoming_stock_is_rejected`.

### 9. [P1] Connect V2 to an actual supported import path before calling it built

Locations: backend/app/routers/integrations_hub.py:50,567–639; docs/superpowers/plans/2026-10-28-fashion-retail-v2-implementation.md, Task 5.1.

Repository searches find production V2 imports only inside the new V2 package. The upload router still imports the existing file_import parser/import_rows. There is no V2 router dispatch, mapping/preview integration, frontend use, feature-flag path or test_v2_import_pipeline.py. Creating helper functions does not make uploading a V2 file work through the software.

The sample test invokes service methods directly, not HTTP/UI. It parses product/SKU/inventory objects without persisting them, posts sales/returns into separate tables and supplies literal unit cost 600 to a calculator. Its all-eight-files test detects schema markers; it does not validate or post supplier/location/purchase business documents.

Required correction: finish the plan's route/preview/confirmation integration behind the agreed boundary, include authenticated route and UI tests, and explicitly document unsupported entity kinds until implemented. Block or deliberately route V2-marked files so the legacy mapper cannot silently reinterpret them.

### 10. [P1] Distinguish a required parent string from resolved catalog integrity

Locations: backend/app/services/integrations/v2/catalog.py:145–200.

validate_sku_row only requires a nonempty product_code; it has no tenant/catalog lookup and cannot establish that the parent exists. There is no accompanying V2 catalog persistence/orchestration path to resolve it. The batch validator explicitly exempts the default option signature from duplicate checks, so two default SKUs under one product are accepted. Duplicate SKU-code checks against persisted data are also absent here.

Additional static gaps: SKU attributes_json and product image_urls are not copied into their result objects; category-governed lookup checks, size-system dependencies, GTIN checks and dated-price conditional requirements are missing. Currency validation checks length only, not a legitimate configured code. Do not describe the eight column lists as eight complete typed validators.

Required correction: resolve tenant-scoped references at the integration boundary, enforce default as well as sized/color option uniqueness, and preserve/validate declared fields rather than silently dropping them.

Probe: `test_duplicate_default_variants_are_rejected`. Parent-resolution and dropped-field observations are static findings, not claimed DB reproductions.

### 11. [P1] Handle returns-only reporting periods and implement actual cost provenance

Location: backend/app/services/integrations/v2/valuation.py:98–99.

A period containing only a linked restocked return is valid: the original sale may belong to the prior month. With ex-tax credit 900 and original cost 600, the function reaches net_revenue.abs(), which does not exist on Python Decimal, and raises AttributeError. The documented default also calls for unavailable margin with a nonpositive denominator, not an alternative signed ratio.

Separately, accepting historical_unit_cost as a function argument is not historical issue-cost tracking. No valuation ledger, persisted receipt/issue matching, cost capture at fulfillment, landed-cost adjustment or opening-cost migration was built. The sample passes an assumed literal and proves arithmetic under that assumption only.

Required correction: handle return-only/zero/negative revenue denominators per the approved KPI contract, and implement validated persisted historical costing before claiming P0-07 complete.

Probe: `test_returns_only_period_does_not_crash`.

### 12. [P2] Preserve explicit numeric zero in validators

Locations: backend/app/services/integrations/v2/sales_returns.py:29–45; inventory.py:48–53.

`str(value or '')` turns native numeric zero into blank. A valid cancelled row with integer quantity_sold=0 is rejected as missing; exempt/zero-priced native numeric values have the same issue. CSV strings such as "0" escape this defect, so existing CSV-only tests miss the typed/Excel input boundary.

Required correction: distinguish None/blank from zero without truthiness conversion; test integer and Decimal zero as well as string zero. Reject nonfinite values and avoid float conversion when validating precise piece counts.

Probe: `test_cancelled_zero_quantity_is_validated_correctly`.

## Verification scope and interpretation

The claimed 46 tests consist of 10 V1 tests plus 36 V2 tests. Their existence and narrow coverage are verified. Passing them does not establish the missing acceptance criteria above. This review does not infer historical RED-before-GREEN execution from final test files or the pasted activity log.

Review probes express required behavior and deliberately expose defects in the current implementation. They are stored outside backend/tests, so they do not silently alter the normal repository suite. Database probes use the existing conftest's disposable PostgreSQL container, real Alembic migration chain, and sanket_app-role session fixture. Each affected review transaction is rolled back; only synthetic seeded records live in the disposable database. Production application files, existing plan/progress claims and client data were not changed.

See VERIFICATION.md for actual suite/probe results and commands. No fixes, production migration, source-authority cutover, deployment or browser/E2E verification was performed. The migration was exercised by the disposable test fixture; a production upgrade/downgrade rehearsal is not claimed.

## Recommended disposition

Change the implementation status to **partial, not integrated; P0 integrity defects outstanding**. Resolve the P1 findings and add these missing cases to normal regression coverage before enabling V2 or moving the roadmap to P1. Then complete the route/preview/persistence/authority/costing acceptance criteria and rerun full verification. Retain the useful foundational work rather than rewriting unrelated existing import functionality.
