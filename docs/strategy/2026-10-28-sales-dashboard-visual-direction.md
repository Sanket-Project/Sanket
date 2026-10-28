# Sales analytics visual direction — proposed, awaiting approval

## Goal

Help a retailer answer, in order: how much did we sell, how did it change,
and where did sales come from? Keep exact figures and source context available.

## Evidence

Inspected SalesAnalytics.tsx, ClientReports.tsx, BranchSales.tsx, frontend/DESIGN.md,
the current API types, and saved desktop review screenshots. The local Browser
redirected to sign-in, so this proposal does not claim an authenticated live audit.
The workspace already contains extensive edits, including a completed earlier
sales redesign. Preserve those edits and their data-integrity behavior.

## Recommended direction

Use a compact overview with one accented sales total, two quieter context cards,
and a two-column content grid. Preserve Space Grotesk headings, IBM Plex Sans UI,
IBM Plex Mono figures and the existing teal semantic tokens. On mobile, place the
sales total first, context cards next, then stack the content in reading order.

For dated transactions: make the sales line chart the dominant panel, with a
compact, labeled best-seller ranking alongside. Put branch bars and today's
recorded totals beneath. Preserve history, grouping, metric and product-period
controls, explicit period labels, accessible exact values and request retries.
Display the actual covered date range when grouping expands the selected range.

For aggregate reports: lead with sales, items and named branch count, then use
ranked branch bars as the main visualization. Show gross profit and purchases in
a secondary panel with their independent date ranges. Use a compact profit table
below; disclose supplier purchases, branch profit and provenance progressively.
Never imply these reports support a time series or growth comparison.

Bars compare rank and size; lines show dated trends; tables provide precise
figures. Avoid gauges without targets and pie charts for ranked comparisons.
The prototype's illustration is not a specification to hardcode its values.

## Alternatives and trade-offs

1. Recommended: compact overview and two-column analysis. More information is
   visible at once, with explicit primary and secondary emphasis.
2. Keep the current stacked story. Easier for narrow screens, but requires more
   desktop scrolling and delays access to product comparisons.
3. Dense analyst workspace with every table expanded. Better for repeated
   lookup, but weaker for the fast comprehension requested here.

## Integrity and interaction requirements

- Show branches only when named by source data; disclose unassigned records.
- Keep currencies separate; use item counts for mixed-currency comparisons.
- Missing values remain unavailable, and chart gaps remain gaps.
- Comparisons exclude incomplete periods and use valid baselines.
- Negative returns need signed values and a zero baseline if visualized as bars.
- Keep dates and gross/net basis next to the affected figures.
- Keep destructive controls under data management, retaining role checks and
  the existing confirmation flow.
- Use existing icon exports, React, Recharts and Tailwind; no new dependencies.
- Preserve loading, error, empty, offline and partial-data states.

## Review artifact

frontend/review/sales-dashboard-proposal.html is an isolated design prototype,
with explicitly illustrative data. It includes imported-report and dated-sales
modes, a light/dark switch, and expandable detail. It does not call sales APIs,
modify records, authenticate, or replace production code. Sidebar context is
illustrative; no navigation redesign is proposed.

After design approval, write the implementation plan with small tasks and
verification per task. Follow RED → GREEN → REFACTOR for behavior changes,
review each diff, run the required frontend and backend checks, then verify
desktop/mobile and both themes using the real components.

## Proposal verification

Viewed the proposal in the in-app Browser at 1440 × 1000 and 375 × 812.
Verified source-view switching, light/dark switching and the expandable exact
sales table. Desktop document width was 1440px at a 1440px viewport; mobile
document width was at most 375px at a 375px viewport. Corrected a narrow-screen
money wrap and confirmed all three dated-sales headline values fit on one line.
Reviewed desktop light and mobile dark screenshots. Sample monthly sales sum
to ₹47,68,000 and 12,510 items; branch figures reconcile to those totals.

Screenshots are saved beside this document in sales-dashboard-proposal/.
No application source or API was changed. The required application test suites
have not been run for this isolated proposal; they remain part of implementation
verification after approval. This document records a proposed direction, not a
completed production redesign.
