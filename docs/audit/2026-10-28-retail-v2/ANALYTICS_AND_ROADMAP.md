# Analytics readiness and prioritized delivery roadmap

This is an implementation proposal awaiting design approval. No application code or database schema was changed for this audit. Estimates are planning ranges for an experienced backend/frontend/data team with QA and finance input; validate against actual capacity. A production-ready contract still needs implementation, migration rehearsal and operational proof.

## 1. KPI contracts and minimum history

All measures require tenant, source, currency, grain, business timezone, period bounds and coverage/completeness flags. Do not silently combine currencies or overlapping source exports. Store gross demand, returns and credited revenue separately. Stockout periods represent censored demand, not observed zero demand. Dimension changes need transaction snapshots or effective-dated dimension history for reproducible historical reports.

| KPI | Definition / minimum fields | History required and limitations |
|---|---|---|
| Daily/monthly sales trend | Recognized timestamp/business date, selling location, channel, sold units, discounted ex-tax amount, credited returns by credit date | Store/day aggregate supports store trends only. Line history needed for SKU breakdown; complete days in requested period. Return-date vs original-cohort attribution must be labeled. |
| SKU performance | SKU, gross sold, returns, net ex-tax revenue, availability and active range | Dated SKU lines or explicitly dated SKU aggregates. Current stock/period profit cannot generate a daily curve. |
| Category profitability | SKU-to-category as-of relationship, net ex-tax sales, original issue cost and reversals | Recognized sale/credit/cost events or qualified same-period source aggregates. Unavailable when historical cost unknown. |
| Store performance | Selling location and business date, recognized sales/credits, currency | Daily store totals work for revenue; do not confuse selling store and fulfillment warehouse. Comparable-store growth needs store open/close dates and a comparable prior period. |
| Inventory turnover | Period net COGS divided by time-weighted average carrying inventory value on the same tax/currency basis | Opening value plus full dated valuation history or representative daily values across period. Single closing snapshot insufficient. Annualize only with explicit period length. |
| Days inventory on hand | Accounting DIO = average inventory value / period COGS * days. Operational cover = current sellable units / qualified expected daily gross demand | Distinguish the two measures. DIO needs turnover history; cover needs dated SKU demand/forecast and fresh stock. Zero/unknown demand yields unavailable/infinite label according to policy, not fabricated days. |
| Sell-through | For a declared cohort/window: net retained sold units / (opening sellable units + accepted receipts + net eligible transfers in + adjustments to sellable supply) | Requires cohort definition, opening balances and all supply/sale/return movements. Returned units reintegrated through net numerator; do not also double add customer returns to denominator. Transfers and receipts treatment fixed across comparisons. |
| Dead stock | Positive stock with no gross sales for configured threshold, e.g. 180 days, and known active/launch dates | Complete demand coverage for threshold plus current stock. Missing history gives unknown, not dead. Newly launched items treated separately. |
| Slow moving | Trailing gross unit velocity/qualified in-stock selling days against category threshold | Usually 8–13 weeks for starting operational review; category/lifecycle configurable. Availability required to avoid confusing stockouts with lack of demand. |
| Stockout analysis | Per SKU/location availability intervals, active selling calendar, gross demand signals | Intraday availability events for duration; daily snapshots give only daily observations and cannot prove intraday stockout length. Lost sales are an estimate with uncertainty, never actual sales. |
| Return rate | Cohort returned units / recognized sold units, capped by valid original lines; value rate separately | Original sale links, return dates, reason and sufficient return-window maturity. Period returns/period sales is a different operational ratio and can exceed 100%. |
| Size demand | Gross sales/availability by SKU size/system/chart, product/category | Dated variant demand with stockout and assortment coverage. Unknown size excluded with coverage disclosed; no splitting assortment ranges. |
| Color demand | Gross sales/availability by approved color and SKU | Same as size. Color aliases preserve source shades and review status. |
| Seasonal performance | Product season/collection and launch/markdown calendar, dated demand and availability | At least two comparable seasonal cycles to assess recurrence; one season allows descriptive reporting, not reliable seasonal learning. |
| Supplier lead time | PO release timestamp to accepted receipt timestamp, ordered/received quantities, supplier/SKU/lane | At least completed deliveries, disclose sample count. Median/p90 distributions; on-time performance needs original promised date and partial receipt policy. |
| Supplier fill rate | Accepted receipts by promise/cutoff / due ordered units after approved cancellations | PO lines and dated receipts, cancellations, damage/rejections. Voucher totals cannot supply this. Cost performance also needs invoice matching/variance. |
| Gross profit/margin | Net ex-tax recognized revenue less matched historical COGS; margin = sum GP / sum revenue | Sale, credit, cost reversal and valuation adjustments; consistent period/currency. Reported aggregate margin allowed with explicit provenance. Markup based on cost is separate. |
| Demand forecasting | Gross units by SKU/location/time bucket, zero vs missing coverage, availability/promo/price/lifecycle, training cutoff | Starting gate can be configurable 13 complete weeks for baseline evaluation, not a universal statistical minimum. Annual seasonality normally needs >=2 cycles; intermittent/cold-start methods require separate validation. Holdout/backtest before decision use. |
| Replenishment | Qualified demand over lead+review time, current ATS, eligible PO/transit, unmet commitments, safety policy, MOQ/multiple, supplier lead times | Fresh authoritative stock and nonoverlapping supply pipelines; forecast quality/staleness gate. Recommendation has lineage, uncertainty and acceptance state. |

### Current report eligibility

The inspected daily sales report supports store/day sales/return/tender summaries for its own period. It cannot support SKU demand, size/color performance or SKU stock coverage. The inspected profit report supports reported SKU/store profitability for its title period but has no dates per transaction. It cannot supply a daily training sequence. Stock report supports quantity/value observations after confirming as_of and basis. Purchase vouchers support supplier/voucher summaries but not SKU procurement fulfillment, lead times or stock receipts. Preserve these useful reports while asking source systems for missing detailed exports.

### Replenishment calculation example and buffer treatment

Define policy explicitly. For an order-up-to method: `target = expected_gross_demand_during(lead_time + review_period) + safety_stock`; `inventory_position = sellable_unreserved + eligible_open_PO + eligible_transfer_transit - unmet_backorders`. Only count inbound due in the decision horizon under the configured reliability policy. Trigger when position is below the configured reorder point, or at scheduled review. `proposed = max(0,target-position)`, rounded to supplier order multiple and MOQ subject to max-stock/budget/capacity. Never add safety stock again if target/reorder point already includes it. Show assumptions and source freshness. A proposal becomes an actual order only through explicit acceptance and PO creation.

## 2. Prioritized roadmap

Complexity: S = a bounded subsystem task, M = multiple contracts/components, L = cross-cutting lifecycle/migration. These are not individual 2–5 minute implementation tasks. After design approval, break the first increment into test-first steps with a verification command per step under the repository writing-plans workflow.

| ID / priority | Improvement and problem solved | Complexity | Existing-data impact | Dependencies | Acceptance criteria |
|---|---|---|---|---|---|
| P0-01 | Freeze V1 contracts and trace all import routes; prevents divergent meanings | M | No destructive change; profile legacy inconsistencies | Inventory of routes/profiles | Contract tests cover frontend/universal differences, actual report grains and V1 replay; no unsupported aggregate-to-event conversion |
| P0-02 | Stable tenant/product/SKU keys and composite FKs; prevents orphans and cross-tenant joins | L | Backfill crosswalks; quarantine unresolved catch-all/name identities | P0-01, source owner review | Unknown parent blocked in V2; duplicate variants reported; RLS and cross-tenant reference tests fail closed |
| P0-03 | Quantity semantics, as_of and source authority; prevents double stock updates/stale overwrites | L | Legacy balances retain provenance; missing dates flagged; no automatic opening ledger | P0-01/02, location reconciliation | Available-only not mapped as on-hand; negatives never silently clamped; older snapshots cannot overwrite newer balances; authority cutover tested |
| P0-04 | Canonical sale/return recognition with single return owner; prevents double returns | L | Preserve V1 combined facts; bridge only with sufficient metadata | P0-02, event keys | Sale/full/partial return/exchange/cancel cases reconcile; concurrent over-return rejected; return dates preserved |
| P0-05 | Decimal/tax/discount basis and payment/refund separation; prevents financial errors | L | Mark unknown tax/currency basis; do not invent cost or refunds | P0-04, finance-approved rules | Paise allocations exact; split payments/refunds dedupe; credit+refund reverses revenue once; demo arithmetic reconciles |
| P0-06 | Unique event registry, posting groups and audit/outbox; safe retry/concurrency | L | Existing fingerprint keys remain in V1; V2 events require stronger identities | P0-02/04 | Concurrent duplicate uploads and post-commit ACK failure create one event; identity payload conflict blocks; cross-partition test passes |
| P0-07 | Historical valuation/opening cost and qualified profitability; prevents current-cost GP | L | Unknown old COGS stays unavailable; validated opening cost required | P0-03/05/06, finance policy | Cost issue/reversal and damaged return reconcile; no zero cost fallback; value roll-forward equals ledger |
| P0-08 | Immutable ledger/cutover and reconciliation; enables operational ERP stock | L | Begin optional external mode; internal migration pilot per scoped authority | P0-03/06/07 | Sale/receipt/transfer/count reversals are atomic; projection rebuild exact; baseline history not replayed into stock twice |
| P1-01 | Fashion category schemas, size/color charts and variant options; improves merchandising | M | Preserve raw descriptions and uncertain tokens; reviewed alias backfill | P0-02 | Kurti multi-size/color and one-size dupatta work; unknown sizes distinct; duplicate option signatures blocked |
| P1-02 | Location IDs, aliases, dated prices and replenishment policies; improves multi-store accuracy | M | Crosswalk existing text locations without merging unconfirmed names | P0-02/03, P1-01 | All positions resolve confirmed locations; store timezone dates correct; prices have explicit currency/effective scope |
| P1-03 | Supplier/SKU terms and PO/GRN/invoice/return lifecycle; separates commitments and actual supply | L | Voucher summaries remain summary lane; request detailed SKU procurement | P0-06/08, supplier mapping | PO does not add stock; GRN does once; invoice changes payable only; partial/many-to-many matching and supplier returns reconcile |
| P1-04 | Harden existing mapped imports with streaming/staging and typed profile semantics | L | Existing profiles versioned and migrated, not discarded | P0-01/06, agreed canonical contracts | Two retailer layouts import without manual reformat; profile revision locks, header collisions, row errors and resume tested on 100k benchmark |
| P1-05 | Backward compatibility pilot and deprecation telemetry; protects customers | M | Side-by-side read validation; explicit cutover, backups and exception queues | P0 complete; P1-01..04 | V1 files keep supported behavior; no silent reinterpretation; pilot totals/stock/cost reconcile and rollback rehearsal passes |
| P1-06 | Analytics fact marts and KPI qualification; prevents falsely precise dashboards | M | Existing aggregates labeled by grain/period; historical category mapping policy | P0-04/07, P1-01/02 | KPI eligibility matrix enforced; no fabricated SKU history; returns/GP denominator tests and report coverage checks pass |
| P2-01 | Forecast eligibility/backtesting, model registry and confidence; improves reliable demand estimates | L | Existing forecast run/results retained; ineligible histories withheld | P1-06, adequate dated SKU history | Gross demand target explicit; missing vs zero/stockout tested; rolling holdout metrics and baseline comparison published |
| P2-02 | Replenishment recommendations with supply/lead-time/MOQ rules | L | Existing suggestions mapped with lineage and staleness disclosure | P1-03, P2-01 | No double safety buffer/incoming; recommendations explain calculation; one acceptance creates one PO |
| P2-03 | Shopify/POS/ERP connectors and enterprise extensions | L | Source identities and authority per connector; no overlapping write ownership | P1-04/05, partner contracts | Webhook retries, late returns, source corrections and cursor replay reconcile against source controls; integration certification per partner |
| P2-04 | Advanced WMS/ownership/FX/FIFO/GL as business needs justify | L | Separate approved migrations, no universal mandatory expansion | Validated operational need and finance policy | Each extension has explicit cost/stock/financial ownership and migration tests; no unsupported accounting claims |

### Suggested sequencing and staffing

Discovery and contracts: roughly 1–2 weeks with product, finance, data and source-system owners. P0 analytics integrity and identity: roughly 3–6 weeks depending on unresolved legacy data. Operational ledger, valuation and procurement pilot: a further 4–8 weeks. P1 mapped onboarding and analytics can proceed in bounded increments after core contracts stabilize. P2 is conditional on data availability and measured value, not an automatic date promise. A small team should not attempt all lifecycle modules simultaneously. Re-estimate after the first migration rehearsal and 100k-row benchmark.

### First increment after design approval

Use manual writing-plans followed by RED/GREEN/REFACTOR. Example small task sequence for the quantity-semantics increment:

1. Add one mapper contract test proving negative stock is rejected rather than clamped; run the single test and verify failure reason.
2. Add one test proving available-only is not on-hand without a confirmed profile basis; run and verify failure.
3. Implement the minimal explicit semantics validation behind V2 routing; rerun those tests.
4. Add stale snapshot version test; observe failure, implement guarded projection update, verify it.
5. Add a V1 regression test for documented behavior and verify existing customers retain supported semantics with warnings.
6. Review diff and run required frontend/backend verification before merging that increment.

These tasks illustrate the required discipline, not authorization to start changing production code before design approval. Large lifecycle increments need their own approved bite-sized test plan.

## 3. Completion and release gates

Design gate: approve data ownership, authority cutover, completed-sale recognition policy, cost method, original-return exception process, tax configuration owner and legacy adapter policy. Defaults are documented so review can be concrete.

Implementation gate: required repository checks pass or pre-existing failures are explicitly triaged; migration/rollback rehearsal succeeds; RLS cannot be bypassed; source controls reconcile at matching grain; replay/concurrent return/partial failure tests pass; no unsupported or synthetic data reaches actual reports. For this documentation-only audit, those V2 service tests do not yet exist. Package checks validate headers, samples, dictionary coverage, references and arithmetic only.

Operations gate: posting/validation error monitoring, reconciliation alerts, owner playbooks, retained source documents, backup restore drill, access/retention settings, agreed throughput benchmark, and visible incomplete-data states. Finance approves valuation/tax policies before using the system as an operational accounting source.
