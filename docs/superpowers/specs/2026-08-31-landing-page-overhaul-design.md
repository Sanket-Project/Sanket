# Landing page overhaul

**Date:** 2026-08-31
**Status:** Approved (design), pending implementation
**Author:** Claude Code, via `superpowers:brainstorming`

---

## 1. Problem

Four complaints, one shared cause.

The live page is `LandingPage`'s hero followed by `LiveConsoleLanding`: **four
content sections, 5,626px tall, roughly 4,500 characters of copy**. o9's
homepage — the benchmark chosen for this work — is 7,736px across **twelve**
sections with a comparable word count. The difference is not how much they say;
it is that they say it in many short, dense blocks while we say it in a few
tall, sparse ones. That single structural fact produces three of the four
complaints:

- **"A lot of empty spaces."** Sections run 700–1,470px for as little as 399
  characters (`#architecture`). Padding is set per-section rather than from a
  shared rhythm, so the gaps are both large and uneven.
- **"Less information about the software."** Four sections cannot carry a
  planning platform's story. There is nowhere that says what the modules are,
  what data it connects to, what signals it reads, or how the forecasting
  actually works.
- **"Make the dashboards and cards interactive."** One control on the page is
  user-operated (the industry selector). Everything else either animates on a
  timer or does nothing.

The fourth is a straightforward defect. `LiveConsoleLanding` puts `id="pricing"`
on a **stats band**, so the header's Pricing link scrolls to "5 INDUSTRIES
SERVED / 29+ CONNECTORS". There is no pricing content on the live page at all.

Underneath, the file carries two hidden alternatives that never render: ~1,300
lines of legacy sections behind `VITE_LEGACY_LANDING` and a second concept,
`ModelsDisagreeLanding` (725 lines), behind `VITE_LANDING_CONCEPT`. The stale
header — written for the legacy page, which *did* have pricing — is exactly the
drift that carrying dead variants produces.

## 2. Honesty constraint

Every claim on the page must be traceable to something the repository actually
does. No customer names, no revenue figures, no analyst awards, no invented
metrics. This is the AGENTS.md "fail honestly" rule applied to marketing copy.

It has one immediate consequence. The catalog holds **42 connectors, of which
6 are `live`** (Shopify, WooCommerce, PostgreSQL, MySQL, CSV Upload, Excel
Upload) and 2 are `beta` (REST API / Push, Generic Webhooks). The remaining 34
are `planned` — the spec exists, the sync adapter does not. The current stats
band advertises "29+ CONNECTORS", which counts them. The new connector section
shows per-provider availability using the same Live / Beta / Coming-soon badges
the authenticated Integrations page already uses, and the headline number
becomes the honest one.

## 3. Information architecture

o9's rhythm — eyebrow, headline, short body, content, CTA — repeated across many
short sections. Eleven sections, each with a named source of truth.

| # | Section | Content source |
|---|---|---|
| 1 | Hero *(unchanged)* | — |
| 2 | **What SANKET does** — Ingest → Forecast → Decide → Act | product behaviour |
| 3 | **Live console** *(kept, made interactive)* | product UI |
| 4 | **Built for your industry** | `app/services/industry_context.py` |
| 5 | **How it works** *(kept, steps expandable)* | product behaviour |
| 6 | **What you get** — module grid | the routes in `frontend/src/App.tsx` |
| 7 | **Signals that move demand** | `SignalType` enum + `services/external_signals/` |
| 8 | **Connect your stack** — searchable grid | `backend/app/connectors/catalog.py` |
| 9 | **The forecasting engine** | `backend/ml/` |
| 10 | **Security and tenancy** *(salvaged from legacy)* | RLS, audit, GxP |
| 11 | **Four ways in** *(stats band, repurposed)* | the public entry points |

Section 4 is the strongest of the new material because the per-industry facts
are real and specific: Apparel & Fashion plans on a 26-week horizon at standard
audit level, Consumer Electronics 12 weeks, Pharmaceuticals **52 weeks at GxP
audit level**, Agrocenter & Farm Inputs 26, Hardware & Industrial Supply 16 —
each with its own required signal types. That is a genuinely differentiating
story no competitor's homepage can copy, and it is already in the codebase.

Navigation becomes **Platform · Industries · How It Works · Integrations ·
Security**, plus Sign In, Create Workspace and Request Enterprise Demo. Pricing
is removed, and every remaining link points at a section that exists. The
`id="pricing"` on the stats band is renamed to `id="get-started"`, so no anchor
in the page is named after content it does not contain.

## 4. Interactivity

Six user-operated controls. All state and data live in the component; there are
no network calls, no authentication, and no effect on first paint.

| Control | Behaviour |
|---|---|
| Industry tabs | Switching vertical re-renders the console with that industry's SKUs, signals, horizon and audit level |
| Module grid | Selecting a module opens a detail panel describing it |
| Connector grid | Free-text search and category filter across the catalog |
| What-if slider | Dragging recomputes the displayed forecast and its downstream numbers |
| How-it-works steps | Expand to reveal detail, collapsed by default |
| Signal cards | Expand to show what each signal feeds |

The console carries a visible "product illustration" label. Illustrative numbers
in a UI mock are normal and understood; the label removes any doubt that they
are a customer's real figures.

Every control is operable by keyboard and carries the ARIA role its behaviour
implies (`tablist`/`tab`, `slider`, `button` with `aria-expanded`). The page is
the product's first impression, and a marketing page that cannot be tabbed
through undercuts the accessibility claims made further down it.

## 5. Typography and spacing

Three roles, applied identically in every section:

- **DM Serif Display** — headlines only. Kept deliberately: the marketing page
  is allowed a display face the product UI does not use.
- **IBM Plex Sans** — all body copy. This is the fix for the visible break in
  the page: the hero wrapper currently sets Space Grotesk inline while
  `live-console.css` sets IBM Plex Sans, so the body font changes family partway
  down the page.
- **IBM Plex Mono** — every eyebrow, label and metric.

One type scale and one section rhythm token replace the ad-hoc per-section
padding, which is what closes the uneven whitespace. Fonts load from a `<link>`
in `index.html` rather than an `@import` inside an inline `<style>` element,
which is render-blocking and duplicated.

## 6. Structure

`LiveConsoleLanding.tsx` is 715 lines and would roughly triple. It splits:

```
src/pages/landing/
  sections/            one file per section
  content.ts           all copy and capability data, typed
  landing.css          type scale + section rhythm tokens
```

**Deleted:** `ModelsDisagreeLanding.tsx`, `models-disagree.css`,
`LandingCaseStudies.tsx`, `LandingTestimonials.tsx` (both placeholder content,
which the honesty constraint rules out), the `VITE_LEGACY_LANDING` and
`VITE_LANDING_CONCEPT` flags, and the legacy branch in `LandingPage.tsx`.
Everything remains in git history.

`LandingPage.tsx` keeps the hero, the header, the modals and the footer, and
composes the sections. It loses roughly 1,300 lines.

## 7. Testing

Vitest with Testing Library, one file per interactive component:

- industry tabs switch the rendered console content
- connector search and category filter narrow the grid
- the what-if slider changes the displayed forecast
- expandable steps and signal cards toggle
- every control is reachable and operable by keyboard

Extending the existing `LandingPage.test.tsx`:

- the header contains no Pricing link
- **every** nav anchor resolves to an element with that id — the regression test
  for the defect that started this work
- the four public entry points are all present
- no "multi-tenant" USP copy (existing assertion, retained)

## 8. Known risk

The connector list must be a static copy in the frontend: the real catalog is
served by an authenticated endpoint and this is a public page. It is sourced
once from `backend/app/connectors/catalog.py` and carries a comment naming that
file as the source of truth, but it can drift when providers are added. The
alternative — a second public endpoint — is not worth a new public API surface
for a marketing page.

## 9. Out of scope

- **A pricing section.** Real Razorpay plans exist (`growth_monthly`,
  `scale_monthly`, `enterprise_monthly`), so one is buildable, but the request
  was to remove the dead link rather than fill it.
- **Images.** The structure is built first; a specific list of what is needed
  and where follows, for the owner to supply.
- **Copywriting beyond capability.** No case studies or testimonials until
  there are real ones to publish.
