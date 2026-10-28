# Critical audit of existing files

28 October 2026. Static source/data audit; no live database was read or changed. Only the brief was attached in this chat. The four client reports below were found in Downloads and inspected directly. Three archived workbooks were inspected separately. Source hashes and exact headers are in source_manifest.json. No supplier identities, registrations or client sample rows are copied into the synthetic deliverables.

## Decision

The current platform is an analytics and planning foundation, not yet a transaction-complete retail ERP. Preserve the existing mapping, replay identity, location and forecast capabilities. The highest risks are mixed report grains, ambiguous stock semantics, duplicate master quantities, incomplete historical costing and unlinked returns. A richer CSV alone will not fix them.

## Verified application evidence

- frontend/src/utils/csvImport.ts: Products requires name/category; SKUs requires sku_code only. Numeric master validation checks numeric conversion but not nonnegative/integer/domain constraints. Both master downloads include warehouse_inventory, forecast_demand and monthly_sales. SKU download includes both lead_time_days and lead_time.
- frontend/src/api/inventory.ts: requires sku_code/on_hand_units, optionally inbound_units/reserved_units/location/source. The download omits as_of and source. Frontend checks nonnegative quantities; the server file mapper instead silently clamps negatives.
- backend/app/services/integrations/file_import.py: map_sales_row rejects quantity < 0 and returns < 0, accepts zero demand, derives gross from price*quantity and net by subtracting discount. It does not define tax/return-value allocation here. Name-only rows can generate a SKU. map_inventory_row maps a broad available field into on_hand_units, clamps negative values, and defaults location. These are verified static findings, not a claim of a reproduced runtime failure.
- backend/app/models/inventory.py: one current balance per tenant/SKU/location with as_of; available property clamps on_hand-reserved at zero. No disjoint damaged/quarantine buckets or movement ledger in this model.
- backend/app/models/product.py: product attributes and SKU attributes already provide extension points. SKU has reference cost/price, defaults currency to USD, and SKU-global buying policy.
- backend/app/models/location.py: locations and per-location forecasts already exist. V2 strengthens references and provenance rather than inventing these capabilities.
- backend/app/services/sales_identity.py: transaction/period replay identities already exist. Fallback fingerprints and occurrence suffixes cannot establish real identity across edited overlapping files. Explicit source event IDs remain necessary.
- backend/app/services/integrations/import_profiles.py and import_layout/import_review/import_dates/import_transforms: saved tenant mapping profiles, revision checks, file-bound confirmation and interpretation machinery already exist. Extend and harden these; do not replace them with an unrelated importer.

## Observed files and reporting grains

| Source | Actual grain and limitation | Safe use |
|---|---|---|
| stock balence Report 2026.csv | Company label / Stock No position. Stock date absent from columns. Description embeds some size/color tokens and ranges such as S TO XXL. | Confirm branch mapping, snapshot time and quantity basis. Do not expand assortment text into invented variants. |
| Sales Data 2026.xlsx | Row 9 headers; store/day sales/return and tender totals; no SKU or order-line identifiers. | Daily store summary lane only. Never allocate these totals across SKUs. |
| Gross Profit Data 2026.xlsx | Row 9 headers; SKU/store aggregate over title period; no individual sale dates. Includes both markup and margin. | Reported period profitability facts. Cannot create daily SKU demand. |
| Purchasr Report 2026.xlsx | Row 2 headers; voucher/supplier quantities and amounts; no SKU lines or receiving locations. | Procurement summary lane. Cannot generate SKU receipts or PO fulfillment. |
| qa_test_products_import.xlsx | Five synthetic master rows with planning quantities. | QA only; not client evidence. |
| qa_test_inventory_import.xlsx | Four synthetic stock rows with no location/as_of. | Legacy QA only; cannot establish real opening stock. |
| Redwine archived workbook | Sales Ledger and Warehouse Inventory plus Executive Summary. Formula cache gaps reported in manifest; authenticity unverified. | Structural test reference only; not proof of actual client activity. |

All raw workbook rows were scanned for structure/formulas. This audit does not assert independently re-executed reconciliation of every client total. Prior reconciliation results in docs/audit/2026-10-27-swecha-client-data/source-reconciliation.json remain prior evidence, not newly computed results.

## Required and optional status today

Product download: name/category required, other columns optional. SKU download: sku_code required by frontend; parent optional there. Inventory: sku_code/on_hand_units required; location defaults in legacy flows. Sales universal import: sku/quantity/timestamp required at header validation, though mapper supports a name fallback. Other uploader fields are optional; this route mismatch needs a contract test. Reports are source exports, not application templates: requiredness for them is defined by a saved source profile, not guessed from populated cells.

## Application Products download

| Existing Field | Current Purpose | Problem | Recommended Change | Priority | Business Justification |
|---|---|---|---|---|---|
| name | Item description | Must not generate identity or infer size/color without review | Keep display/raw description; explicit product and SKU codes | P1 | Avoid variant merging |
| brand | Brand label | Free spelling variants fragment reporting | Tenant brand ID and confirmed alias mapping | P1 | Reliable brand analysis |
| category | Category classification | Free labels create taxonomy drift | Approved category hierarchy with raw-to-canonical mapping | P1 | Reliable category reporting |
| subcategory | Category classification | Free labels create taxonomy drift | Approved category hierarchy with raw-to-canonical mapping | P1 | Reliable category reporting |
| external_id | Source identity/status/dimension/date | Semantics require typed, scoped dictionary and null handling | Validate type and lookup; preserve raw source; avoid inferred facts | P1 | Stable interoperable imports |
| status | Source identity/status/dimension/date | Semantics require typed, scoped dictionary and null handling | Validate type and lookup; preserve raw source; avoid inferred facts | P1 | Stable interoperable imports |
| warehouse_inventory | Unscoped stock quantity | Duplicates inventory ownership; lacks SKU/location/time | Remove from master; migrate only with confirmed grain and snapshot time | P0 | Prevents inconsistent stock |
| lead_time | Lead time | Ambiguous unit and duplicate lead_time_days | Map to supplier_skus.lead_time_days after confirmation | P1 | Lead times differ by supplier and SKU |
| safety_stock | Stock policy | Not physical stock; master-global policy | Move to SKU/location replenishment policy | P1 | Store policies differ |
| forecast_demand | Forecast scalar | No horizon, run, model, location or confidence | Move to forecast run/results; preserve legacy raw value only | P0 | Forecast is not observed demand |
| monthly_sales | Historical summary scalar | No month, gross/net definition or location | Import dated actual sales or retain labeled period aggregate | P0 | Prevents fabricated history |

## Application SKUs download

| Existing Field | Current Purpose | Problem | Recommended Change | Priority | Business Justification |
|---|---|---|---|---|---|
| product_external_id | Parent product key | Frontend validation requires only SKU code | Require existing parent in V2; quarantine unresolved parents | P0 | Prevents orphan or catch-all products |
| sku_code | Sellable item identity | Must remain tenant-scoped text; unknown SKU policy differs by route | Resolve stable SKU FK; reject unknown V2 transaction references | P0 | No invented catalog identity |
| description | Item description | Must not generate identity or infer size/color without review | Keep display/raw description; explicit product and SKU codes | P1 | Avoid variant merging |
| unit_cost | Catalog reference unit cost | Not historical issue cost | reference_cost_ex_tax plus receipt valuation ledger | P0 | Accurate historical COGS |
| unit_price | Catalog price | MRP and selling price/tax basis not separated | Effective-dated selling price and MRP records | P1 | Correct promotions and location pricing |
| currency | Monetary currency | SKU model defaults USD; uploads may omit currency | Require INR or explicit confirmed profile default | P0 | No false currency conversion |
| lead_time_days | Replenishment lead time | SKU-global value misses supplier route | Use supplier SKU fallback plus lane lead times | P1 | Correct supply planning |
| lead_time | Lead time | Ambiguous unit and duplicate lead_time_days | Map to supplier_skus.lead_time_days after confirmation | P1 | Lead times differ by supplier and SKU |
| moq | Minimum order quantity | No supplier or pack multiple | Move to supplier_skus with order_multiple | P1 | Supplier-specific buying constraints |
| safety_stock | Stock policy | Not physical stock; master-global policy | Move to SKU/location replenishment policy | P1 | Store policies differ |
| reorder_point | Reorder threshold | SKU-global policy | Move to SKU/location policy | P1 | Correct multi-location planning |
| gtin | Trade item identifier | Text/check digit/allocation validation needed | Optional legitimate GS1 identifier; internal barcode separate | P1 | SKU codes are not GTINs |
| external_id | Source identity/status/dimension/date | Semantics require typed, scoped dictionary and null handling | Validate type and lookup; preserve raw source; avoid inferred facts | P1 | Stable interoperable imports |
| warehouse_inventory | Unscoped stock quantity | Duplicates inventory ownership; lacks SKU/location/time | Remove from master; migrate only with confirmed grain and snapshot time | P0 | Prevents inconsistent stock |
| forecast_demand | Forecast scalar | No horizon, run, model, location or confidence | Move to forecast run/results; preserve legacy raw value only | P0 | Forecast is not observed demand |
| monthly_sales | Historical summary scalar | No month, gross/net definition or location | Import dated actual sales or retain labeled period aggregate | P0 | Prevents fabricated history |

## Application Inventory download

| Existing Field | Current Purpose | Problem | Recommended Change | Priority | Business Justification |
|---|---|---|---|---|---|
| sku_code | Sellable item identity | Must remain tenant-scoped text; unknown SKU policy differs by route | Resolve stable SKU FK; reject unknown V2 transaction references | P0 | No invented catalog identity |
| on_hand_units | Current physical stock | No mandatory snapshot time; inadequate status buckets | on_hand_qty plus as_of and location required | P0 | Stops stale stock overwrites |
| inbound_units | Incoming units | PO commitments and dispatched transfers conflated | Split open PO from transit; reconcile authoritative documents | P1 | No duplicated supply |
| reserved_units | Allocated physical units | No allocation lifecycle or oversubscription rule | Reservation records and disjoint stock state validation | P0 | Prevents overselling |
| location | Location reference | Free text aliases may duplicate a physical location | Canonical location FK with approved aliases | P0 | Reliable stock and store metrics |

## Application sales uploader supported fields (not a discovered CSV download)

| Existing Field | Current Purpose | Problem | Recommended Change | Priority | Business Justification |
|---|---|---|---|---|---|
| sku | Sellable item identity | Must remain tenant-scoped text; unknown SKU policy differs by route | Resolve stable SKU FK; reject unknown V2 transaction references | P0 | No invented catalog identity |
| name | Item description | Must not generate identity or infer size/color without review | Keep display/raw description; explicit product and SKU codes | P1 | Avoid variant merging |
| quantity | Quantity | Meaning changes with document/report type | Require document_type or explicit sales quantity semantics | P0 | Purchase returns cannot become sales |
| timestamp | Sales date/time | Timezone and recognition basis unspecified | Offset timestamp and location timezone | P0 | Correct daily reporting |
| price | Sales unit selling price | Tax basis unspecified | Explicit unit_price_ex_tax; configured inclusive adapter | P0 | Financial reconciliation |
| revenue | Source gross line revenue | Gross/net/tax semantics not fixed | Explicit gross ex-tax control and recomputation | P0 | No double discount |
| discount | Sales discount | Amount vs percent and line vs unit ambiguous | Positive allocated line discount_ex_tax | P0 | Correct net sales |
| channel | Source identity/status/dimension/date | Semantics require typed, scoped dictionary and null handling | Validate type and lookup; preserve raw source; avoid inferred facts | P1 | Stable interoperable imports |
| region | Source identity/status/dimension/date | Semantics require typed, scoped dictionary and null handling | Validate type and lookup; preserve raw source; avoid inferred facts | P1 | Stable interoperable imports |
| order_id | Order identity | Not enough to identify repeated SKU lines | Require stable order_line_id and transaction event ID | P0 | Safe deduplication |
| line_id | Order line identity | Optional legacy identity permits ambiguous replay | Required immutable line ID in V2 | P0 | Corrections distinguishable from new events |
| warehouse | Location reference | Free text aliases may duplicate a physical location | Canonical location FK with approved aliases | P0 | Reliable stock and store metrics |
| returns | Returned units | Unlinked scalar lacks event date/value/refund | Nonnegative legacy only; V2 returns event with original line | P0 | Avoid duplicate reversals |
| in_stock | Source identity/status/dimension/date | Semantics require typed, scoped dictionary and null handling | Validate type and lookup; preserve raw source; avoid inferred facts | P1 | Stable interoperable imports |
| stockout | Source identity/status/dimension/date | Semantics require typed, scoped dictionary and null handling | Validate type and lookup; preserve raw source; avoid inferred facts | P1 | Stable interoperable imports |
| currency | Monetary currency | SKU model defaults USD; uploads may omit currency | Require INR or explicit confirmed profile default | P0 | No false currency conversion |

## stock balence Report 2026.csv

| Existing Field | Current Purpose | Problem | Recommended Change | Priority | Business Justification |
|---|---|---|---|---|---|
| Company Name | Source branch label | May represent location rather than tenant/legal company | Confirmed location aliases within authenticated tenant | P0 | Protects tenancy and location joins |
| Stock No | Source item code | Do not assume GTIN, style or globally unique identity | Tenant/source SKU crosswalk preserving exact text | P0 | Reliable joins and leading zeros |
| Item Description | Item description | Must not generate identity or infer size/color without review | Keep display/raw description; explicit product and SKU codes | P1 | Avoid variant merging |
| Category | Category classification | Free labels create taxonomy drift | Approved category hierarchy with raw-to-canonical mapping | P1 | Reliable category reporting |
| Brand | Brand label | Free spelling variants fragment reporting | Tenant brand ID and confirmed alias mapping | P1 | Reliable brand analysis |
| Style No | Source style | May collide across brands/suppliers; not variant identity | Product/style attribute with explicit grouping crosswalk | P1 | Avoid merging distinct products |
| Sub Category | Category classification | Free labels create taxonomy drift | Approved category hierarchy with raw-to-canonical mapping | P1 | Reliable category reporting |
| Cost Price | Source stock cost | Location variation and tax basis unknown | Preserve per-position reported cost; confirm tax and method | P0 | No arbitrary catalog cost overwrites |
| Retail Price | Reported retail price | Not proven MRP or actual sale price | Preserve source label; map only after confirmation | P1 | Avoid mislabeled pricing |
| Closing Bal.Qty | Closing reported stock | Snapshot date absent; quantity basis needs confirmation | on_hand_qty only after confirmed semantics and as_of | P0 | Never infer physical stock from ATS |
| Closing Bal.Val | Closing reported value | Cost method and tax basis not explicit | Store reported control value; reconcile valuation ledger | P0 | No unsupported inventory valuation |

## Sales Data 2026.xlsx

| Existing Field | Current Purpose | Problem | Recommended Change | Priority | Business Justification |
|---|---|---|---|---|---|
| Company Name | Source branch label | May represent location rather than tenant/legal company | Confirmed location aliases within authenticated tenant | P0 | Protects tenancy and location joins |
| Voucher Date | Source identity/status/dimension/date | Semantics require typed, scoped dictionary and null handling | Validate type and lookup; preserve raw source; avoid inferred facts | P1 | Stable interoperable imports |
| Type | Source identity/status/dimension/date | Semantics require typed, scoped dictionary and null handling | Validate type and lookup; preserve raw source; avoid inferred facts | P1 | Stable interoperable imports |
| Total Sales Bill | Source report measure | Report-grain value is not an event identity or normalized master | Retain raw measure and declared grain; typed mapping before posting | P1 | Avoid unsupported transaction reconstruction |
| Sales Qty | Reported sold units | Different file grains; cannot infer timestamps | Preserve report grain and period; request source transactions | P0 | Correct demand eligibility |
| Sales Amount | Reported monetary measure | Tax, sign, grain or formula basis must be declared | Preserve reported control; canonical decimal and reconciliation policy | P0 | Consistent financial basis |
| Total Return Bill | Source report measure | Report-grain value is not an event identity or normalized master | Retain raw measure and declared grain; typed mapping before posting | P1 | Avoid unsupported transaction reconstruction |
| Return Qty | Daily returned units | Store/day total cannot link original lines | Keep store/day summary; request line returns export | P0 | No invented SKU returns |
| Return Amount | Daily returned money | Tax and refund basis unclear | Preserve source summary and confirm basis | P0 | Returns differ from cash refunds |
| Total Net Bill | Source report measure | Report-grain value is not an event identity or normalized master | Retain raw measure and declared grain; typed mapping before posting | P1 | Avoid unsupported transaction reconstruction |
| Net Qty | Sold less returned units | Cannot reconstruct gross demand from net alone | Retain gross sales and returns separately | P0 | Protects return rate and forecasts |
| Net Amount | Reported monetary measure | Tax, sign, grain or formula basis must be declared | Preserve reported control; canonical decimal and reconciliation policy | P0 | Consistent financial basis |
| CARD | Daily tender/settlement summary | Not individual captured payments or refund allocations | Keep daily summary; request payment/refund references for reconciliation | P0 | Avoid counting tenders as revenue |
| Cash | Daily tender/settlement summary | Not individual captured payments or refund allocations | Keep daily summary; request payment/refund references for reconciliation | P0 | Avoid counting tenders as revenue |
| Credit Note | Daily tender/settlement summary | Not individual captured payments or refund allocations | Keep daily summary; request payment/refund references for reconciliation | P0 | Avoid counting tenders as revenue |
| E-Wallet | Daily tender/settlement summary | Not individual captured payments or refund allocations | Keep daily summary; request payment/refund references for reconciliation | P0 | Avoid counting tenders as revenue |
| Payment Pendig | Daily tender/settlement summary | Not individual captured payments or refund allocations | Keep daily summary; request payment/refund references for reconciliation | P0 | Avoid counting tenders as revenue |

## Gross Profit Data 2026.xlsx

| Existing Field | Current Purpose | Problem | Recommended Change | Priority | Business Justification |
|---|---|---|---|---|---|
| Company Name | Source branch label | May represent location rather than tenant/legal company | Confirmed location aliases within authenticated tenant | P0 | Protects tenancy and location joins |
| Stock No | Source item code | Do not assume GTIN, style or globally unique identity | Tenant/source SKU crosswalk preserving exact text | P0 | Reliable joins and leading zeros |
| Item Description | Item description | Must not generate identity or infer size/color without review | Keep display/raw description; explicit product and SKU codes | P1 | Avoid variant merging |
| Brand | Brand label | Free spelling variants fragment reporting | Tenant brand ID and confirmed alias mapping | P1 | Reliable brand analysis |
| Sales Qty | Reported sold units | Different file grains; cannot infer timestamps | Preserve report grain and period; request source transactions | P0 | Correct demand eligibility |
| Net Sales Value | Reported monetary measure | Tax, sign, grain or formula basis must be declared | Preserve reported control; canonical decimal and reconciliation policy | P0 | Consistent financial basis |
| Sale Value (Without Tax) | Reported monetary measure | Tax, sign, grain or formula basis must be declared | Preserve reported control; canonical decimal and reconciliation policy | P0 | Consistent financial basis |
| Cost of Goods (With Tax) | Tax-inclusive source cost | Recoverable tax may not be COGS | Retain reported source control; use validated ex-tax cost basis | P0 | Consistent revenue/cost tax basis |
| Cost of Goods (Without Tax) | Tax-exclusive source COGS | Period totals lack issue history | Import reported aggregate, not synthesized issue ledger | P0 | Preserve auditability |
| Gross Profit Amount | Reported monetary measure | Tax, sign, grain or formula basis must be declared | Preserve reported control; canonical decimal and reconciliation policy | P0 | Consistent financial basis |
| Gross Profit % (Based on Cost) | Markup percentage | Not margin; averaging invalid | Label markup; recompute from summed GP/cost | P0 | Prevents overstated gross margin |
| Gross Profit % (Based on Sale) | Sales margin percentage | Averaging row percentages invalid | Recompute summed GP/ex-tax revenue | P0 | Weighted correct profitability |

## Purchasr Report 2026.xlsx

| Existing Field | Current Purpose | Problem | Recommended Change | Priority | Business Justification |
|---|---|---|---|---|---|
| Voucher Type | Procurement document type | Signed returns require type-aware normalization | Map Purchase vs Purchase Return to explicit positive events | P0 | Prevents double sign inversion |
| Voucher Date | Source identity/status/dimension/date | Semantics require typed, scoped dictionary and null handling | Validate type and lookup; preserve raw source; avoid inferred facts | P1 | Stable interoperable imports |
| Voucher Number | Voucher identifier | Must be scoped by source, supplier/type as appropriate | Immutable document identity and duplicate conflict checks | P0 | Safe replays |
| Party Name | Supplier label | Name not stable supplier identifier | Supplier crosswalk; preserve raw name and resolve ID | P1 | No accidental supplier merges |
| Quantity | Quantity | Meaning changes with document/report type | Require document_type or explicit sales quantity semantics | P0 | Purchase returns cannot become sales |
| Disc. Amount | Reported monetary measure | Tax, sign, grain or formula basis must be declared | Preserve reported control; canonical decimal and reconciliation policy | P0 | Consistent financial basis |
| Tax Amount | Reported monetary measure | Tax, sign, grain or formula basis must be declared | Preserve reported control; canonical decimal and reconciliation policy | P0 | Consistent financial basis |
| Net Amount | Reported monetary measure | Tax, sign, grain or formula basis must be declared | Preserve reported control; canonical decimal and reconciliation policy | P0 | Consistent financial basis |

## qa_test_products_import.xlsx

| Existing Field | Current Purpose | Problem | Recommended Change | Priority | Business Justification |
|---|---|---|---|---|---|
| name | Item description | Must not generate identity or infer size/color without review | Keep display/raw description; explicit product and SKU codes | P1 | Avoid variant merging |
| category | Category classification | Free labels create taxonomy drift | Approved category hierarchy with raw-to-canonical mapping | P1 | Reliable category reporting |
| subcategory | Category classification | Free labels create taxonomy drift | Approved category hierarchy with raw-to-canonical mapping | P1 | Reliable category reporting |
| brand | Brand label | Free spelling variants fragment reporting | Tenant brand ID and confirmed alias mapping | P1 | Reliable brand analysis |
| external_id | Source identity/status/dimension/date | Semantics require typed, scoped dictionary and null handling | Validate type and lookup; preserve raw source; avoid inferred facts | P1 | Stable interoperable imports |
| lead_time | Lead time | Ambiguous unit and duplicate lead_time_days | Map to supplier_skus.lead_time_days after confirmation | P1 | Lead times differ by supplier and SKU |
| safety_stock | Stock policy | Not physical stock; master-global policy | Move to SKU/location replenishment policy | P1 | Store policies differ |
| forecast_demand | Forecast scalar | No horizon, run, model, location or confidence | Move to forecast run/results; preserve legacy raw value only | P0 | Forecast is not observed demand |
| monthly_sales | Historical summary scalar | No month, gross/net definition or location | Import dated actual sales or retain labeled period aggregate | P0 | Prevents fabricated history |

## qa_test_inventory_import.xlsx

| Existing Field | Current Purpose | Problem | Recommended Change | Priority | Business Justification |
|---|---|---|---|---|---|
| sku_code | Sellable item identity | Must remain tenant-scoped text; unknown SKU policy differs by route | Resolve stable SKU FK; reject unknown V2 transaction references | P0 | No invented catalog identity |
| on_hand_units | Current physical stock | No mandatory snapshot time; inadequate status buckets | on_hand_qty plus as_of and location required | P0 | Stops stale stock overwrites |
| inbound_units | Incoming units | PO commitments and dispatched transfers conflated | Split open PO from transit; reconcile authoritative documents | P1 | No duplicated supply |
| reserved_units | Allocated physical units | No allocation lifecycle or oversubscription rule | Reservation records and disjoint stock state validation | P0 | Prevents overselling |

## Redwine_Label_Fashion_Sales_and_Inventory_Record (1).xlsx

| Existing Field | Current Purpose | Problem | Recommended Change | Priority | Business Justification |
|---|---|---|---|---|---|
| Order ID | Source report measure | Report-grain value is not an event identity or normalized master | Retain raw measure and declared grain; typed mapping before posting | P1 | Avoid unsupported transaction reconstruction |
| Order Date | Source identity/status/dimension/date | Semantics require typed, scoped dictionary and null handling | Validate type and lookup; preserve raw source; avoid inferred facts | P1 | Stable interoperable imports |
| SKU | Sellable item identity | Must remain tenant-scoped text; unknown SKU policy differs by route | Resolve stable SKU FK; reject unknown V2 transaction references | P0 | No invented catalog identity |
| Product ID | Parent source product | Repeated alongside SKU; may disagree | Validate against SKU parent; master-owned relationship | P0 | Correct product aggregation |
| Product Name | Item description | Must not generate identity or infer size/color without review | Keep display/raw description; explicit product and SKU codes | P1 | Avoid variant merging |
| Category | Category classification | Free labels create taxonomy drift | Approved category hierarchy with raw-to-canonical mapping | P1 | Reliable category reporting |
| Size | Variant size | No size system or measurement chart | size_code plus size_system and chart reference | P1 | M is not universal sizing |
| Quantity Ordered | Ordered units | Ordered is not fulfilled or recognized sale | Map only with recognition policy and status | P0 | Avoid overstated sales |
| Unit Retail Price | Reported monetary measure | Tax, sign, grain or formula basis must be declared | Preserve reported control; canonical decimal and reconciliation policy | P0 | Consistent financial basis |
| Total Revenue | Calculated revenue | Archived workbook formulas may have no cached values | Recalculate with validated engine or explicitly derive documented formula | P0 | Blank cache is not zero revenue |
| Unit Product Cost | Source unit cost | Tax/cost method not declared | Preserve source and qualify cost basis; do not use current master | P0 | Profit needs historical cost |
| Total Cost of Goods | Reported monetary measure | Tax, sign, grain or formula basis must be declared | Preserve reported control; canonical decimal and reconciliation policy | P0 | Consistent financial basis |
| Gross Profit Contribution | Reported monetary measure | Tax, sign, grain or formula basis must be declared | Preserve reported control; canonical decimal and reconciliation policy | P0 | Consistent financial basis |
| Fulfillment Warehouse | Location reference | Free text aliases may duplicate a physical location | Canonical location FK with approved aliases | P0 | Reliable stock and store metrics |
| Sales Channel | Source identity/status/dimension/date | Semantics require typed, scoped dictionary and null handling | Validate type and lookup; preserve raw source; avoid inferred facts | P1 | Stable interoperable imports |

## Redwine_Label_Fashion_Sales_and_Inventory_Record (1).xlsx

| Existing Field | Current Purpose | Problem | Recommended Change | Priority | Business Justification |
|---|---|---|---|---|---|
| SKU | Sellable item identity | Must remain tenant-scoped text; unknown SKU policy differs by route | Resolve stable SKU FK; reject unknown V2 transaction references | P0 | No invented catalog identity |
| Product ID | Parent source product | Repeated alongside SKU; may disagree | Validate against SKU parent; master-owned relationship | P0 | Correct product aggregation |
| Product Name | Item description | Must not generate identity or infer size/color without review | Keep display/raw description; explicit product and SKU codes | P1 | Avoid variant merging |
| Category | Category classification | Free labels create taxonomy drift | Approved category hierarchy with raw-to-canonical mapping | P1 | Reliable category reporting |
| Size | Variant size | No size system or measurement chart | size_code plus size_system and chart reference | P1 | M is not universal sizing |
| Warehouse Code | Location reference | Free text aliases may duplicate a physical location | Canonical location FK with approved aliases | P0 | Reliable stock and store metrics |
| Fulfillment City | Source identity/status/dimension/date | Semantics require typed, scoped dictionary and null handling | Validate type and lookup; preserve raw source; avoid inferred facts | P1 | Stable interoperable imports |
| Stock On Hand (Qty) | Source report measure | Report-grain value is not an event identity or normalized master | Retain raw measure and declared grain; typed mapping before posting | P1 | Avoid unsupported transaction reconstruction |
| Safety/Reorder Threshold | Combined policy threshold | Safety stock and reorder point conflated | Require separately defined safety_stock_qty and reorder_point_qty | P1 | Avoid double counting buffers |
| Unit Cost (INR) | Reported monetary measure | Tax, sign, grain or formula basis must be declared | Preserve reported control; canonical decimal and reconciliation policy | P0 | Consistent financial basis |
| Unit Price (INR) | Reported monetary measure | Tax, sign, grain or formula basis must be declared | Preserve reported control; canonical decimal and reconciliation policy | P0 | Consistent financial basis |
| Total Asset Value (At Cost) | Calculated stock value | Formula cache and cost method need validation | Qualified source control only | P0 | No false value from blank cache |
| Inventory Status | Source report measure | Report-grain value is not an event identity or normalized master | Retain raw measure and declared grain; typed mapping before posting | P1 | Avoid unsupported transaction reconstruction |

## Gap assessment

| Capability | Current evidence | V2 recommendation |
|---|---|---|
| Catalog | Products/SKUs and JSON attributes exist; parent optional in SKU upload | Enforce stable product parent and category-typed variants, including one default variant |
| Inventory | Current balance with as_of; broad aliases and clamping | Explicit quantity semantics, immutable stock ledger, reservations and controlled snapshots |
| Sales/returns | Gross units and returns fields, replay keys | Stable line/event identity, separate returns/credit/refund entities and recognition rules |
| Procurement | Client voucher summaries; no procurement models found in inspected model directory | Supplier/PO/receipt/invoice/return lifecycle, retain aggregates separately |
| Finance | Catalog cost and reported source GP | Historical valuation/COGS, tax basis and allocations |
| Import interoperability | Mapping profiles and reviewed interpretation already implemented | Versioned canonical contracts, source authority, streaming and posting groups |
| Forecasting | Run/result and location forecast structures exist | Feed only eligible dated actuals, preserve model/cutoff/horizon and censored demand |
| Tenancy | Tenant IDs/RLS required by repository | Composite tenant FKs plus RLS and worker isolation |

Missing data is not zero. No report total, synthetic test row or forecast should silently become an observed SKU transaction.

## Full-row source profiling

data_profile.json records blank/distinct/numeric/negative/fractional counts for every inspected table column, candidate-key duplicates and independent detail sums against available footer controls. These diagnostics exclude confirmed title/header/footer rows. Candidate-key duplicates are review signals, not automatic proof of duplicated business events. Footer comparison is a separate fresh check from the prior client audit; it does not prove the business authenticity of either detail or footer.

| File / sheet | Detail rows | Candidate duplicate groups | Excess rows |
|---|---:|---:|---:|
| stock balence Report 2026.csv / CSV | 16519 | 0 | 0 |
| Sales Data 2026.xlsx / Sheet1 | 121 | 0 | 0 |
| Gross Profit Data 2026.xlsx / Sheet1 | 15524 | 0 | 0 |
| Purchasr Report 2026.xlsx / Sheet1 | 266 | 0 | 0 |
| qa_test_products_import.xlsx / Products | 5 | 0 | 0 |
| qa_test_inventory_import.xlsx / Inventory | 4 | 0 | 0 |
| Redwine_Label_Fashion_Sales_and_Inventory_Record (1).xlsx / Sales Ledger | 500 | 0 | 0 |
| Redwine_Label_Fashion_Sales_and_Inventory_Record (1).xlsx / Warehouse Inventory | 150 | 0 | 0 |

Use the recorded detail-minus-footer differences to distinguish rounding and scope inconsistencies. Do not sum report percentages or price columns. Formula cells without cached values in the archived workbook are not zero-valued facts. The profile is read-only and does not repair or overwrite any source data.

## Specific data-quality observations

- Stock: 16,519 detail positions and 38,419 closing units; no duplicate company/Stock No keys or negative numeric values in inspected detail. This does not establish the missing measurement date or prove that closing stock is physically sellable.
- Sales: 121 store/day details; 2,683 sold units less 40 returned units = 2,643 net units. Sales amount INR 2,640,989 less returns INR 59,055 = INR 2,581,934 net. All these footer comparisons reconcile exactly. The already-net columns must not have returns subtracted again.
- Gross profit: 15,524 details include 8 negative Sales Qty rows, 18 negative Net Sales Value rows, and 985 negative Gross Profit Amount rows. These are net period observations, not automatically invalid transactions. Preserve signed aggregate measures. Negative GP can represent genuine loss; never normalize every negative amount into a return. Gross sales demand cannot be recovered uniquely from these net quantities.
- Purchase report: 266 detail vouchers include 29 negative quantities, 29 negative tax amounts and 29 negative net amounts. The source adapter must validate voucher type before converting return magnitudes to positive canonical purchase-return events. Negative purchase returns are not a reason to weaken the no-negative-sales rule.
- Archived fashion workbook: 500 sale rows have 1,500 formula cells without cached results. Its 150 inventory rows have calculated asset-value/status fields with missing cached outputs. Numeric results must be explicitly calculated/verified or withheld; missing caches cannot become zero revenue, zero cost or zero inventory value.
- No duplicate candidate keys were observed in these selected table grains. This is not evidence of globally unique transaction identity: the actual daily sales and period-profit reports do not contain transaction line keys.
