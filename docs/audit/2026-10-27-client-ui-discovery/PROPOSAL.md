# Client catalogue, regional trends, dashboard and inventory proposal

Status: approved by the user on 2026-10-27 and implemented. See [implementation and verification](IMPLEMENTATION.md). The evidence below records the pre-change discovery.

## Evidence and limits

Inspected the running local swecha-demo workspace after its requested business-data reset. It remains empty; no sample data was restored. Screenshots were saved and inspected at the current in-app browser viewport. The populated inventory evidence is the user's supplied screenshot. The dashboard confidence capsule is hidden in the empty workspace; its layout issue was assessed from source and the user's report.

1. Dashboard — needs clearer text hierarchy and confidence placement. [Screenshot](01-dashboard.png).
2. Trend Analysis — poor catalogue relevance: industry preset products and aggregate industry signals remain visible with an empty company catalogue. [Screenshot](02-trend-analysis.png).
3. Regional Insights — poor geographic clarity: Telangana produces no matching centers; some state labels are treated as cities with unknown states. Anonymous native selects lack a district drill-down. [Screenshot](03-telangana-regional.png).
4. Inventory — needs simpler onboarding and decision hierarchy: large zero-value summary cards dominate the empty state. The supplied populated screenshot repeats SKUs per store, technical explanations and assumed lead-time badges; a Critical status can sit alongside No action. [Screenshot](04-inventory-empty.png).

## Proposed design

### Regional Insights and dropdowns

- State → District filters, including Hyderabad and all 33 Telangana districts, using the official Telangana district reference. Searchable, labelled comboboxes with keyboard navigation, clear selection and consistent teal styling; menus scroll within the viewport.
- Keep district choices available when evidence is missing. Show No data for this district rather than inventing scores or distributing a state score across districts.
- Validate geography at ingestion and preserve state/city/district granularity. A state result must not become a city card. Label external interest as a relative search-interest index rather than sales growth.
- State and district selections narrow company sales where uploaded records have an explicit geographic mapping. Missing mapping remains visible; do not infer a store's district from its name alone.

### Company-based Trend Analysis

- Replace preset product lists with searchable products, categories and SKUs from the tenant's uploaded catalogue. Group variant SKUs under relevant product search terms rather than querying every internal SKU code.
- Separate Company sales trends, calculated from uploaded sales, from External market interest matched to catalogue terms. Display period, source, freshness and matched products. Missing history or external evidence gets a clear empty state.
- Reuse the existing focus configuration where appropriate. Keep private catalogue-derived requests/results tenant scoped under RLS; reuse public signals only where relevant. Deduplicate and bound background collection for the 25k-SKU target.
- An empty catalogue shows an import prompt, without unrelated industry products standing in for company trends.

### Dashboard confidence

- Replace the floating amber capsule with one aligned Confidence field in the planning summary: score, readable band and View reasons. Keep short labels on one line and allow explanatory text to wrap naturally.
- Identify confidence as a forecast evidence/readiness assessment; do not imply measured accuracy. Reduce competing copy and keep a clear heading → status → next action hierarchy.

### Inventory

- Default to one row per SKU, with product name primary, SKU code secondary, available units and count of stores needing attention. Expand a SKU to inspect its stores. Selecting one location switches to that store's stock view.
- Put attention filters first: All, Needs stock, Overstock and Missing data. Use plain language such as Stock lasts 14 days, Available and Arriving. Keep forecast method and replenishment assumptions in details, with a visible summary where needed.
- Show a saved recommendation only when it matches the SKU and location. A shortage with no recommendation says Review shortage rather than No action. Keep suggested review steps distinct from executable recommendations; never invent order quantities.
- Do not present pooled stock cover as individual-store cover. Replace the misleading loaded-row Stock decisions count with accurate SKU/location counts and server-side pagination/search for the complete catalogue, removing the effective 500-row ceiling.
- Empty inventory gives a short import path for products/SKUs, sales and stock rather than a screen dominated by zero totals.

## Alternatives considered

Styling-only changes would leave incorrect geography and catalogue relevance intact. Product-only grouping could hide hundreds of SKUs under one generic imported product. The recommended SKU overview plus expandable stores keeps variants discoverable while reducing repeated rows.

## Implementation after approval

Write a task-by-task plan with verification, then implement using failing tests first. Cover geographic normalization and missing evidence, tenant catalogue filtering, confidence layout, location-specific recommendations, pagination and empty states. Verify frontend typecheck/lint/tests, backend pytest, and the affected browser flows at desktop and narrow widths. Use isolated test fixtures; keep the real workspace empty.

Reference: [Official Telangana district list](https://www.telangana.gov.in/about/districts/). The local registry currently contains only 15 Telangana districts and does not power a district selector.
