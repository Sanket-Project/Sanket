---
version: alpha
name: SANKET Predictive OS
description: >-
  Visual identity for SANKET — a predictive demand-forecasting and supply-chain
  intelligence platform. Calm, instrument-grade, enterprise. Built on the
  "Blue Whale" deep teal with a "Jet Stream" pale-teal accent.
colors:
  canvas: "#BDD9D7"
  surface: "#ffffff"
  surface-2: "#f4f8f8"
  surface-3: "#e1eeed"
  text: "#022327"
  text-muted: "#1a4950"
  text-subtle: "#4b787e"
  primary: "#03363D"
  primary-strong: "#022429"
  on-primary: "#ffffff"
  canvas-dark: "#021a1d"
  surface-dark: "#03363D"
  surface-2-dark: "#05454e"
  surface-3-dark: "#085560"
  text-dark: "#eef7f6"
  primary-dark: "#BDD9D7"
  on-primary-dark: "#03363D"
  border: "rgba(3, 54, 61, 0.08)"
  border-strong: "rgba(3, 54, 61, 0.16)"
typography:
  display-lg:
    fontFamily: Space Grotesk
    fontSize: 84px
    fontWeight: "700"
    lineHeight: 88px
    letterSpacing: -0.03em
  display-md:
    fontFamily: Space Grotesk
    fontSize: 48px
    fontWeight: "700"
    lineHeight: 52px
    letterSpacing: -0.02em
  heading-lg:
    fontFamily: Space Grotesk
    fontSize: 24px
    fontWeight: "600"
    lineHeight: 32px
    letterSpacing: -0.01em
  heading-md:
    fontFamily: Space Grotesk
    fontSize: 18px
    fontWeight: "600"
    lineHeight: 24px
  body-lg:
    fontFamily: IBM Plex Sans
    fontSize: 18px
    fontWeight: "400"
    lineHeight: 28px
  body-md:
    fontFamily: IBM Plex Sans
    fontSize: 16px
    fontWeight: "400"
    lineHeight: 24px
  label-caps:
    fontFamily: Space Grotesk
    fontSize: 12px
    fontWeight: "600"
    lineHeight: 16px
    letterSpacing: 0.14em
  data-mono:
    fontFamily: IBM Plex Mono
    fontSize: 13px
    fontWeight: "500"
    lineHeight: 18px
rounded:
  sm: 12px
  DEFAULT: 20px
  pill: 9999px
spacing:
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 40px
components:
  logo-tile:
    backgroundColor: primary
    textColor: primary-dark
    rounded: sm
  button-primary:
    backgroundColor: primary
    textColor: on-primary
    rounded: sm
  card:
    backgroundColor: surface
    rounded: DEFAULT
---

## Overview

SANKET (Sanskrit *saṅketa*, "signal") turns a company's sales, inventory, and
live market signals into a single forecast for every SKU. The interface should
feel like a **precision instrument** — quiet, dense with meaning, trustworthy.
The mood is closer to a scientific dashboard or an aircraft display than to a
consumer app: confident, calm, and never decorative for its own sake.

## Colors

The palette is anchored on a single deep teal and its pale complement, applied
with high restraint. Color carries information; it is not ornament.

- **Blue Whale — Primary (`#03363D`):** The brand color. Buttons, the logo tile,
  active states, and headline ink in light mode. In dark mode it becomes the
  card surface.
- **Jet Stream — Accent (`#BDD9D7`):** The pale complement. It is the light-mode
  canvas and, inverted, the active/brand color in dark mode. The forecast curve
  in the logo is drawn in Jet Stream.
- **Surfaces:** Pure white cards float over the Jet Stream canvas in light mode;
  layered Blue Whale tones (`#03363D` -> `#085560`) stack in dark mode.
- **Text:** Near-black teal (`#022327`) for primary text, stepping to muted and
  subtle teals for hierarchy — never pure gray.

Avoid introducing new hues. The earlier purple/indigo prism and the
blue-purple-cyan hexagon were off-brand and have been retired in favor of this
teal system.

## Typography

**Space Grotesk** is the display and heading face — geometric, technical, a
little editorial. **IBM Plex Sans** carries body and UI text. **IBM Plex Mono**
is reserved for data: figures, IDs, tickers, and forecast readouts. Headlines
run tight (negative tracking); all-caps labels run wide (`0.14em`).

## Logo

The mark is a **forecast peak**: a single rising-and-cresting curve that reads
as a demand signal peaking, with a node dot marking the predicted apex. It sits
in a Blue Whale rounded tile with the curve drawn in Jet Stream. The curve also
quietly implies an *S* for SANKET.

- **Tile:** Blue Whale (`#03363D`), radius `sm`. On dark surfaces the tile may be
  dropped and the curve drawn directly in Jet Stream.
- **Curve:** Jet Stream (`#BDD9D7`), rounded caps.
- **Node:** White apex dot.
- **Wordmark:** "SANKET" in Space Grotesk, tight tracking, optionally with the
  "Predictive OS" label-caps kicker.
- **Clear space:** keep at least the height of the node dot on every side.
- **Minimum size:** 20px tile. Below that, use the mark without the wordmark.

## Motion

Motion is slow and eased, never bouncy. Standard easing is
`cubic-bezier(0.16, 1, 0.3, 1)` over 400-900ms for entrances. The logo curve may
"draw on" once on load; it should not loop.

## Principles

1. **Instrument, not ornament.** Every element should earn its place by carrying
   information or aiding a decision.
2. **One accent, applied sparingly.** Restraint is the brand.
3. **Data is monospaced.** Numbers align and read like a readout.
4. **Calm confidence.** Deep teal, generous space, tight type.
