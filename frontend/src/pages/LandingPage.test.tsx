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
    // statistics band, so the anchor scrolled to "5 INDUSTRIES SERVED".
    // Every nav id must exist as a section id somewhere on the page.
    const navIds = [...page.matchAll(/\{\s*label:\s*"[^"]+",\s*id:\s*"([^"]+)"\s*\}/g)].map(
      (m) => m[1],
    );
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
