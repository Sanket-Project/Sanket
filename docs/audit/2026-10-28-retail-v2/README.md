# Fashion retail V2 review package

Prepared 28 October 2026. This package is an architecture proposal, not an implemented application release. Existing V1 imports remain unchanged. V2 CSV files must not be uploaded to production until the V2 adapter is built and approved.

Read in this order:

1. AUDIT.md — verified current fields, per-field findings, source limitations and gap analysis.
2. ARCHITECTURE.md — ownership, normalized entities, stock/finance rules, ERD, trade-offs.
3. DATA_DICTIONARY.md or data_dictionary.csv — ordered complete field contracts for eight imports.
4. IMPORT_SPEC.md — validation, mapping, scale, replay, migration and acceptance examples.
5. ANALYTICS_AND_ROADMAP.md — KPI prerequisites, priorities, dependencies and acceptance criteria.
6. templates/ — eight header-only CSVs; samples/ — eight clearly synthetic CSVs.

All DEMO identities and example.invalid contacts are invented test values. GTIN, GSTIN and HSN fields are deliberately blank. DEMO-TAX-5 is an illustrative 5% configuration to exercise arithmetic, not a statement of the statutory rate for these goods. Configure verified effective-dated rates and HSN classifications before fiscal use. Taxable samples require that setup and verified HSN; they are not filing-ready invoices.

Import order: confirm tenant source profiles and brand/category/collection/season/tax/size/color/channel/reason lookups; suppliers; locations (parents first); products; SKUs; approved opening inventory; historical sales; returns; purchases in PO, receipt, invoice, return order. Opening inventory is as of 1 October before the sample sale. Opening stock represents prior history and is not a receipt from the sample PO. Historical imports at or before a later stock baseline do not mutate that baseline again. Procurement examples occur after the sale and return.

Sample expectations: sell two kurtis for INR 1,800 excluding tax after INR 200 line discount; GST INR 90; collect INR 1,890. Return one for INR 900 plus INR 45 credited tax; refund INR 945. Ex-tax net revenue INR 900, retained sale COGS INR 600, GP INR 300 and margin 33.3333% assuming confirmed historical issue cost INR 600/unit. PO 10, receipt 10, invoice 10, supplier return 1. PO remaining-to-receive = 0; net retained receipts = 9; supplier credit pending until separately documented. Final kurti physical stock = 20 - 2 + 1 + 10 - 1 = 28, including one damaged unit. With opening reservation 2 unchanged, ATS = 25. Dupatta has one one-size variant with 10 units and no sales.

source_manifest.json records inspected originals without copying client rows. SOURCES.md separates conventions from design choices. verification.json records package checks. The ZIP contains documentation, templates, dictionary, manifest and samples only; it excludes client files, backups, logs and this builder.
