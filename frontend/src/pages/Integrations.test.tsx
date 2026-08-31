import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

/**
 * Source-level assertion. Integrations is a 950-line page of provider panels
 * behind a modal and a live catalog query; what matters here is a single fact
 * that is plainly visible in the source — it no longer offers, or sends, a
 * target industry. The server refuses a mismatched one either way.
 */
const source = readFileSync("src/pages/Integrations.tsx", "utf8");

describe("integrations", () => {
  it("never sends a target industry", () => {
    expect(source).not.toMatch(/target_industry/);
  });

  it("offers no industry selector", () => {
    expect(source).not.toMatch(/Target industry/i);
    expect(source).not.toMatch(/setIndustry/);
  });
});
