---
version: 1
name: SANKET Predictive OS — Premium Minimal
reference: User-selected dashboard image, 29 October 2026
---

# Visual direction

Follow the user-selected reference: white navigation and panels, a near-white cool canvas, navy typography, deep teal actions, mint selection, fine borders, restrained shadows and compact, readable business information. The current reference supersedes the earlier lavender exploration.

The authoritative implementation is `src/styles/index.css`, consumed by semantic Tailwind colors in `tailwind.config.ts`. Primitive RGB channels feed semantic aliases and opacity-aware utilities; do not duplicate raw colors in page components. Every industry shares the interaction palette while retaining its terminology, features and server-owned scope.

## Tokens

| Role | Light | Dark |
|---|---|---|
| Canvas | #F8FAFC | #101D25 |
| Surface | #FFFFFF | #182A33 |
| Secondary surface | #F4F8FA | #203842 |
| Primary text | #10283F | #EAF3F3 |
| Body/label text | #536B82 | #B6CDD4 |
| Supporting text | #5B7388 | #99B4BF |
| Border | #E3EBEF | #2E4A55 |
| Primary action | #06484B | #8AD5CA |
| Selected surface | #E0F3EF | #214740 |
| Recorded chart series | #123548 | #C2DCE3 |
| Expected chart series | #0A998D | #8AD5CA |

Use success, warning and danger colors for evidenced statuses, accompanied by text/icons. Color alone must not communicate risk. Normal-sized text must pass 4.5:1 contrast against its intended surface. Missing data is unavailable, never an inferred zero or a healthy state.

## Typography and spacing

Retain the existing font assets: IBM Plex Sans for UI/body, Space Grotesk for headings, IBM Plex Mono selectively for IDs and aligned data. Page titles are 28px semibold, panel headings 15–18px, body 14px, labels/helper text 12px. Use tabular figures for comparisons. Avoid long uppercase labels and very small tracking-heavy copy.

Use the 4/8/12/16/20/24/32px spacing rhythm. Cards use 20px padding, compact cards 16px, forms 40px controls with larger mobile hit areas, and 12px panel corners. Controls use 8px corners, overlays 16px and the dashboard hero 20px. Static information panels do not lift on hover. Shadows identify floating controls rather than decorate every panel.

## Composition

The workspace uses a 244px collapsible white navigation rail and a quiet header with the actual navigation finder, breadcrumb, recorded-currency control, theme, alerts and account actions. The industry badge describes the authenticated workspace; it is not a switcher.

The dashboard uses an original editorial hero, compact metrics, the actual-versus-expected forecast as its analytical anchor, a contextual summary and an API-backed inventory snapshot. Catalog and inventory pages prioritize toolbars and working tables/grids. Decisions prioritize evidence and actions. Imports prioritize review, mapping and outcomes. Settings and onboarding prioritize aligned forms and progress. Preserve workflow-specific composition instead of turning every page into identical cards.

Complex tables scroll in their own region. The page itself must fit 390/768/1280/1536px widths. Dense navigation and filter controls wrap or scroll within their own boundary.

## Chart contract

Use `--chart-actual` for recorded demand and `--chart-forecast` for expected demand, with a dashed predicted line and a labeled P10–P90 band. Preserve null gaps and observed zeros. Provide units, dates, contextual tooltips and exact tabular values where supported. A model interval is nominal, not a measured accuracy claim. Summed SKU quantiles are not calibrated portfolio quantiles; keep that explanation available.

## Icons and logo

Import every UI icon through `src/components/ui/icons.tsx`; never directly from lucide-react or react-iconly. Iconly owns generic interface vocabulary at 1.5px; lucide owns supply-chain concepts and the complete status ladder. Use numeric sizes and currentColor. Add new symbols centrally.

Reuse `LogoMark`: the forecast peak in the deep teal tile with a pale mint curve and apex node. Never substitute a letter or a newly drawn decorative mark.

## Motion and accessibility

Use 120–180ms feedback and restrained 180–240ms disclosures. Respect reduced motion for CSS animation, transitions, smooth scrolling and JS consumers. Avoid perpetual decorative motion and intermediate animated business values. Keep visible focus, associated labels/descriptions, busy announcements, keyboard table activation, tab navigation, Escape handling and mobile drawer focus restoration.

## Reference and artwork

The source image is `C:/Users/admin/Downloads/ChatGPT Image Oct 29, 2026, 02_26_03 PM.png`. Its records, products and numbers are visual examples, not production data. Original generated planning artwork lives in `public/images/planning-hero.png`; the optimized 42KB WebP is the consumed asset. It is decorative, not a representation of a customer's actual stock. Catalog imagery must come from existing product image sources.

Design-review fixtures live only in `e2e/` and are visibly labeled. The production application never imports or mounts them.

## Components

Use the shared kit before writing page-local UI. All live in `src/components/ui/` unless noted.

| Need | Use | Notes |
|---|---|---|
| A KPI | `MetricTile` | `provenance` is required: recorded, estimated, forecast or heuristic. `null` shows "—" plus a reason. `KPICard` (`components/charts/KPICard`) is a legacy adapter: it takes an optional `provenance` (default recorded) and bridges the legacy sentinel values "Unavailable" / "—" to the unavailable state, using `subtitle` as the reason. |
| A table | `DataTable` (`Table`) | `sortValue` per column, `loading`, `density`, `maxHeight`, `mobile="cards"` with column `priority`, `selection` only where bulk actions exist, `caption`. |
| Filters | `FilterBar` + `Select` / `SegmentedControl` | Native select. Segmented control for 2–5 views. |
| Views on one page | `Tabs` | WAI-ARIA tabs; arrow keys move focus, Enter selects. |
| Grouping without a card | `Section` | Heading, hairline divider, actions. |
| Loading, error, unavailable | `LoadingState`, `ErrorState`, `UnavailableState`, `QueryBoundary` | Never render 0 for missing data. QueryBoundary: cached data stays on a failed refresh with a stale note; a disabled (idle) query renders `idle`, not an error. |
| Detail or history panel | `Drawer` | Shares focus handling with `Modal` (`useDialogFocus`). |
| A chart | `components/charts/kit`: `ChartFrame`, `ChartTooltip`, `ChartLegend`, `AXIS_PROPS`, `GRID_PROPS`, `formatDateTick`, `formatCompact`, `useCurrencyTick` | Tooltip order: actual, expected, range, lower, upper. Currency axes use `useCurrencyTick(currency)` so ticks match the app's money display. |
| Type | `.t-page .t-section .t-card .t-kpi .t-label .t-body .t-table` | Instead of `text-[Npx]`. |
| Motion | `duration-fast` (140ms), `duration-base` (200ms), `ease-standard` | Reduced motion is handled globally. |
