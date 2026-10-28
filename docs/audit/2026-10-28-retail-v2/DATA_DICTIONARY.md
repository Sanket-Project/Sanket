# V2 CSV data dictionary

Proposal dated 28 October 2026. R = required; O = optional; C = conditionally required. Derived fields are excluded from write contracts. Each table fixes header order. Blank is unknown, never automatically zero. These are proposed contracts, not supported endpoints in the current application.

CSV uses UTF-8, RFC-style quoting, comma delimiter, decimal dot and no currency/grouping symbols. Identifiers are text. Piece quantities are integers. Financial totals round to 2 decimals using decimal half-up after line discount allocation. Unit costs/prices retain 4 decimals. Timestamps require ISO 8601 offset. A tenant is obtained from authenticated context, never an uploaded tenant_id.

## products

```csv
schema_version,product_code,product_name,brand_code,category_code,style_number,description,collection_code,season_code,status,hsn_code,tax_class_code,manufacturer_supplier_code,image_urls,attributes_json
```

| Column | Type | Required | Meaning and validation |
|---|---|---|---|
| schema_version | text | R | Exactly retail_v2.0.products |
| product_code | text(64) | R | Stable tenant-unique product/style identity; never infer from name |
| product_name | text(200) | R | Display name; never a relationship key |
| brand_code | text(64) | O | Approved tenant brand lookup; blank means unknown |
| category_code | text(64) | R | Approved leaf category; its parent supplies subcategory hierarchy |
| style_number | text(64) | O | Manufacturer style; not globally unique |
| description | text | O | Plain text description |
| collection_code | text(64) | O | Tenant collection lookup |
| season_code | text(64) | O | Tenant season lookup; not an inferred date |
| status | enum | R | active; seasonal; clearance; pre_launch; discontinued |
| hsn_code | text(8) | O | Verified HSN as text; required before taxable posting if applicable; blank in samples |
| tax_class_code | text(64) | O | Effective-dated tax class lookup; required before taxable posting |
| manufacturer_supplier_code | text(64) | O | Supplier FK for manufacturer only; purchasing suppliers use supplier_skus |
| image_urls | json array | O | HTTPS URLs; no image fetched during import; blank unknown |
| attributes_json | json object | O | Category-schema validated product defaults; SKU may override declared variant dimensions |

## skus

```csv
schema_version,sku_code,product_code,external_sku_id,color_code,color_name,size_code,size_system,barcode,gtin,mrp_incl_tax,selling_price_incl_tax,reference_cost_ex_tax,currency,price_valid_from,status,attributes_json
```

| Column | Type | Required | Meaning and validation |
|---|---|---|---|
| schema_version | text | R | Exactly retail_v2.0.skus |
| sku_code | text(64) | R | Tenant-unique stable sellable variant; preserve leading zeros |
| product_code | text(64) | R | FK products.product_code; no catch-all parent in V2 |
| external_sku_id | text(128) | O | Source-specific identity; source_system is supplied by import profile |
| color_code | text(64) | C | Required if category uses color dimension; approved lookup |
| color_name | text(100) | O | Display label; must agree with color_code |
| size_code | text(32) | C | Required if category uses size; approved size-system lookup |
| size_system | text(32) | C | Required with size_code; label IN_ALPHA does not imply universal measurements |
| barcode | text(64) | O | Internal barcode text; distinct namespace from GTIN |
| gtin | text(14) | O | Only legitimate assigned 8/12/13/14 digit GTIN with valid check digit; blank sample |
| mrp_incl_tax | decimal(18,2) | O | Nonnegative INR example; regulated maximum retail price; effective from price_valid_from |
| selling_price_incl_tax | decimal(18,2) | O | Nonnegative default price; actual transaction price is separate |
| reference_cost_ex_tax | decimal(18,4) | O | Optional planning/reference cost; never historical COGS |
| currency | char(3) | R | ISO currency code; INR samples; never silently default USD |
| price_valid_from | timestamptz | C | Required if MRP or selling price provided; creates price list record |
| status | enum | R | active; inactive; discontinued |
| attributes_json | json object | O | Variant-only schema-validated attributes, e.g. measurements |

## inventory

```csv
schema_version,snapshot_id,as_of,sku_code,location_code,on_hand_qty,reserved_qty,damaged_qty,quarantine_qty,in_transit_qty,open_po_qty,source_system,count_reference,reported_stock_value_ex_tax,currency
```

| Column | Type | Required | Meaning and validation |
|---|---|---|---|
| schema_version | text | R | Exactly retail_v2.0.inventory; snapshot contract only |
| snapshot_id | text(128) | R | Source-stable snapshot identity; repeated keys are retry not new adjustment |
| as_of | timestamptz | R | Business measurement time with offset; not upload timestamp |
| sku_code | text(64) | R | FK skus.sku_code |
| location_code | text(64) | R | FK locations.location_code |
| on_hand_qty | integer | R | Nonnegative physically held units including reserved/damaged/quarantine |
| reserved_qty | integer | R | Nonnegative subset of good on-hand, exclusive of damaged/quarantine |
| damaged_qty | integer | R | Nonnegative mutually exclusive unavailable stock bucket |
| quarantine_qty | integer | R | Nonnegative mutually exclusive quality-control stock bucket |
| in_transit_qty | integer | O | Destination-bound dispatched transfer units; reconcile transfer ledger; not on hand |
| open_po_qty | integer | O | Unreceived and uncancelled PO units; excludes transfer transit |
| source_system | text(64) | R | Registered external authority identifier; tenant scope server supplied |
| count_reference | text(128) | O | Approved physical count reference; mandatory for count adjustment posting |
| reported_stock_value_ex_tax | decimal(18,4) | O | Nonnegative source control value only; never silently overwrite cost ledger |
| currency | char(3) | C | Required when reported_stock_value_ex_tax present |

## sales

```csv
schema_version,source_system,transaction_id,order_id,order_line_id,transaction_at,sku_code,location_code,fulfillment_location_code,channel_code,quantity_sold,returns,unit_price_ex_tax,mrp_incl_tax,discount_ex_tax,tax_code,tax_rate_pct,tax_amount,currency,order_status,invoice_number,place_of_supply_state_code,payment_method,payment_reference,payment_amount
```

| Column | Type | Required | Meaning and validation |
|---|---|---|---|
| schema_version | text | R | Exactly retail_v2.0.sales |
| source_system | text(64) | R | Registered source namespace; not a generic upload label |
| transaction_id | text(128) | R | Immutable source event identifier |
| order_id | text(128) | R | Source order header identity |
| order_line_id | text(128) | R | Stable order line identity; cannot substitute SKU when repeated lines exist |
| transaction_at | timestamptz | R | Recognition event time with offset; local business day from location timezone |
| sku_code | text(64) | R | FK skus.sku_code; product derived through SKU |
| location_code | text(64) | R | Selling location FK; fulfillment location optional separately |
| fulfillment_location_code | text(64) | O | Stock issuing location FK; defaults to selling location only by confirmed profile |
| channel_code | text(64) | R | Approved channel lookup; pos; web; marketplace examples |
| quantity_sold | integer | R | Nonnegative; >0 for recognized sale; zero only for cancelled state |
| returns | integer | R | Exactly 0 here; physical returns posted only through returns.csv |
| unit_price_ex_tax | decimal(18,4) | R | Nonnegative selling price before discount excluding GST, per unit |
| mrp_incl_tax | decimal(18,2) | O | Historical MRP snapshot; not used to derive realized revenue |
| discount_ex_tax | decimal(18,2) | R | Nonnegative total allocated LINE discount, not percentage and not per unit |
| tax_code | text(64) | R | Approved effective-dated classification; sample is illustrative only |
| tax_rate_pct | decimal(7,4) | R | Nonnegative percentage; 5 means 5 percent; validate against configured tax code |
| tax_amount | decimal(18,2) | R | Nonnegative GST total; inclusive/exclusive source conversion happens before this contract |
| currency | char(3) | R | ISO currency code; one currency per order |
| order_status | enum | R | completed; cancelled; completed means recognized and fulfilled for this simple contract |
| invoice_number | text(128) | O | Source tax invoice reference; required by configured fiscal posting policy |
| place_of_supply_state_code | text(2) | C | Required for GST posting; official state code text |
| payment_method | text(64) | O | Convenience only for exactly one tender; mixed requires payment child import |
| payment_reference | text(128) | C | Required to create a payment; blank method alone does not imply payment |
| payment_amount | decimal(18,2) | C | Nonnegative; repeat order payment reference must carry identical header data |

## returns

```csv
schema_version,source_system,return_id,return_line_id,return_at,original_source_system,original_transaction_id,original_order_line_id,sku_code,location_code,returns,return_value_ex_tax,tax_code,tax_amount,currency,reason_code,disposition,credit_note_number,refund_reference,refund_amount,refund_method,refund_at,exchange_order_id,status
```

| Column | Type | Required | Meaning and validation |
|---|---|---|---|
| schema_version | text | R | Exactly retail_v2.0.returns |
| source_system | text(64) | R | Registered source namespace |
| return_id | text(128) | R | Stable return header identity |
| return_line_id | text(128) | R | Stable return line identity |
| return_at | timestamptz | R | Approved return/credit recognition time; received disposition applied at this time in simple contract |
| original_source_system | text(64) | C | Original namespace; mandatory unless approved unlinked return workflow |
| original_transaction_id | text(128) | C | Original sale event; mandatory for linked return |
| original_order_line_id | text(128) | C | Original line; cumulative approved returns cannot exceed recognized sold units |
| sku_code | text(64) | R | FK SKU; must match original line |
| location_code | text(64) | R | Receiving location FK; may differ from original sale |
| returns | integer | R | Strictly positive physical return quantity; never negative sales |
| return_value_ex_tax | decimal(18,2) | R | Nonnegative credit after original discount allocation, excluding GST |
| tax_code | text(64) | R | Original applicable tax classification; do not use today's rate |
| tax_amount | decimal(18,2) | R | Nonnegative credited GST; separate fiscal eligibility validation |
| currency | char(3) | R | Must match original sale or use explicit FX workflow |
| reason_code | text(64) | R | Approved reason e.g. size_issue; damaged; unwanted |
| disposition | enum | R | restock; quarantine; damaged; no_receipt; simple file records physical outcome |
| credit_note_number | text(128) | O | Fiscal/commercial credit reference; required for fiscal posting policy |
| refund_reference | text(128) | O | Optional one refund header; repeated ref must agree and allocated child lines deduplicate |
| refund_amount | decimal(18,2) | C | Nonnegative cash credit; required with refund reference; not additional revenue reversal |
| refund_method | text(64) | C | Required with refund reference; tender lookup |
| refund_at | timestamptz | C | Required with refund reference; can differ from return time |
| exchange_order_id | text(128) | O | Optional replacement sale order identity; both legs remain independent |
| status | enum | R | approved; draft; rejected; only approved posts credit and receipt |

## purchases

```csv
schema_version,source_system,document_type,document_id,document_line_id,document_at,supplier_code,sku_code,location_code,po_id,po_line_id,related_document_id,related_document_line_id,quantity,unit_cost_ex_tax,discount_ex_tax,freight_ex_tax,tax_code,tax_rate_pct,tax_amount,currency,invoice_number,expected_delivery_date,status
```

| Column | Type | Required | Meaning and validation |
|---|---|---|---|
| schema_version | text | R | Exactly retail_v2.0.purchases; one row per document line event |
| source_system | text(64) | R | Registered source namespace |
| document_type | enum | R | purchase_order; goods_receipt; supplier_invoice; purchase_return |
| document_id | text(128) | R | Stable identity within source and document type |
| document_line_id | text(128) | R | Stable line identity within document |
| document_at | timestamptz | R | Business posting/order time with offset |
| supplier_code | text(64) | R | FK suppliers.supplier_code |
| sku_code | text(64) | R | FK SKU; invoice summaries without SKU use separate summary lane |
| location_code | text(64) | R | Destination/return-issuing location FK |
| po_id | text(128) | C | PO header identity; required for PO and linked documents |
| po_line_id | text(128) | C | PO line identity; required for linked receipt/invoice/return |
| related_document_id | text(128) | C | For purchase_return: original receipt document ID; optional invoice/receipt matching elsewhere |
| related_document_line_id | text(128) | C | Required with related document ID; original source is same namespace in simple contract |
| quantity | integer | R | Strictly positive ordered/received/invoiced/returned units according to document_type |
| unit_cost_ex_tax | decimal(18,4) | R | Nonnegative unit base cost; realized receipt cost and invoice variance kept separately |
| discount_ex_tax | decimal(18,2) | R | Nonnegative total line discount |
| freight_ex_tax | decimal(18,2) | R | Nonnegative allocated line freight; never repeat whole-header freight on each line |
| tax_code | text(64) | R | Configured purchase tax classification; sample illustrative |
| tax_rate_pct | decimal(7,4) | R | Percentage; effective-date validate |
| tax_amount | decimal(18,2) | R | Nonnegative total line tax after applicable allocation |
| currency | char(3) | R | ISO currency code; one currency per document |
| invoice_number | text(128) | C | Required on supplier_invoice; unique per supplier/fiscal scope |
| expected_delivery_date | date | O | ISO YYYY-MM-DD; useful on PO |
| status | enum | R | draft; posted; cancelled; posted events immutable |

## suppliers

```csv
schema_version,supplier_code,supplier_name,supplier_type,gstin,state_code,country_code,currency,payment_terms_days,default_lead_time_days,contact_email,phone,address,status
```

| Column | Type | Required | Meaning and validation |
|---|---|---|---|
| schema_version | text | R | Exactly retail_v2.0.suppliers |
| supplier_code | text(64) | R | Tenant-unique stable identity |
| supplier_name | text(200) | R | Synthetic sample name explicitly marked |
| supplier_type | enum | R | manufacturer; wholesaler; distributor; other |
| gstin | text(15) | O | Verified tax registration; blank sample; syntax validity does not establish registration |
| state_code | text(2) | C | Required for GST posting; state lookup |
| country_code | char(2) | R | ISO country code |
| currency | char(3) | R | Default purchasing currency; transaction snapshots override explicitly |
| payment_terms_days | integer | O | Nonnegative contractual due-day offset |
| default_lead_time_days | integer | O | Nonnegative fallback only; supplier_skus owns item-specific values |
| contact_email | text(254) | O | Optional email; no message sent by importing |
| phone | text(32) | O | Optional contact number preserved as text |
| address | text | O | Supplier address; blank synthetic sample |
| status | enum | R | active; inactive; blocked |

## locations

```csv
schema_version,location_code,location_name,location_type,parent_location_code,timezone,state_code,country_code,address,fulfills_orders,status
```

| Column | Type | Required | Meaning and validation |
|---|---|---|---|
| schema_version | text | R | Exactly retail_v2.0.locations |
| location_code | text(64) | R | Tenant-unique stable identity; explicit aliases map legacy case variants |
| location_name | text(200) | R | Human label |
| location_type | enum | R | store; warehouse; virtual |
| parent_location_code | text(64) | O | FK location; no self-link or cycles |
| timezone | text(64) | R | IANA timezone; business day calculated here |
| state_code | text(2) | C | Required for GST posting |
| country_code | char(2) | R | ISO country code |
| address | text | O | Postal address; blank synthetic sample |
| fulfills_orders | boolean | R | true or false only |
| status | enum | R | active; inactive |
