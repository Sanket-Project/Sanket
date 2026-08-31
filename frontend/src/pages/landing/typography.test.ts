import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

/**
 * The landing page ran four font families at once: DM Serif Display for
 * headlines, Space Grotesk set inline on the page wrapper, IBM Plex Sans set by
 * live-console.css, and IBM Plex Mono for labels. Body copy therefore changed
 * family partway down the page, where the hero ended and the sections began.
 *
 * Three roles now, routed through tokens so a fourth cannot be introduced by
 * editing a single rule.
 */
const css = readFileSync("src/pages/landing/live-console.css", "utf8");
const page = readFileSync("src/pages/LandingPage.tsx", "utf8");
const html = readFileSync("index.html", "utf8");

describe("landing typography", () => {
  it("declares the three type roles as tokens", () => {
    expect(css).toContain("--lc-font-display");
    expect(css).toContain("--lc-font-body");
    expect(css).toContain("--lc-font-mono");
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

  it("does not set a competing body font on the page wrapper", () => {
    expect(page).not.toMatch(/fontFamily:\s*"'Space Grotesk'/);
  });

  it("puts the hero on the same body font as the sections below it", () => {
    // Removing the inline Space Grotesk was not enough on its own: the hero
    // sits outside .lc, so it fell through to the app-wide Geist Sans while the
    // sections used IBM Plex Sans — the same family change, moved. The tokens
    // live on .landing-root so both inherit one body font.
    expect(page).toMatch(/className="landing-root /);
    expect(css).toMatch(/\.landing-root\s*\{[^}]*--lc-font-body/);
  });

  it("loads fonts from the document head, not an inline @import", () => {
    expect(page).not.toMatch(/@import url\('https:\/\/fonts\.googleapis\.com/);
    expect(html).toMatch(/fonts\.googleapis\.com/);
  });
});
