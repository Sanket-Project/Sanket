import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

/** The landing page shares the product-wide heading, body, and data roles. */
const css = readFileSync("src/pages/landing/live-console.css", "utf8");
const page = readFileSync("src/pages/LandingPage.tsx", "utf8");
const html = readFileSync("index.html", "utf8");

describe("landing typography", () => {
  it("declares the three type roles as tokens", () => {
    expect(css).toContain('--lc-font-display: "Space Grotesk"');
    expect(css).toContain('--lc-font-body: "IBM Plex Sans"');
    expect(css).toContain('--lc-font-mono: "IBM Plex Mono"');
  });

  it("names no font family outside those tokens", () => {
    const families = [...css.matchAll(/font-family:\s*([^;]+);/g)].map((m) => m[1].trim());
    expect(families.length).toBeGreaterThan(0);
    for (const f of families) {
      expect(f, `raw font stack "${f}" should use a --lc-font-* token`).toMatch(
        /var\(--lc-font-/,
      );
    }
  });

  it("does not set a competing font inline", () => {
    expect(page).not.toMatch(/fontFamily\s*:/);
  });

  it("puts the hero on the same body font as the sections below it", () => {
    // The tokens live on .landing-root so the hero and sections inherit one
    // body family before users enter signup and the authenticated portal.
    expect(page).toMatch(/className="landing-root /);
    expect(css).toMatch(/\.landing-root\s*\{[^}]*--lc-font-body/);
  });

  it("loads fonts from the document head, not an inline @import", () => {
    expect(page).not.toMatch(/@import url\('https:\/\/fonts\.googleapis\.com/);
    expect(html).toMatch(/fonts\.googleapis\.com/);
  });
});
