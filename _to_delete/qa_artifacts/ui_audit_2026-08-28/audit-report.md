# Sanket product UI/UX audit — 28 August 2026

## Audit scope

Desktop review of the live Fashion sandbox at its default browser viewport. The sampled flow covers Dashboard, Products, Inventory, Forecasts, Hybrid Forecasts, Decisions, Scenario Simulator, Data Quality, WhatsApp Digest, Integrations, and Dashboard dark mode.

## Overall verdict

Sanket does not mainly have an “image problem.” It has a product-hierarchy problem. The application contains strong decision intelligence, but most screens lead with configuration, definitions, or generic KPI cards. The clearest product promise—what changed, what needs action, why, and what it is worth—is strongest on Decisions and weak on the Dashboard.

The light palette is recognisable but over-applied: the saturated pale-teal canvas occupies most of every page, making white cards feel repetitive. Dark mode has insufficient tonal separation and low-contrast subtle text. The current dark subtle-text token measures approximately 2.98:1 against its card background.

## Captured steps

1. **Dashboard — Needs redesign.** Attractive and coherent, but it is an industry trend dashboard rather than an operating command centre. It does not foreground open decisions, shortage risk, forecast confidence, data freshness, or money at stake. The trend callout has no next action.
2. **Products — Needs asset correction.** Product cards are usable, but every unrelated product receives the same fashion mannequin fallback. This makes the catalogue feel synthetic. Use distinct real product images where available; otherwise use a restrained category fallback rather than a misleading photograph.
3. **Inventory — Structurally sound, weak decision context.** The table is clear, but it reports all rows as healthy while Decisions says some SKUs have only 4–7 days of cover. Add forecast-aware status, days of cover, next arrival, and recommended action. Small product thumbnails can aid recognition; large imagery would reduce useful density.
4. **Forecasts — Too much setup above the result.** Configuration and P10/P50/P90 education dominate the first viewport. Default to the latest successful run and put configuration in a compact drawer or secondary panel. Keep explanations close to each chart and decision.
5. **Hybrid Forecasts — Duplicates Forecasts.** The large explanation panel repeats concepts already taught elsewhere and pushes the forecast below the fold. Merge Forecasts and Hybrid Forecasts into one Forecast workspace with Baseline/Signal-adjusted modes.
6. **Decisions — Strongest screen.** This is the visual and product north star: urgency, reason, financial impact, and action are visible together. Improve sorting/bulk review, clarify “Alerting,” and label the icon-only dismiss action.
7. **Scenario Simulator — Good controls, inert first impression.** The empty output panel is too large. Preserve the last simulation, preselect a recommended scenario, or show a baseline state so the right side communicates value before the first run.
8. **Data Quality — Clear, but oversized summary.** The issue cards explain cause and remedy well. Compress the wide metric area and provide direct remediation actions such as “Review 8 rows” or “Reconnect inventory source.”
9. **WhatsApp Digest — Strong supporting surface.** The dark message preview adds useful contrast and makes the outcome tangible. This is a good example of showing the product artifact instead of explaining the feature.
10. **Integrations — Good grouping, weak brand recognition.** Use official connector logos and show Connected/Needs attention first. Add search and category filters before presenting the full 42-source catalogue.
11. **Dashboard dark mode — Needs correction.** Nearly every surface stays in the same teal family. Labels, borders, and cards lose separation; subtle text is below the normal-text contrast target.

## Highest-impact redesign

### 1. Turn Dashboard into “Today’s planning brief”

The first viewport should answer five questions:

1. What changed?
2. What needs my decision?
3. Why?
4. What is it worth?
5. Can I trust the data and forecast?

Recommended structure:

- Top command strip: orders due, revenue protected, stockouts approaching, forecast confidence, data-quality warnings.
- Main left column: ranked decision queue with reason, days of cover, value, Accept/Review action.
- Main right column: trust panel for forecast confidence, data freshness, integrations, and WhatsApp delivery.
- Secondary row: actual versus forecast chart with confidence band and ranked drivers.
- Lower row: inventory risk by category/location and recent operational activity.

### 2. Reduce the teal surface area

- Keep deep teal for navigation and primary actions.
- Change the light canvas from `#BDD9D7` to a near-neutral cool background around `#F3F7F6`.
- Reserve seafoam for selected states, AI insight panels, and confidence bands—roughly 5–10% of the page, not the entire canvas.
- Add a small industry accent: fashion rose, electronics blue, pharma cyan, hardware amber, agro green. Do not recolour the whole application per industry.
- For dark mode, use neutral dark layers with clearer elevation, then keep teal as an accent. Raise subtle text to at least 4.5:1 for normal-size labels.

### 3. Simplify the information architecture

The sidebar contains more destinations than fit in a normal 720px-high laptop viewport; most Intelligence, Decisions, and Analytics destinations are hidden inside an independently scrolling area.

Suggested top-level model:

- Overview
- Plan — forecasts, trends, scenarios
- Act — decisions, alerts
- Stock — products, SKUs, inventory
- Measure — ROI, accuracy, sales
- Data — integrations, signals, quality

Use collapsible groups, badges for pending decisions/alerts, and a command search. Remove the visible `build unknown` stamp from normal users and hide the query-devtools launcher in the sandbox.

### 4. Use imagery only when it improves recognition

- Products: yes—distinct product photos or honest category fallbacks.
- Inventory: small thumbnail beside product/SKU, optional; do not add a large inventory hero image.
- Integrations: official connector logos.
- Dashboard/Forecasts/Decisions: prefer data, status, and operational visuals over decorative photography.

## Accessibility risks visible in this audit

- Dark-mode subtle text is approximately 2.98:1 against the dark surface, below the normal-text target.
- Products includes unnamed icon-only view controls in the accessibility tree.
- Decisions uses an icon-only dismiss action without a visible or announced name.
- The long independently scrolling sidebar reduces discoverability at common laptop heights.
- Screenshots cannot confirm full keyboard traversal, focus visibility, zoom reflow, screen-reader announcements, or chart tooltip accessibility; those require interaction testing.

## Capture files

- `01-dashboard.png`
- `02-products.png`
- `03-inventory.png`
- `04-forecasts.png`
- `05-hybrid-forecasts.png`
- `06-decisions.png`
- `07-scenarios.png`
- `08-data-quality.png`
- `09-whatsapp-digest.png`
- `10-integrations.png`
- `11-dashboard-dark.png`
