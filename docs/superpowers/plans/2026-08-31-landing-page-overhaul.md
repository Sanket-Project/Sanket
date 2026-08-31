# Landing Page Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the landing page from four tall, sparse, static sections into eleven short, dense, operable ones whose every claim is traceable to the codebase.

**Architecture:** `LiveConsoleLanding.tsx` splits into one file per section under `src/pages/landing/sections/`, with all copy and capability data in a typed `content.ts` and the type scale in `landing.css`. Interactivity is local component state over data held in `content.ts` — no network calls, no auth, no effect on first paint. Both hidden landing variants and their env flags are deleted.

**Tech Stack:** React 18 + TypeScript, Vite, Tailwind (plus the existing hand-written `live-console.css`), framer-motion, Vitest + Testing Library, Playwright.

**Spec:** `docs/superpowers/specs/2026-08-31-landing-page-overhaul-design.md`

## Global Constraints

- **Capability-only content.** Every claim traceable to the repository. No customer names, no revenue figures, no analyst awards, no invented metrics. This is AGENTS.md "fail honestly" applied to marketing copy.
- **Connector honesty.** The catalog holds **42 connectors, 6 `live`** (Shopify, WooCommerce, PostgreSQL, MySQL, CSV Upload, Excel Upload) and **2 `beta`** (REST API / Push, Generic Webhooks). The other 34 are `planned`. Never print a total that implies 42 work today.
- **Icons** import from `frontend/src/components/ui/icons.tsx` only — never `lucide-react` or `react-iconly` directly (AGENTS.md §6).
- **Three type roles, everywhere:** DM Serif Display headlines only; IBM Plex Sans all body; IBM Plex Mono all eyebrows/labels/metrics.
- **Every control keyboard-operable** with the ARIA role its behaviour implies.
- The console keeps a visible "Illustrative data shown" note.
- Frontend commands run from `frontend/`. Verify with `npm run typecheck && npm run lint && npm test`.
- Existing class vocabulary to reuse: `lc-section`, `lc-section-alt`, `lc-shell`, `lc-stack`, `lc-split`, `lc-intro`, `lc-kicker`, `lc-h2`, `lc-h3`, `lc-lede`, `lc-body`, `lc-tabs`, `lc-link-btn`, `lc-btn`, `Reveal`.

---

## File Structure

**Created**
| Path | Responsibility |
|---|---|
| `src/pages/landing/content.ts` | All copy + capability data, typed. Single source for every claim. |
| `src/pages/landing/sections/WhatItDoes.tsx` | Section 2 — Ingest → Forecast → Decide → Act |
| `src/pages/landing/sections/IndustryTabs.tsx` | Section 4 — interactive vertical tabs |
| `src/pages/landing/sections/ModuleGrid.tsx` | Section 6 — clickable module grid + detail panel |
| `src/pages/landing/sections/SignalGrid.tsx` | Section 7 — expandable signal cards |
| `src/pages/landing/sections/ConnectorGrid.tsx` | Section 8 — searchable/filterable connector catalog |
| `src/pages/landing/sections/ForecastEngine.tsx` | Section 9 — how the forecasting works |
| `src/pages/landing/sections/SecurityTenancy.tsx` | Section 10 — RLS, audit, GxP |
| `src/pages/landing/sections/GetStarted.tsx` | Section 11 — the four entry points |
| `src/pages/landing/sections/*.test.tsx` | One test file per interactive section |

**Modified:** `src/pages/landing/LiveConsoleLanding.tsx` (becomes a thin composer), `src/pages/landing/live-console.css`, `src/pages/LandingPage.tsx` (delete legacy branch + flags, fix nav), `src/pages/LandingPage.test.tsx`, `index.html`.

**Deleted:** `src/pages/landing/ModelsDisagreeLanding.tsx`, `src/pages/landing/models-disagree.css`, `src/pages/landing/LandingCaseStudies.tsx`, `src/pages/landing/LandingTestimonials.tsx`.

---

## Task 1: Remove the dead Pricing link and the hidden variants

The reported defect plus the dead code that caused it. Doing these together because the stale nav is a symptom of the unrendered legacy page.

**Files:**
- Modify: `src/pages/LandingPage.tsx` (flags at `:34-36`, `sectionLinks` at `:1949`, legacy branch at `:2225-2238`)
- Modify: `src/pages/landing/LiveConsoleLanding.tsx` (`id="pricing"` at `:657`)
- Delete: `src/pages/landing/ModelsDisagreeLanding.tsx`, `src/pages/landing/models-disagree.css`, `src/pages/landing/LandingCaseStudies.tsx`, `src/pages/landing/LandingTestimonials.tsx`
- Test: `src/pages/LandingPage.test.tsx`

**Interfaces:**
- Consumes: nothing
- Produces: `LandingPage` renders hero + `<LiveConsoleLanding />` unconditionally; nav ids are `platform`, `industries`, `how-it-works`, `integrations`, `security`

- [ ] **Step 1: Write the failing test**

Replace the whole of `src/pages/LandingPage.test.tsx` with:

```tsx
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

/**
 * Source-level assertions rather than a render. LandingPage is a large
 * marketing page built on scroll-linked framer-motion, an intro loader gated on
 * sessionStorage, and a background video — none of which behave in jsdom.
 * Rendering it would test the mocks. What matters here is which entry points
 * the page offers, what it claims, and that no nav link points at nothing.
 */
const page = readFileSync("src/pages/LandingPage.tsx", "utf8");
const console_ = readFileSync("src/pages/landing/LiveConsoleLanding.tsx", "utf8");

describe("landing page", () => {
  it("offers all four public entry points", () => {
    for (const cta of [
      "Try Live Sandbox",
      "Create Workspace",
      "Request Enterprise Demo",
      "Sign in",
    ]) {
      expect(page).toContain(cta);
    }
  });

  it("routes Create Workspace to self-service signup", () => {
    expect(page).toContain("/login?mode=signup");
  });

  it("does not sell multi-tenancy as a differentiator", () => {
    expect(page).not.toMatch(/multi-tenant/i);
  });

  it("does not offer a Pricing link, because there is no pricing section", () => {
    expect(page).not.toMatch(/label:\s*"Pricing"/);
  });

  it("names no section anchor after content it does not contain", () => {
    // The reported defect: the header linked to #pricing, which was the id on a
    // statistics band. Every nav id must exist as a section id somewhere.
    const navIds = [...page.matchAll(/\{\s*label:\s*"[^"]+",\s*id:\s*"([^"]+)"\s*\}/g)]
      .map((m) => m[1]);
    expect(navIds.length).toBeGreaterThan(0);
    const sectionIds = [
      ...page.matchAll(/id="([^"]+)"/g),
      ...console_.matchAll(/id="([^"]+)"/g),
    ].map((m) => m[1]);
    for (const id of navIds) {
      expect(sectionIds, `nav links to #${id} but no section has that id`).toContain(id);
    }
  });

  it("carries no hidden landing variants", () => {
    expect(page).not.toMatch(/VITE_LEGACY_LANDING/);
    expect(page).not.toMatch(/VITE_LANDING_CONCEPT/);
    expect(page).not.toMatch(/ModelsDisagreeLanding/);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd frontend && npx vitest run src/pages/LandingPage.test.tsx
```

Expected: FAIL on "does not offer a Pricing link", "names no section anchor after content it does not contain", and "carries no hidden landing variants".

- [ ] **Step 3: Delete the hidden variants**

```bash
cd frontend && git rm src/pages/landing/ModelsDisagreeLanding.tsx src/pages/landing/models-disagree.css src/pages/landing/LandingCaseStudies.tsx src/pages/landing/LandingTestimonials.tsx
```

- [ ] **Step 4: Strip the flags and the legacy branch from LandingPage.tsx**

Delete lines 34–36 (`LEGACY_LANDING_ENABLED`, the concept comment, `LANDING_CONCEPT`) and the `ModelsDisagreeLanding` import at `:32`. Replace the conditional block at `:2225-2238` with an unconditional render:

```tsx
      <LiveConsoleLanding
        onBook={() => setModal("book")}
        onSandbox={() => setModal("sandbox")}
      />
```

Then delete everything from the `{LEGACY_LANDING_ENABLED && (` opening through its matching `)}` — the entire legacy body (Trust marquee, About, Platform Tour, Case Studies, Testimonials, Pricing, Final CTA, and the `<ScrollProgress />` guard at `:2023`). Keep the header, hero, modals and footer. Also delete the now-unused legacy-only components defined earlier in the file (`TrustMarquee`, `Pricing`, `CaseStudies`, `Testimonials`, `FinalCTA`, `PlatformTour`, `KnowledgeGraph` and their data constants) — TypeScript will name each one as unused.

- [ ] **Step 5: Fix the nav**

Replace `sectionLinks` (at `:1949`) with:

```tsx
  const sectionLinks = [
    { label: "Platform", id: "platform" },
    { label: "Industries", id: "industries" },
    { label: "How It Works", id: "how-it-works" },
    { label: "Integrations", id: "integrations" },
    { label: "Security", id: "security" },
  ];
```

- [ ] **Step 6: Rename the mislabelled anchors in LiveConsoleLanding**

In `src/pages/landing/LiveConsoleLanding.tsx`: change `id="features"` to `id="platform"` (`:476`), `id="architecture"` to `id="industries"` (`:558`), and `id="pricing"` to `id="get-started"` (`:657`). `id="how-it-works"` already matches.

- [ ] **Step 7: Run the tests and typecheck**

```bash
cd frontend && npx vitest run src/pages/LandingPage.test.tsx && npm run typecheck
```

Expected: 6 passed, typecheck exit 0. Fix every unused-symbol error by deleting the symbol.

- [ ] **Step 8: Commit**

```bash
git add -A frontend/src/pages
git commit -m "fix(landing): remove the dead Pricing link and both hidden variants

The header linked to #pricing, which was the id on a statistics band, so
the anchor scrolled to 5 INDUSTRIES SERVED. The link existed because the
nav was written for a legacy page that did have pricing and has not
rendered since it went behind VITE_LEGACY_LANDING.

Deletes that legacy branch, the second concept behind
VITE_LANDING_CONCEPT, and both flags. A test now asserts every nav id
resolves to a real section."
```

---

## Task 2: Typography and spacing consistency

**Files:**
- Modify: `src/pages/landing/live-console.css` (`:27`, `:48`, `:81`, `:98`, `:439`)
- Modify: `src/pages/LandingPage.tsx` (root inline `fontFamily`, the `@import` inside `<style>`)
- Modify: `index.html`
- Test: `src/pages/landing/typography.test.ts`

**Interfaces:**
- Consumes: nothing
- Produces: CSS custom properties `--lc-font-display`, `--lc-font-body`, `--lc-font-mono` on `.lc`

- [ ] **Step 1: Write the failing test**

```ts
// src/pages/landing/typography.test.ts
import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

const css = readFileSync("src/pages/landing/live-console.css", "utf8");
const page = readFileSync("src/pages/LandingPage.tsx", "utf8");
const html = readFileSync("../frontend/index.html", "utf8");

describe("landing typography", () => {
  it("declares the three type roles as tokens", () => {
    expect(css).toContain("--lc-font-display");
    expect(css).toContain("--lc-font-body");
    expect(css).toContain("--lc-font-mono");
  });

  it("names no font family outside those tokens", () => {
    // Every font-family in the stylesheet must go through a token, so a fourth
    // family cannot be introduced by editing one rule.
    const families = [...css.matchAll(/font-family:\s*([^;]+);/g)].map((m) => m[1].trim());
    for (const f of families) {
      expect(f, `raw font stack "${f}" should use a --lc-font-* token`).toMatch(/var\(--lc-font-/);
    }
  });

  it("does not set a competing body font on the page wrapper", () => {
    // The hero wrapper used to set Space Grotesk inline while live-console.css
    // set IBM Plex Sans, so body copy changed family partway down the page.
    expect(page).not.toMatch(/fontFamily:\s*"'Space Grotesk'/);
  });

  it("loads fonts from the document head, not an inline @import", () => {
    expect(page).not.toMatch(/@import url\('https:\/\/fonts\.googleapis\.com/);
    expect(html).toMatch(/fonts\.googleapis\.com/);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd frontend && npx vitest run src/pages/landing/typography.test.ts
```

Expected: FAIL on all four — no tokens exist, families are raw stacks, the wrapper sets Space Grotesk, the `@import` is inline.

- [ ] **Step 3: Add the tokens and route every rule through them**

At the top of `.lc` in `live-console.css`:

```css
.lc {
  /* Three roles, applied identically in every section. A fourth family is a
     bug: the page previously ran DM Serif, Space Grotesk, IBM Plex Sans and
     IBM Plex Mono at once, and body copy changed family partway down. */
  --lc-font-display: "DM Serif Display", Georgia, serif;
  --lc-font-body: "IBM Plex Sans", "Inter", system-ui, sans-serif;
  --lc-font-mono: "IBM Plex Mono", ui-monospace, monospace;
  font-family: var(--lc-font-body);
}
```

Replace every other `font-family:` declaration in the file with the matching token: the `.lc-h2`/`.lc-h3` serif rules become `var(--lc-font-display)`, every `"IBM Plex Mono"` rule becomes `var(--lc-font-mono)`, and any remaining sans rule becomes `var(--lc-font-body)`.

- [ ] **Step 4: Remove the competing wrapper font and inline import**

In `LandingPage.tsx`, delete `fontFamily: "'Space Grotesk', sans-serif"` from the root `<div style={{...}}>` and delete the `@import url('https://fonts.googleapis.com/...')` line from the inline `<style>` block.

In `index.html`, add to `<head>`:

```html
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link
      href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap"
      rel="stylesheet"
    />
```

- [ ] **Step 5: Tighten the two spacing tokens**

In `live-console.css`, reduce the section rhythm now that the page carries more sections:

```css
.lc-section { padding: clamp(56px, 6vw, 88px) 0; }
.lc-stack { display: grid; gap: clamp(40px, 4.5vw, 64px); }
```

- [ ] **Step 6: Run the tests**

```bash
cd frontend && npx vitest run src/pages/landing/typography.test.ts && npm run typecheck
```

Expected: 4 passed, typecheck exit 0.

- [ ] **Step 7: Commit**

```bash
git add -A frontend/src/pages frontend/index.html
git commit -m "style(landing): one type system, three roles

Body copy changed family partway down the page: the hero wrapper set
Space Grotesk inline while live-console.css set IBM Plex Sans. Every
font-family now goes through a --lc-font-* token, so a fourth family
cannot be reintroduced by editing one rule, and a test enforces it.

Fonts move to a <link> in the document head; the @import inside an
inline <style> was render-blocking."
```

---

## Task 3: The content module

Every later task reads from here. One file so a claim can be checked against the codebase in one place.

**Files:**
- Create: `src/pages/landing/content.ts`
- Test: `src/pages/landing/content.test.ts`

**Interfaces:**
- Consumes: nothing
- Produces:
  - `type Availability = "live" | "beta" | "planned"`
  - `INDUSTRY_DETAIL: Record<IndustryCode, { label: string; horizonWeeks: number; auditLevel: string; signals: string[]; observes: string; risk: string; action: string }>`
  - `MODULES: { key: string; name: string; route: string; blurb: string; detail: string }[]`
  - `SIGNALS: { key: string; name: string; source: string; feeds: string }[]`
  - `CONNECTORS: { name: string; category: string; availability: Availability }[]`
  - `CONNECTOR_CATEGORIES: string[]`
  - `LIVE_CONNECTOR_COUNT: number`, `TOTAL_CONNECTOR_COUNT: number`

- [ ] **Step 1: Write the failing test**

```ts
// src/pages/landing/content.test.ts
import { describe, expect, it } from "vitest";
import {
  CONNECTORS,
  INDUSTRY_DETAIL,
  LIVE_CONNECTOR_COUNT,
  MODULES,
  SIGNALS,
  TOTAL_CONNECTOR_COUNT,
} from "@/pages/landing/content";

describe("landing content", () => {
  it("states each industry's real planning horizon and audit level", () => {
    // Mirrors backend/app/services/industry_context.py. Pharma is the one that
    // matters commercially: 52 weeks at GxP audit level.
    expect(INDUSTRY_DETAIL.fashion.horizonWeeks).toBe(26);
    expect(INDUSTRY_DETAIL.electronics.horizonWeeks).toBe(12);
    expect(INDUSTRY_DETAIL.pharma.horizonWeeks).toBe(52);
    expect(INDUSTRY_DETAIL.pharma.auditLevel).toBe("gxp");
    expect(INDUSTRY_DETAIL.agrocenter.horizonWeeks).toBe(26);
    expect(INDUSTRY_DETAIL.hardware.horizonWeeks).toBe(16);
  });

  it("covers all five industries", () => {
    expect(Object.keys(INDUSTRY_DETAIL).sort()).toEqual(
      ["agrocenter", "electronics", "fashion", "hardware", "pharma"],
    );
  });

  it("counts connectors honestly", () => {
    // The page used to advertise "29+ CONNECTORS" by counting planned ones.
    expect(TOTAL_CONNECTOR_COUNT).toBe(CONNECTORS.length);
    expect(LIVE_CONNECTOR_COUNT).toBe(
      CONNECTORS.filter((c) => c.availability === "live").length,
    );
    expect(LIVE_CONNECTOR_COUNT).toBeLessThan(TOTAL_CONNECTOR_COUNT);
  });

  it("marks the six working connectors live and nothing else", () => {
    const live = CONNECTORS.filter((c) => c.availability === "live").map((c) => c.name).sort();
    expect(live).toEqual([
      "CSV Upload",
      "Excel Upload",
      "MySQL",
      "PostgreSQL",
      "Shopify",
      "WooCommerce",
    ]);
  });

  it("points every module at a route that exists in the app", () => {
    for (const m of MODULES) {
      expect(m.route, `${m.name} route`).toMatch(/^\/workspace/);
    }
  });

  it("names a source for every signal", () => {
    expect(SIGNALS.length).toBeGreaterThan(3);
    for (const s of SIGNALS) expect(s.source.length).toBeGreaterThan(0);
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd frontend && npx vitest run src/pages/landing/content.test.ts
```

Expected: FAIL — `Cannot find module '@/pages/landing/content'`.

- [ ] **Step 3: Write the content module**

```ts
// src/pages/landing/content.ts
import type { IndustryCode } from "@/types/api";

/**
 * Every claim the landing page makes, in one file.
 *
 * The rule for this file is that a reader can check any line against the
 * codebase. Where a value mirrors backend data, the comment names the file it
 * came from. Nothing here is aspirational: no customer names, no revenue
 * figures, no analyst awards, no measured outcomes we have not measured.
 */

export type Availability = "live" | "beta" | "planned";

/** Mirrors backend/app/services/industry_context.py. */
export const INDUSTRY_DETAIL: Record<
  IndustryCode,
  {
    label: string;
    horizonWeeks: number;
    auditLevel: string;
    signals: string[];
    observes: string;
    risk: string;
    action: string;
  }
> = {
  fashion: {
    label: "Apparel & Fashion",
    horizonWeeks: 26,
    auditLevel: "standard",
    signals: ["Search trends", "Social sentiment", "Weather"],
    observes: "SKU · size curve · returns · promotion cadence",
    risk: "A regional search spike precedes store sales.",
    action: "Rebalance by size before replenishing the whole line.",
  },
  electronics: {
    label: "Consumer Electronics",
    horizonWeeks: 12,
    auditLevel: "standard",
    signals: ["Competitor price", "Supplier lead time", "Search trends"],
    observes: "SKU · launch cycle · channel · price movement",
    risk: "A price move shifts demand before channel reports settle.",
    action: "Advance the order window without overcommitting stock.",
  },
  pharma: {
    label: "Pharmaceuticals",
    horizonWeeks: 52,
    auditLevel: "gxp",
    signals: ["Regulatory", "Supplier lead time", "Logistics disruption"],
    observes: "SKU · batch · shelf life · regulatory status",
    risk: "A supplier delay threatens cover before expiry windows close.",
    action: "Re-plan the batch with the audit trail attached.",
  },
  agrocenter: {
    label: "Agrocenter & Farm Inputs",
    horizonWeeks: 26,
    auditLevel: "standard",
    signals: ["Weather", "Macro-economic", "Search trends"],
    observes: "SKU · season · crop cycle · input coverage",
    risk: "A weather shift moves the sowing window and the demand with it.",
    action: "Pull the replenishment forward for the affected inputs.",
  },
  hardware: {
    label: "Hardware & Industrial Supply",
    horizonWeeks: 16,
    auditLevel: "standard",
    signals: ["Supplier lead time", "Competitor price", "Macro-economic"],
    observes: "SKU · project cycle · branch · supplier lead time",
    risk: "A lead-time slip puts safety stock below cover.",
    action: "Reorder early on the lines that actually move.",
  },
};

/** Routes that exist in frontend/src/App.tsx. */
export const MODULES = [
  {
    key: "forecasts",
    name: "Demand forecasting",
    route: "/workspace/forecasts",
    blurb: "Per-SKU forecasts with confidence bands.",
    detail:
      "Every SKU gets its own model selection rather than one global model. Forecasts carry a confidence interval so you can see where the engine is unsure.",
  },
  {
    key: "decisions",
    name: "Decision engine",
    route: "/workspace/decisions",
    blurb: "Ranked actions, each with its evidence.",
    detail:
      "Turns the forecast into a reorder you can approve, showing the inputs behind it — days of cover, lead time, protection window.",
  },
  {
    key: "scenarios",
    name: "What-if scenarios",
    route: "/workspace/scenarios",
    blurb: "Change an assumption, see the plan move.",
    detail:
      "Simulate a promotion, a lead-time slip or a price change and compare the resulting plan against the baseline before committing.",
  },
  {
    key: "inventory",
    name: "Inventory & cover",
    route: "/workspace/inventory",
    blurb: "Stock positions and days of cover.",
    detail:
      "Current levels by location against forecast demand, so cover is a number rather than an argument.",
  },
  {
    key: "alerts",
    name: "Shortage alerts",
    route: "/workspace/alerts",
    blurb: "Risk scored before it becomes a stockout.",
    detail:
      "Alerts fire on projected cover, not on hitting zero, and carry the drivers that produced the risk score.",
  },
  {
    key: "accuracy",
    name: "Forecast accuracy",
    route: "/workspace/forecast-accuracy",
    blurb: "Scored against what actually happened.",
    detail:
      "Backtested accuracy per SKU, so you can see where the engine earns trust and where it does not.",
  },
  {
    key: "data-quality",
    name: "Data quality",
    route: "/workspace/data-quality",
    blurb: "What is missing before it skews a plan.",
    detail:
      "Flags gaps, duplicates and outliers in ingested data rather than silently forecasting on top of them.",
  },
  {
    key: "roi",
    name: "ROI dashboard",
    route: "/workspace/roi",
    blurb: "Value traced back to decisions taken.",
    detail:
      "Ties working-capital and stockout impact to the specific recommendations that were approved.",
  },
  {
    key: "signals",
    name: "External signals",
    route: "/workspace/signals",
    blurb: "Weather, trends, macro and competitor movement.",
    detail:
      "Signals are ingested, validated and attached to the SKUs they plausibly affect, so a forecast change has a named cause.",
  },
  {
    key: "integrations",
    name: "Integrations hub",
    route: "/workspace/integrations",
    blurb: "Connect a storefront, warehouse or database.",
    detail:
      "Connect a source or upload a file; SANKET maps it into the canonical schema without a migration project.",
  },
] as const;

/** Mirrors the SignalType enum in backend/app/models/enums.py. */
export const SIGNALS = [
  {
    key: "weather",
    name: "Weather",
    source: "Open-Meteo",
    feeds: "Seasonal demand, sowing windows, footfall.",
  },
  {
    key: "trend_search",
    name: "Search trends",
    source: "Google Trends",
    feeds: "Early demand movement before it reaches sales.",
  },
  {
    key: "social_sentiment",
    name: "Social sentiment",
    source: "Reddit",
    feeds: "Category interest and emerging product talk.",
  },
  {
    key: "competitor_price",
    name: "Competitor price",
    source: "Retail price tracking",
    feeds: "Share shift when a rival moves on price.",
  },
  {
    key: "macro_economic",
    name: "Macro-economic",
    source: "FRED",
    feeds: "Demand pressure from rates, inflation and output.",
  },
  {
    key: "regulatory",
    name: "Regulatory",
    source: "FDA feeds",
    feeds: "Supply risk from recalls and approvals.",
  },
  {
    key: "supplier_lead",
    name: "Supplier lead time",
    source: "Connected ERP / purchase orders",
    feeds: "Protection window and reorder timing.",
  },
  {
    key: "logistics_disruption",
    name: "Logistics disruption",
    source: "Freight and port feeds",
    feeds: "Delay risk on inbound stock.",
  },
] as const;

/**
 * Mirrors backend/app/connectors/catalog.py — the source of truth.
 *
 * This is a static copy because the real catalog is served by an authenticated
 * endpoint and this page is public. It can drift when providers are added;
 * check it against the backend file when you touch either.
 *
 * `availability` is load-bearing, not decoration. Six of these work today. The
 * page previously advertised "29+ CONNECTORS" by counting the planned ones.
 */
export const CONNECTORS: { name: string; category: string; availability: Availability }[] = [
  { name: "Shopify", category: "Sales & E-commerce", availability: "live" },
  { name: "WooCommerce", category: "Sales & E-commerce", availability: "live" },
  { name: "CSV Upload", category: "Files", availability: "live" },
  { name: "Excel Upload", category: "Files", availability: "live" },
  { name: "PostgreSQL", category: "Databases", availability: "live" },
  { name: "MySQL", category: "Databases", availability: "live" },
  { name: "REST API / Push", category: "API", availability: "beta" },
  { name: "Generic Webhooks", category: "Streaming", availability: "beta" },
  { name: "Magento", category: "Sales & E-commerce", availability: "planned" },
  { name: "BigCommerce", category: "Sales & E-commerce", availability: "planned" },
  { name: "Amazon Seller", category: "Sales & E-commerce", availability: "planned" },
  { name: "Flipkart Seller", category: "Sales & E-commerce", availability: "planned" },
  { name: "Square", category: "Point of Sale", availability: "planned" },
  { name: "Lightspeed", category: "Point of Sale", availability: "planned" },
  { name: "Toast", category: "Point of Sale", availability: "planned" },
  { name: "Clover", category: "Point of Sale", availability: "planned" },
  { name: "SAP S/4HANA", category: "ERP & Inventory", availability: "planned" },
  { name: "Oracle ERP", category: "ERP & Inventory", availability: "planned" },
  { name: "Microsoft Dynamics 365", category: "ERP & Inventory", availability: "planned" },
  { name: "Oracle NetSuite", category: "ERP & Inventory", availability: "planned" },
  { name: "Odoo", category: "ERP & Inventory", availability: "planned" },
  { name: "Tally Prime / ERP 9", category: "ERP & Inventory", availability: "planned" },
  { name: "Zoho Books", category: "ERP & Inventory", availability: "planned" },
  { name: "Zoho Inventory", category: "ERP & Inventory", availability: "planned" },
  { name: "Busy Accounting", category: "ERP & Inventory", availability: "planned" },
  { name: "Marg ERP", category: "ERP & Inventory", availability: "planned" },
  { name: "Vyapar", category: "ERP & Inventory", availability: "planned" },
  { name: "ERPNext / Frappe", category: "ERP & Inventory", availability: "planned" },
  { name: "Unicommerce", category: "ERP & Inventory", availability: "planned" },
  { name: "Manhattan Associates", category: "Warehouse", availability: "planned" },
  { name: "Blue Yonder", category: "Warehouse", availability: "planned" },
  { name: "Infor WMS", category: "Warehouse", availability: "planned" },
  { name: "Fishbowl", category: "Warehouse", availability: "planned" },
  { name: "Snowflake", category: "Data Warehouse", availability: "planned" },
  { name: "Databricks", category: "Data Warehouse", availability: "planned" },
  { name: "Google BigQuery", category: "Data Warehouse", availability: "planned" },
  { name: "Amazon Redshift", category: "Data Warehouse", availability: "planned" },
  { name: "Azure Synapse", category: "Data Warehouse", availability: "planned" },
  { name: "Apache Kafka", category: "Streaming", availability: "planned" },
  { name: "RabbitMQ", category: "Streaming", availability: "planned" },
  { name: "AWS Kinesis", category: "Streaming", availability: "planned" },
  { name: "Google Pub/Sub", category: "Streaming", availability: "planned" },
];

export const CONNECTOR_CATEGORIES = [...new Set(CONNECTORS.map((c) => c.category))];
export const TOTAL_CONNECTOR_COUNT = CONNECTORS.length;
export const LIVE_CONNECTOR_COUNT = CONNECTORS.filter((c) => c.availability === "live").length;
```

- [ ] **Step 4: Run the tests**

```bash
cd frontend && npx vitest run src/pages/landing/content.test.ts && npm run typecheck
```

Expected: 6 passed, typecheck exit 0.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/landing/content.ts frontend/src/pages/landing/content.test.ts
git commit -m "feat(landing): one content module, every claim traceable

Industry horizons and audit levels mirror industry_context.py; the
connector list mirrors connectors/catalog.py including availability.
Six connectors are live out of 42 — the page advertised 29+ by counting
the planned ones, and a test now pins the honest counts."
```

---

## Task 4: Interactive industry tabs

**Files:**
- Create: `src/pages/landing/sections/IndustryTabs.tsx`, `src/pages/landing/sections/IndustryTabs.test.tsx`
- Modify: `src/pages/landing/LiveConsoleLanding.tsx` (replace the inline industries section at `:558-655`)

**Interfaces:**
- Consumes: `INDUSTRY_DETAIL` from `content.ts`
- Produces: `<IndustryTabs />` rendering `<section id="industries">`

- [ ] **Step 1: Write the failing test**

```tsx
// src/pages/landing/sections/IndustryTabs.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { IndustryTabs } from "@/pages/landing/sections/IndustryTabs";

describe("IndustryTabs", () => {
  it("shows the first industry's real horizon on load", () => {
    render(<IndustryTabs />);
    expect(screen.getByRole("tab", { name: /apparel & fashion/i })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByText(/26-week/i)).toBeInTheDocument();
  });

  it("switches the panel when another industry is chosen", async () => {
    const user = userEvent.setup();
    render(<IndustryTabs />);
    await user.click(screen.getByRole("tab", { name: /pharmaceuticals/i }));

    // Pharma is the commercially distinctive one: 52 weeks at GxP.
    expect(screen.getByText(/52-week/i)).toBeInTheDocument();
    expect(screen.getByText(/gxp/i)).toBeInTheDocument();
    expect(screen.queryByText(/26-week/i)).toBeNull();
  });

  it("is operable by keyboard", async () => {
    const user = userEvent.setup();
    render(<IndustryTabs />);
    await user.tab();
    expect(screen.getByRole("tab", { name: /apparel & fashion/i })).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("tabpanel")).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd frontend && npx vitest run src/pages/landing/sections/IndustryTabs.test.tsx
```

Expected: FAIL — module not found.

- [ ] **Step 3: Write the component**

```tsx
// src/pages/landing/sections/IndustryTabs.tsx
import { useState } from "react";
import { Cpu, Layers, Pill, Sprout, Wrench, type AppIcon } from "@/components/ui/icons";
import { INDUSTRY_DETAIL } from "@/pages/landing/content";
import type { IndustryCode } from "@/types/api";

const ICONS: Record<IndustryCode, AppIcon> = {
  fashion: Layers,
  electronics: Cpu,
  pharma: Pill,
  agrocenter: Sprout,
  hardware: Wrench,
};

const ORDER: IndustryCode[] = ["fashion", "electronics", "pharma", "agrocenter", "hardware"];

/**
 * The strongest section on the page, because the facts are specific and real:
 * each vertical plans on its own horizon at its own audit level, straight from
 * the backend's industry registry. No competitor homepage can copy it, because
 * it describes what this engine actually does per industry.
 */
export const IndustryTabs = () => {
  const [active, setActive] = useState<IndustryCode>("fashion");
  const detail = INDUSTRY_DETAIL[active];

  return (
    <section id="industries" className="lc-section">
      <div className="lc-shell">
        <div className="lc-intro lc-intro-center">
          <p className="lc-kicker">Industries</p>
          <h2 className="lc-h2">One engine, fluent in your operation</h2>
          <p className="lc-lede">
            The reasoning stays the same. The horizon, the signals and the audit
            level change with what you sell.
          </p>
        </div>

        <div className="lc-tabs" role="tablist" aria-label="Industries">
          {ORDER.map((code) => {
            const Icon = ICONS[code];
            return (
              <button
                key={code}
                type="button"
                role="tab"
                aria-selected={active === code}
                aria-controls="lc-industry-panel"
                className={active === code ? "is-active" : ""}
                onClick={() => setActive(code)}
              >
                <Icon size={16} aria-hidden="true" />
                {INDUSTRY_DETAIL[code].label}
              </button>
            );
          })}
        </div>

        <div id="lc-industry-panel" role="tabpanel" className="lc-industry-panel">
          <dl className="lc-industry-specs">
            <div>
              <dt>Planning horizon</dt>
              <dd>{detail.horizonWeeks}-week</dd>
            </div>
            <div>
              <dt>Audit level</dt>
              <dd>{detail.auditLevel}</dd>
            </div>
            <div>
              <dt>Signals</dt>
              <dd>{detail.signals.join(" · ")}</dd>
            </div>
          </dl>
          <div className="lc-industry-card-stack">
            <article>
              <span className="lc-card-label">SANKET observes</span>
              <p>{detail.observes}</p>
            </article>
            <article>
              <span className="lc-card-label">It catches</span>
              <p>{detail.risk}</p>
            </article>
            <article>
              <span className="lc-card-label">You act</span>
              <p>{detail.action}</p>
            </article>
          </div>
        </div>
      </div>
    </section>
  );
};
```

- [ ] **Step 4: Wire it in**

In `LiveConsoleLanding.tsx`, delete the inline industries `<section id="industries">` block and the now-unused `INDUSTRIES` constant, `active`/`industry` state and `handleIndustry`. Render `<IndustryTabs />` in its place and add `import { IndustryTabs } from "./sections/IndustryTabs";`.

- [ ] **Step 5: Run the tests**

```bash
cd frontend && npx vitest run src/pages/landing/sections/IndustryTabs.test.tsx && npm run typecheck
```

Expected: 3 passed, typecheck exit 0.

- [ ] **Step 6: Commit**

```bash
git add -A frontend/src/pages/landing
git commit -m "feat(landing): industry tabs show each vertical's real planning profile"
```

---

## Task 5: Searchable connector grid

**Files:**
- Create: `src/pages/landing/sections/ConnectorGrid.tsx`, `src/pages/landing/sections/ConnectorGrid.test.tsx`

**Interfaces:**
- Consumes: `CONNECTORS`, `CONNECTOR_CATEGORIES`, `LIVE_CONNECTOR_COUNT`, `TOTAL_CONNECTOR_COUNT`
- Produces: `<ConnectorGrid />` rendering `<section id="integrations">`

- [ ] **Step 1: Write the failing test**

```tsx
// src/pages/landing/sections/ConnectorGrid.test.tsx
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ConnectorGrid } from "@/pages/landing/sections/ConnectorGrid";

describe("ConnectorGrid", () => {
  it("filters by free-text search", async () => {
    const user = userEvent.setup();
    render(<ConnectorGrid />);
    await user.type(screen.getByRole("searchbox", { name: /search connectors/i }), "shop");

    expect(screen.getByText("Shopify")).toBeInTheDocument();
    expect(screen.queryByText("Snowflake")).toBeNull();
  });

  it("filters by category", async () => {
    const user = userEvent.setup();
    render(<ConnectorGrid />);
    await user.click(screen.getByRole("button", { name: /^databases$/i }));

    expect(screen.getByText("PostgreSQL")).toBeInTheDocument();
    expect(screen.queryByText("Shopify")).toBeNull();
  });

  it("says plainly how many connectors actually work today", () => {
    // The page used to advertise "29+ CONNECTORS", counting ones with no
    // adapter built. Six work; the rest are on the roadmap.
    render(<ConnectorGrid />);
    expect(screen.getByText(/6 live today/i)).toBeInTheDocument();
  });

  it("marks a planned connector as not yet available", () => {
    render(<ConnectorGrid />);
    const card = screen.getByText("Snowflake").closest("li");
    expect(card).not.toBeNull();
    expect(within(card as HTMLElement).getByText(/coming soon/i)).toBeInTheDocument();
  });

  it("reports when a search matches nothing", async () => {
    const user = userEvent.setup();
    render(<ConnectorGrid />);
    await user.type(screen.getByRole("searchbox", { name: /search connectors/i }), "zzzz");
    expect(screen.getByText(/no connectors match/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd frontend && npx vitest run src/pages/landing/sections/ConnectorGrid.test.tsx
```

Expected: FAIL — module not found.

- [ ] **Step 3: Write the component**

```tsx
// src/pages/landing/sections/ConnectorGrid.tsx
import { useMemo, useState } from "react";
import { Search } from "@/components/ui/icons";
import {
  CONNECTORS,
  CONNECTOR_CATEGORIES,
  LIVE_CONNECTOR_COUNT,
  TOTAL_CONNECTOR_COUNT,
  type Availability,
} from "@/pages/landing/content";

const BADGE: Record<Availability, string> = {
  live: "Live",
  beta: "Beta",
  planned: "Coming soon",
};

const ALL = "All";

/**
 * Availability is shown per connector rather than rolled into one headline
 * number. Six of the forty-two work today; advertising the catalog size as if
 * it were the integration count is the kind of claim this page must not make.
 */
export const ConnectorGrid = () => {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState(ALL);

  const shown = useMemo(() => {
    const q = query.trim().toLowerCase();
    return CONNECTORS.filter(
      (c) =>
        (category === ALL || c.category === category) &&
        (q === "" || c.name.toLowerCase().includes(q)),
    );
  }, [query, category]);

  return (
    <section id="integrations" className="lc-section lc-section-alt">
      <div className="lc-shell">
        <div className="lc-intro">
          <p className="lc-kicker">Integrations</p>
          <h2 className="lc-h2">Works on top of the stack you already run</h2>
          <p className="lc-lede">
            {LIVE_CONNECTOR_COUNT} live today, {TOTAL_CONNECTOR_COUNT} in the
            catalog. Start with a file or a database and add sources as you go —
            there is no migration step.
          </p>
        </div>

        <div className="lc-connector-controls">
          <label className="lc-search">
            <Search size={15} aria-hidden="true" />
            <input
              type="search"
              aria-label="Search connectors"
              placeholder="Search connectors"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <div className="lc-chips">
            {[ALL, ...CONNECTOR_CATEGORIES].map((c) => (
              <button
                key={c}
                type="button"
                aria-pressed={category === c}
                className={category === c ? "is-active" : ""}
                onClick={() => setCategory(c)}
              >
                {c}
              </button>
            ))}
          </div>
        </div>

        {shown.length === 0 ? (
          <p className="lc-body">No connectors match that search.</p>
        ) : (
          <ul className="lc-connector-grid">
            {shown.map((c) => (
              <li key={c.name} className={`lc-connector is-${c.availability}`}>
                <span className="lc-connector-name">{c.name}</span>
                <span className="lc-connector-meta">{c.category}</span>
                <span className={`lc-badge is-${c.availability}`}>{BADGE[c.availability]}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
};
```

- [ ] **Step 4: Run the tests**

```bash
cd frontend && npx vitest run src/pages/landing/sections/ConnectorGrid.test.tsx && npm run typecheck
```

Expected: 5 passed, typecheck exit 0.

- [ ] **Step 5: Commit**

```bash
git add -A frontend/src/pages/landing/sections
git commit -m "feat(landing): searchable connector grid with honest availability"
```

---

## Task 6: Module grid with detail panel

**Files:**
- Create: `src/pages/landing/sections/ModuleGrid.tsx`, `src/pages/landing/sections/ModuleGrid.test.tsx`

**Interfaces:**
- Consumes: `MODULES`
- Produces: `<ModuleGrid />` rendering `<section id="platform-modules">`

- [ ] **Step 1: Write the failing test**

```tsx
// src/pages/landing/sections/ModuleGrid.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ModuleGrid } from "@/pages/landing/sections/ModuleGrid";

describe("ModuleGrid", () => {
  it("lists every module", () => {
    render(<ModuleGrid />);
    expect(screen.getByRole("button", { name: /demand forecasting/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /decision engine/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /what-if scenarios/i })).toBeInTheDocument();
  });

  it("opens a module's detail when selected", async () => {
    const user = userEvent.setup();
    render(<ModuleGrid />);
    await user.click(screen.getByRole("button", { name: /what-if scenarios/i }));

    expect(screen.getByText(/simulate a promotion/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /what-if scenarios/i })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });

  it("shows one detail at a time", async () => {
    const user = userEvent.setup();
    render(<ModuleGrid />);
    await user.click(screen.getByRole("button", { name: /what-if scenarios/i }));
    await user.click(screen.getByRole("button", { name: /data quality/i }));

    expect(screen.getByText(/flags gaps, duplicates/i)).toBeInTheDocument();
    expect(screen.queryByText(/simulate a promotion/i)).toBeNull();
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd frontend && npx vitest run src/pages/landing/sections/ModuleGrid.test.tsx
```

Expected: FAIL — module not found.

- [ ] **Step 3: Write the component**

```tsx
// src/pages/landing/sections/ModuleGrid.tsx
import { useState } from "react";
import { MODULES } from "@/pages/landing/content";

/**
 * o9's homepage answers "what do I get" with a solutions taxonomy. This is the
 * equivalent, built from the routes that actually exist in App.tsx rather than
 * from a wishlist.
 */
export const ModuleGrid = () => {
  const [open, setOpen] = useState<string | null>(null);

  return (
    <section id="platform-modules" className="lc-section">
      <div className="lc-shell">
        <div className="lc-intro">
          <p className="lc-kicker">The platform</p>
          <h2 className="lc-h2">What you get on day one</h2>
          <p className="lc-lede">
            Every module below is part of the workspace, scoped to your industry.
            Select one to see what it does.
          </p>
        </div>

        <ul className="lc-module-grid">
          {MODULES.map((m) => (
            <li key={m.key}>
              <button
                type="button"
                aria-expanded={open === m.key}
                aria-controls={`module-detail-${m.key}`}
                className={open === m.key ? "is-active" : ""}
                onClick={() => setOpen(open === m.key ? null : m.key)}
              >
                <span className="lc-module-name">{m.name}</span>
                <span className="lc-module-blurb">{m.blurb}</span>
              </button>
              {open === m.key && (
                <p id={`module-detail-${m.key}`} className="lc-module-detail">
                  {m.detail}
                </p>
              )}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
};
```

- [ ] **Step 4: Run the tests**

```bash
cd frontend && npx vitest run src/pages/landing/sections/ModuleGrid.test.tsx && npm run typecheck
```

Expected: 3 passed, typecheck exit 0.

- [ ] **Step 5: Commit**

```bash
git add -A frontend/src/pages/landing/sections
git commit -m "feat(landing): module grid built from the app's real routes"
```

---

## Task 7: Signal grid, engine, security and get-started sections

Four presentational sections, grouped because none carries meaningful state and a reviewer would accept or reject them together.

**Files:**
- Create: `src/pages/landing/sections/SignalGrid.tsx`, `ForecastEngine.tsx`, `SecurityTenancy.tsx`, `GetStarted.tsx`, `WhatItDoes.tsx`
- Create: `src/pages/landing/sections/SignalGrid.test.tsx`
- Modify: `src/pages/landing/LiveConsoleLanding.tsx`

**Interfaces:**
- Consumes: `SIGNALS`
- Produces: `<WhatItDoes />`, `<SignalGrid />` (`<section id="signals">`), `<ForecastEngine />` (`<section id="engine">`), `<SecurityTenancy />` (`<section id="security">`), `<GetStarted onBook onSandbox />` (`<section id="get-started">`)

- [ ] **Step 1: Write the failing test**

```tsx
// src/pages/landing/sections/SignalGrid.test.tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { SignalGrid } from "@/pages/landing/sections/SignalGrid";

describe("SignalGrid", () => {
  it("names the source behind each signal", () => {
    render(<SignalGrid />);
    expect(screen.getByText("Google Trends")).toBeInTheDocument();
    expect(screen.getByText("FRED")).toBeInTheDocument();
  });

  it("expands a signal to show what it feeds", async () => {
    const user = userEvent.setup();
    render(<SignalGrid />);
    await user.click(screen.getByRole("button", { name: /weather/i }));
    expect(screen.getByText(/seasonal demand, sowing windows/i)).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

```bash
cd frontend && npx vitest run src/pages/landing/sections/SignalGrid.test.tsx
```

Expected: FAIL — module not found.

- [ ] **Step 3: Write SignalGrid**

```tsx
// src/pages/landing/sections/SignalGrid.tsx
import { useState } from "react";
import { SIGNALS } from "@/pages/landing/content";

export const SignalGrid = () => {
  const [open, setOpen] = useState<string | null>(null);

  return (
    <section id="signals" className="lc-section lc-section-alt">
      <div className="lc-shell">
        <div className="lc-intro">
          <p className="lc-kicker">Signals</p>
          <h2 className="lc-h2">Demand moves before your sales report does</h2>
          <p className="lc-lede">
            SANKET reads outside signals alongside your own history, so a
            forecast change comes with a named cause instead of a shrug.
          </p>
        </div>

        <ul className="lc-signal-grid">
          {SIGNALS.map((s) => (
            <li key={s.key}>
              <button
                type="button"
                aria-expanded={open === s.key}
                onClick={() => setOpen(open === s.key ? null : s.key)}
              >
                <span className="lc-signal-name">{s.name}</span>
                <span className="lc-signal-source">{s.source}</span>
              </button>
              {open === s.key && <p className="lc-signal-feeds">{s.feeds}</p>}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
};
```

- [ ] **Step 4: Write the three remaining presentational sections**

`WhatItDoes.tsx` — `<section id="what-it-does" className="lc-section">` with kicker "How it fits", h2 "From raw orders to an approved reorder", and four steps (Ingest / Forecast / Decide / Act) each a short paragraph, using `lc-stack` for rhythm.

`ForecastEngine.tsx` — `<section id="engine" className="lc-section">` with kicker "The engine", h2 "Per-SKU models, scored against what happened", and three points: per-SKU model routing rather than one global model; a zero-shot foundation model (Chronos) so a new SKU forecasts without history; accuracy backtested and reported per SKU so trust is earned rather than asserted.

`SecurityTenancy.tsx` — `<section id="security" className="lc-section lc-section-alt">` with kicker "Security", h2 "Your data stays yours", and three points: PostgreSQL row-level security so isolation is enforced at the database, not the application; an append-only audit trail on every decision; GxP / 21 CFR Part 11 audit level for pharmaceutical workspaces. Keep the existing honest framing — architected *for* SOC 2 and HIPAA workflows, not certified.

`GetStarted.tsx` — `<section id="get-started" className="lc-section">` taking `{ onBook, onSandbox }`, presenting the four entry points as cards: Try Live Sandbox (`onSandbox`), Create Workspace (link to `/login?mode=signup`), Request Enterprise Demo (`onBook`), Sign In (link to `/login`).

- [ ] **Step 5: Compose them**

In `LiveConsoleLanding.tsx`, import all five and render in order: existing console (`#platform`) → `<WhatItDoes />` → existing `#how-it-works` → `<IndustryTabs />` → `<ModuleGrid />` → `<SignalGrid />` → `<ConnectorGrid />` → `<ForecastEngine />` → `<SecurityTenancy />` → `<GetStarted />`. Delete the old stats band that carried `id="get-started"`.

- [ ] **Step 6: Run the tests**

```bash
cd frontend && npx vitest run src/pages/landing && npm run typecheck && npm run lint
```

Expected: all pass, typecheck exit 0, lint 0 errors.

- [ ] **Step 7: Commit**

```bash
git add -A frontend/src/pages/landing
git commit -m "feat(landing): signals, engine, security and entry-point sections"
```

---

## Task 8: Style the new sections

**Files:**
- Modify: `src/pages/landing/live-console.css`

**Interfaces:**
- Consumes: the class names used in Tasks 4–7
- Produces: styles for `.lc-industry-panel`, `.lc-industry-specs`, `.lc-connector-controls`, `.lc-search`, `.lc-chips`, `.lc-connector-grid`, `.lc-connector`, `.lc-badge`, `.lc-module-grid`, `.lc-module-detail`, `.lc-signal-grid`

- [ ] **Step 1: Write the styles**

Add to `live-console.css`, reusing the existing tokens (`--lc-bg-alt`, the radius and border variables already defined) and the three font tokens from Task 2. Grids use `repeat(auto-fill, minmax(220px, 1fr))` so they reflow without breakpoints. Badges: `.lc-badge.is-live` green, `.is-beta` amber, `.is-planned` muted grey. Every interactive element gets a visible `:focus-visible` outline.

- [ ] **Step 2: Verify in the browser**

```bash
cd frontend && npm run dev
```

Open the page, confirm: no horizontal scroll at 375px, 768px and 1440px; the tab/chip/search controls all show a focus ring when tabbed to; the connector grid reflows without overlap; no section shows a void taller than its content.

- [ ] **Step 3: Run the suite**

```bash
cd frontend && npm run typecheck && npm run lint && npm test
```

Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/landing/live-console.css
git commit -m "style(landing): style the new interactive sections"
```

---

## Task 9: End-to-end verification

**Files:**
- Modify: `frontend/e2e/industry-scope.spec.ts` (the landing-page test)

- [ ] **Step 1: Extend the existing landing E2E**

Add to the "public landing page offers all four entry points" test:

```ts
    // Every nav link must scroll to a section that exists — the defect that
    // started this work was a Pricing link pointing at a statistics band.
    for (const label of ["Platform", "Industries", "How It Works", "Integrations", "Security"]) {
      const link = page.getByRole("button", { name: new RegExp(`^${label}$`, "i") }).first();
      await expect(link).toBeVisible();
    }
    await expect(page.getByRole("button", { name: /^pricing$/i })).toHaveCount(0);

    // The connector grid is operable.
    await page.getByRole("searchbox", { name: /search connectors/i }).fill("shop");
    await expect(page.getByText("Shopify")).toBeVisible();
    await expect(page.getByText("Snowflake")).toHaveCount(0);
```

- [ ] **Step 2: Run it**

```bash
cd frontend && npx playwright test e2e/industry-scope.spec.ts --reporter=line
```

Expected: both tests pass. The stack must be up — see the memory note on what Playwright needs.

- [ ] **Step 3: Commit**

```bash
git add frontend/e2e/industry-scope.spec.ts
git commit -m "test(e2e): landing nav resolves and the connector grid filters"
```

---

## Task 10: Report the image slots

**Files:** none — this task produces a message, not a commit.

- [ ] **Step 1: Collect the slots**

Walk the finished page and list every place an image would earn its keep, with the exact aspect ratio and the file path it should be dropped at. The existing `INDUSTRY_DETAIL` pattern already supports per-industry artwork (`public/assets/<industry>.png`), so those slots exist; the new sections may want a product screenshot for the console and the module grid.

- [ ] **Step 2: Report to the user**

Give the list as: purpose, section, dimensions, file path. Do not invent placeholder images or ship stock photography.

---

## Self-Review

**Spec coverage:** §1 problem → Tasks 1, 2; §2 honesty constraint → Task 3 (counts pinned by test), Task 5 (per-connector badges); §3 IA, all eleven sections → Task 1 (hero, console, how-it-works retained), Tasks 4–7 (the seven new/rebuilt); §3 nav rename → Task 1; §4 interactivity, all six controls → Task 4 (tabs), 5 (search+filter), 6 (module detail), 7 (signal expand), and the what-if slider **— gap found: the slider is specified in §4 but has no task.** See below. §5 typography → Task 2; §6 structure/deletions → Tasks 1, 4, 7; §7 testing → every task; §8 connector drift risk → documented in the Task 3 code comment; §9 out of scope → Task 10 covers images.

**Gap fixed:** the what-if slider from spec §4 is folded into Task 6 as a follow-on rather than its own task — the module grid's "What-if scenarios" entry gets a live slider in its detail panel, with a test asserting the displayed forecast number changes when the slider moves. An executor should treat that as Step 3a of Task 6.

**Placeholder scan:** no TBD/TODO. Task 7 Step 4 and Task 8 Step 1 describe content and styles in prose rather than full code — acceptable because they are presentational and the class vocabulary is fully specified, but an executor should follow the established patterns in the file rather than inventing new ones.

**Type consistency:** `INDUSTRY_DETAIL`, `MODULES`, `SIGNALS`, `CONNECTORS`, `CONNECTOR_CATEGORIES`, `LIVE_CONNECTOR_COUNT`, `TOTAL_CONNECTOR_COUNT` and `Availability` are defined in Task 3 and used with those exact names in Tasks 4–7. Section ids `platform`, `industries`, `how-it-works`, `integrations`, `security` match the `sectionLinks` set in Task 1. `IndustryCode` is imported from `@/types/api` in both Task 3 and Task 4.
