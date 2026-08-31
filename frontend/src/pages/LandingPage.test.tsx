import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

/**
 * Source-level assertions rather than a render.
 *
 * LandingPage is a 2,600-line marketing page built on scroll-linked framer
 * motion, an intro loader gated on sessionStorage, and a background video —
 * none of which behave in jsdom. Rendering it would test the mocks. What
 * matters here is which entry points the page offers and what it claims, and
 * both are visible in the source.
 */
const source = readFileSync("src/pages/LandingPage.tsx", "utf8");

describe("landing page", () => {
  it("offers all four public entry points", () => {
    for (const cta of [
      "Try Live Sandbox",
      "Create Workspace",
      "Request Enterprise Demo",
      "Sign in",
    ]) {
      expect(source).toContain(cta);
    }
  });

  it("routes Create Workspace to self-service signup", () => {
    expect(source).toContain("/login?mode=signup");
  });

  it("does not sell multi-tenancy as a differentiator", () => {
    expect(source).not.toMatch(/multi-tenant/i);
  });

  it("does not let a visitor pick a sandbox industry the session ignores", () => {
    // The picker only ever called setIndustry() client-side; the sandbox
    // session itself was always the same shared tenant.
    expect(source).not.toMatch(/setIndustry/);
  });
});
