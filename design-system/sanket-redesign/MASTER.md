# Sanket Redesign — Source of Truth

## Product job

Sanket is an action-first planning workspace. Every primary screen should answer, in order:

1. What changed?
2. Why did it change?
3. What should the planner do?
4. What is the operational or financial consequence?

The approved dashboard mockup is the visual source of truth:
`C:\Users\admin\.codex\generated_images\01a0444f-5a78-7eb2-a14d-4a690ff75c9c\exec-d1762105-d954-4334-a9e6-5ca8be63ded9.png`.

## Brand locks

- Primary identity: Blue Whale deep teal `#03363D`.
- Light canvas: neutral cool `#F3F7F6`; pale mint is a local insight tint, not the page background.
- Dark canvas: near-black blue-green `#071B1D`; surfaces step through `#0B2528` and `#103136`.
- Type: Space Grotesk for headings, IBM Plex Sans for UI/body, IBM Plex Mono for figures and IDs.
- Semantic colors: emerald = positive, amber = attention/uncertainty, rose = risk, cyan = informational comparison.
- No gradients, glow, glassmorphism, ornamental 3D, or repeated decorative pills in the product workspace.

## Layout and hierarchy

- Desktop workspace target: 1280–1440px wide with an action-first asymmetric grid.
- Exactly one primary focal anchor per page.
- Group with spacing and alignment first, row dividers second, borders third, shadows last.
- Do not put every section or row in its own card.
- Base body copy is 14–16px with at least 1.45 line-height.
- Persistent interactive targets are at least 40px desktop and 44px touch layouts.

## Forecast chart standard

- Actual/history: solid deep-teal or high-contrast neutral line, 2px.
- Expected forecast: dashed accent line, 2px.
- Expected range: one flat fill at 10–14% opacity; no gradient and no visible P10/P90 boundary lines.
- Keep grids sparse and horizontal only. Use a visible history/forecast divider when both exist.
- Legends use plain language: `Actual`, `Expected`, `Expected range`.
- Tooltips show date, actual/expected units, and lower/upper range in that order.
- Never rely on color alone: solid vs dashed lines and text labels are required.

## Navigation

- Plan: Dashboard, Decisions, Forecasts, Scenarios.
- Stock: Products, SKUs, Inventory, Shortage Alerts.
- Measure: Trends, Sales Analytics, ROI, Forecast Accuracy.
- Data: External Signals, Data Quality, Integrations, WhatsApp Digest.
- Secondary and specialist routes remain deep-linkable without competing in primary navigation.

## Product imagery

- Fashion images use one consistent editorial ecommerce studio setup.
- Every visible product category and important color variant receives a distinct asset.
- Product cards may use large imagery; SKU and inventory surfaces use compact thumbnails only when they aid identification.
- User-uploaded images always override generated defaults.

## Accessibility and motion

- WCAG AA contrast minimum for standard text in both themes.
- Visible focus rings, semantic headings, keyboard-operable controls, and descriptive image alt text.
- Motion is functional, 150–300ms, and disabled under `prefers-reduced-motion`.

## Skill-informed decisions

- Product Design: selected visual target is implemented before further stylistic invention.
- UI/UX Pro Max: data-dense dashboard structure, progressive disclosure, accessible line-with-confidence-band charts.
- Composition Director: one primary focal anchor; no equal-emphasis KPI wall.
- Typography Director: locked type roles, readable measures, semantic line breaks.
- Brand Intelligence: preserve Sanket logo geometry and deep-teal identity; use sourced connector marks rather than approximations.
- Visual QA: compare source and implementation at the same viewport before handoff.

