# Premium Minimal — Pass 2: shared component kit and workflow-group migration

**Date:** 2026-10-29
**Branch:** `design/premium-minimal-pass-2` (checkpoint `7e47945` holds pass 1)
**Status:** Design approved in chat; spec awaiting review.

## Context

Pass 1 (checkpoint `7e47945`) applied the Premium Minimal reference to every
screen at the token and palette level: white surfaces, a cool near-white
canvas, navy text, deep teal actions, mint selection, a light navigation rail,
the planning hero and the forecast chart contract. `frontend/DESIGN.md` is the
design-language source of truth and is unchanged by this pass. Baseline at the
checkpoint: `tsc` clean, Vitest 82 files / 387 tests passing.

Pass 1 left the pages sharing tokens but not components. Measured in
`frontend/src` (non-test `.tsx`):

| Pattern | Files | Shared alternative today |
|---|---|---|
| Hand-built `<table>` | 18 | `Table` used in 4 |
| Raw `<select>` | 20 | `SearchableSelect` used in 2 |
| Hand-rolled `animate-pulse` loaders | 19 | `Skeleton` used in 0 |
| Recharts `<Tooltip>` with local styling | 7 | none |
| `role="tab"` implementations | 2 | none |

The review harness (`frontend/e2e/review.html`) renders a blank page for
`screen=SalesAnalytics`: `AppShell` calls `useWorkspaceIndustry`, which throws
outside an authenticated workspace, and the harness route does not provide one.

## Decisions already made

- **Build on pass 1**, do not restart.
- **Palette:** the reference's white, deep teal and mint. No lavender or purple.
  The master prompt's lavender wording is superseded by the reference image and
  `DESIGN.md`.
- **Approach A:** build the shared component kit first, then migrate screens
  in workflow groups.

## Guardrails

1. No backend, API-contract, schema, auth, tenancy or industry-scope changes.
   `api/` modules are consumed as they are.
2. No new product capability the backend does not support (no header product
   search, no industry switcher: industry is server-owned).
3. Every existing control keeps its behaviour and its accessible name, so the
   existing page tests remain valid. Destructive actions stay behind
   `ConfirmDialog`.
4. No hardcoded demonstration data in production code. Fixtures stay in `e2e/`.
5. Missing data renders as unavailable, never as an inferred zero.
6. Icons import only through `components/ui/icons.tsx`.
7. No new runtime dependency. `framer-motion` is already installed; CSS
   transitions are preferred where they suffice.

## 1. Foundation additions

In `frontend/src/styles/index.css` and `frontend/tailwind.config.ts`:

- **Motion tokens:** `--dur-fast: 140ms` (hover, press, focus),
  `--dur: 200ms` (disclosure, tab, dropdown, drawer), `--ease: cubic-bezier(0.2, 0, 0, 1)`.
  Exposed as Tailwind `duration-fast`, `duration-base`, `ease-standard`. The
  existing `prefers-reduced-motion` block sets both durations to `0ms`.
- **Type-scale utilities** (`@layer components`), from the `DESIGN.md` sizes:
  `.t-page` (28px semibold heading font), `.t-section` (18px), `.t-card` (15px),
  `.t-kpi` (28px tabular), `.t-label` (12px medium muted), `.t-body` (14px),
  `.t-table` (13px tabular). They replace ad-hoc `text-[15px]` and similar
  values as screens migrate.
- **Focus ring:** `.focus-ring`, a 2px accent outline with a 2px offset on
  `:focus-visible`, applied by every kit control.
- **Elevation:** keep the existing `shadow-sm|md|lg` tokens, with roles fixed:
  `sm` for resting panels, `md` for popovers and dropdowns, `lg` for modals and
  drawers. Static panels do not lift on hover.

## 2. Component kit

All of these live in `frontend/src/components/ui/`. Existing component APIs
stay backward compatible, so unmigrated screens keep working.

### DataTable (upgrade of `Table`)

The existing `Table<T>` props are unchanged; everything new is optional.

- `sort`: a column opts in with `sortValue: (row) => string | number | null`.
  Header buttons set `aria-sort`. Sorting is client-side, applied only to the
  rows passed in, and nulls sort last. Server-paginated tables do not enable it.
- `loading`: renders `rows` skeleton rows that keep the column widths.
- `density`: `"comfortable"` (default, py-3) or `"compact"` (py-2).
- `maxHeight`: the table scrolls in its own region and the header stays sticky
  inside it.
- `mobile="cards"`: below 768px each row renders as a card. A column's
  `priority: "primary" | "secondary" | "hidden-mobile"` controls placement.
- `selection`: an optional `{ selected, onChange }` that adds a checkbox
  column. Used only where bulk actions already exist (Products, SKUs).
- `caption`: a visually hidden `<caption>` for screen readers.
- Row click and keyboard activation behave as they do today.

### MetricTile (successor to `KPICard`)

Props: `label`, `value`, `unit?`, `provenance`, `hint?`, `tone?`, `icon?`,
`href? | onClick?`, `unavailableReason?`.

- `provenance` is one of `"recorded" | "estimated" | "forecast" | "heuristic"`
  and renders as a small labelled marker. It is required, so every KPI states
  where its number comes from.
- When `value` is `null` or `undefined`, the tile shows "—" and
  `unavailableReason`. It never shows 0.
- No delta is rendered unless the caller passes a computed one; a delta is
  never invented.
- `KPICard` stays as a thin adapter over `MetricTile` with provenance
  `"recorded"`, until its callers migrate. It is then removed.

### Select, SegmentedControl, Tabs, FilterBar

- `Select`: a styled wrapper over the native `<select>`, which keeps native
  keyboard and screen-reader behaviour, with a label, a hint and an error.
  It replaces the raw selects.
- `SegmentedControl`: for 2–5 mutually exclusive views (daily/weekly/monthly).
  A radio group with arrow-key navigation.
- `Tabs`: the WAI-ARIA tabs pattern with roving tabindex, Home/End and
  `aria-controls`. An optional `onChange` lets a page keep the tab in its URL.
- `FilterBar`: a wrapping toolbar slot with filters on the left, actions on
  the right and a "Clear filters" button when any filter is active. On mobile
  it scrolls horizontally within its own bounds.

### Chart primitives (`components/charts/kit/`)

- `ChartFrame`: title, description, legend slot, controls slot, and states for
  loading, empty and error with a fixed height, so the layout does not jump.
- `ChartTooltip`: one tooltip for all charts. It shows the date, the series
  values with their units, and the range when one exists. The order follows
  `DESIGN.md`: actual, then expected, then lower/upper.
- `ChartLegend`: plain-language series names with matching swatches. A dashed
  swatch marks forecast series.
- `axis.ts`: tick formatters for dates (by granularity), compact numbers and
  currency, plus the shared grid and axis props.
- The existing `ForecastChart` keeps its data contract and adopts these pieces.

### State views

- `LoadingState` (`Skeleton` variants: `lines`, `card`, `chart`, `table`),
  `EmptyState` (existing), `ErrorState` (message plus an optional retry that
  calls the query's `refetch`) and `UnavailableState` (data the source cannot
  supply, with the reason).
- `QueryBoundary`: a small helper that takes a TanStack Query result and
  renders the right state, so pages stop repeating `isLoading`/`isError`
  branches.

### Drawer

A right-side panel (full screen below 640px). It reuses `Modal`'s focus trap,
Escape handling and focus restoration, and opens with a 200ms slide that is
disabled under reduced motion. Used for detail views, forecast run history and
import-row errors.

### Section

A heading, an optional description and actions, then content, separated by
spacing and a hairline divider instead of a card. This keeps pages from
wrapping every block in its own card.

## 3. Screen migration by workflow group

Each group moves its screens onto the kit and fixes the UX problems found in
those screens. The layout follows each workflow's purpose:

| # | Group | Screens | Layout intent |
|---|---|---|---|
| 1 | Sales | SalesAnalytics, LiveSales | The trend chart anchors the page, with `SegmentedControl` granularity (day/week/month, the values the API accepts). Rankings and location tables use `DataTable`. Clicking a chart bucket shows that bucket's recorded figures, including the transaction count, in the shared tooltip or panel. There is no transaction-list drawer, because `api/salesAnalytics.ts` exposes counts, not line items. |
| 2 | Forecasts | Forecasts, HybridForecasts (restored, see below) | The forecast chart anchors the page. Run history and run status move to a `Drawer`. Tables use `DataTable` with sorting. Confidence text stays nominal ("model interval", not measured accuracy). |
| 3 | Catalog and stock | Inventory, Products, Skus, ProductDetail, SkuDetail | A toolbar with `FilterBar`, then a dense `DataTable`. Products and SKUs already have bulk actions, which use `selection`. Detail pages use `Section`s rather than stacked cards. |
| 4 | Decisions | Decisions, ShortageAlerts, FinancialImpact, ROIDashboard, TrendAnalysis | The evidence leads to the action. Every number is a `MetricTile` with provenance. Comparisons use one `ChartFrame`. |
| 5 | Data | DataQuality, SmartImport / ImportUploader / ImportModal | The outcome summary (imported, rejected, why) comes first, then the rows to review. Row errors open in a `Drawer`. Mapping and correction appear only where the backend supports them today. |
| 6 | Admin | Integrations, Webhooks, Settings, Profile, Billing, Notifications | Aligned forms. Connection status uses text plus an icon. Destructive actions stay behind `ConfirmDialog`. |
| 7 | Entry and industry | Login, ForgotPassword, ResetPassword, AcceptInvite, Onboarding steps, Legal, NotFound, LandingPage, 5 industry dashboards, PharmaBatches | Industry dashboards and PharmaBatches adopt the kit while keeping each industry's terminology and features. Auth and onboarding get form and stepper consistency. The landing page receives only a consistency pass. |

**Unrouted page modules (user decision, 2026-10-29).** Four page modules were
not imported by `App.tsx` or by anything else. `/workspace/forecasts/hybrid`
redirected to `/workspace/forecasts` because of commit `cd83f2f`.

- **Hybrid Forecasts is restored.** `/workspace/forecasts/hybrid` renders
  `HybridForecastsPage` instead of redirecting. The sidebar's **Plan** group
  gets a "Hybrid Forecasts" entry directly after "Forecasts". The navigation
  finder picks it up from the same nav list, and its icon comes from
  `icons.tsx`. The Forecasts page's existing sentence about trend adjustment
  happening "only in Hybrid forecasts" becomes a link to the restored page.
  The page joins group 2 and is redesigned with the kit:
  - The run controls (horizon, start) sit in a `FilterBar`.
  - The live run stage reads from the existing WebSocket stages, as a progress
    indicator with its text label. The existing 40s stale-queue warning stays.
  - The pessimistic, base and optimistic scenarios render in one `ChartFrame`
    (`ScenarioBands`) and as `MetricTile`s with provenance `"forecast"`.
  - The trend panel and explanations become `Section`s.
  - The API contract (`api/hybridForecast.ts`) is unchanged.
- **WhatIfScenario, Signals and ForecastAccuracy are removed**, along with the
  modules only they use. They stay recoverable from git history. Removed:
  `pages/WhatIfScenario.tsx`, `pages/WhatIfScenario.test.tsx`,
  `api/scenarios.ts`, `pages/Signals.tsx`, `api/signals.ts`,
  `components/signals/EconomicIndicators.tsx`,
  `components/signals/SocialBuzz.tsx`, `pages/ForecastAccuracy.tsx`,
  `pages/ForecastAccuracy.test.tsx`, `pages/forecastAccuracyRules.ts` and
  `api/forecastAccuracy.ts`. The matching backend routers stay, because this
  pass makes no backend changes. `components/ai/ScenarioAssistant.tsx` is kept,
  because `components/ai/Interactive.test.tsx` still covers it. Harness entries
  and audit captures for the removed screens are dropped.

The shell (`AppShell`, `Sidebar`, `TopBar`) was reworked in pass 1. In pass 2
it adopts the motion and focus utilities only; its structure stays.

## 4. Data honesty

- Provenance on every `MetricTile`.
- Chart legends distinguish recorded from expected. The P10–P90 band is
  labelled "model interval".
- Summed SKU quantiles keep their existing "not a calibrated portfolio
  quantile" explanation.
- No delta, trend arrow or percentage is shown unless the API supplies it or it
  is computed from two real values.

## 5. Testing and verification

- **Harness first:** fix `e2e/review.html` so every screen mounts inside a
  workspace context from `e2e/planning-fixture.ts`, which is visibly labelled
  as a fixture. Production code never imports it.
- **TDD per kit component** (Vitest + RTL): write the failing test first, for
  sort order and `aria-sort`, nulls sorting last, mobile cards, skeleton rows,
  "—" plus reason for unavailable metrics, a provenance label on every tile,
  `Tabs` and `SegmentedControl` keyboard paths, `Drawer` focus trap and
  restore, and `ChartTooltip` value order.
- **Per group:** existing page tests stay green without weakening their
  assertions. Harness captures in light and dark at 390, 768, 1280 and
  1672px go into `docs/audit/2026-10-29-premium-minimal-pass-2/`, plus a check
  that the page does not scroll horizontally at any of those widths.
- **End of pass:** `npm run typecheck`, `npm run lint` (no new errors against
  the pass-1 baseline), `npm test`, `npm run build` with the main chunk size
  recorded and compared, and the Playwright design specs (`premium-minimal`,
  `sales-analytics-design`).
- **Not verified by this pass:** live checkout, OAuth connections, message
  delivery and destructive operations against real customer data.

## 6. Delivery

- One commit per kit component and one per screen group, on
  `design/premium-minimal-pass-2`. Unrelated backend changes stay uncommitted.
- `DESIGN.md` gains a short "Components" section that names the kit and when to
  use each piece.
- The final report lists the screens migrated, the components created, the
  files changed, the test and build output, and any screen or workflow that
  was not verified.

## Out of scope

Backend changes, new features, palette changes, a new icon library, and
restructuring the shell. The only navigation changes are restoring Hybrid
Forecasts and removing the three unrouted modules, both by user decision.

Hybrid Forecasts restoration is tested first: a Sidebar test asserts the entry
and its order, a route test asserts that `/workspace/forecasts/hybrid` renders
the page rather than redirecting, and the existing `HybridForecasts.test.tsx`
stays green.
