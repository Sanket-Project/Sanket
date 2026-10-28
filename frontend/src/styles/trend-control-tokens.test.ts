import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import postcss from "postcss";
import tailwindcss from "tailwindcss";
import palette from "../../tailwind.config";

const trendSource = readFileSync("src/pages/TrendAnalysis.tsx", "utf8");
const selectSource = readFileSync("src/components/ui/SearchableSelect.tsx", "utf8");
const gaugeSource = readFileSync("src/components/charts/TrendScoreGauge.tsx", "utf8");
const compile = async (raw: string) => (await postcss([tailwindcss({ ...palette, content: [{ raw, extension: "tsx" }] })]).process("@tailwind utilities;", { from: undefined })).css;

describe("Trend control design tokens", () => {
  it("generates the active tab's themed background and matching foreground in the actual palette", async () => {
    const activeClasses = trendSource.match(/tab === id \? "([^"]+)"/)?.[1];
    expect(activeClasses).toBeTruthy();
    const css = await compile(activeClasses!);
    expect(css).toMatch(/background-color:\s*var\(--accent\)/);
    expect(css).toMatch(/color:\s*var\(--accent-fg\)/);
  });

  it("generates CSS for every brand color utility used by the trend and dropdown controls", async () => {
    const classes = [...new Set((trendSource + selectSource + gaugeSource).match(/(?:hover:|focus-visible:)?(?:bg|text|border|ring)-(?:primary|accent)(?:-[a-z]+)?(?:\/\d+)?/g))];
    expect(classes.length).toBeGreaterThan(0);
    const css = await compile(classes.join(" "));
    const missing = classes.filter((name) => !css.includes(`.${name.replace(/[:/]/g, (part) => `\\${part}`)}`));
    expect(missing).toEqual([]);
  });
});
