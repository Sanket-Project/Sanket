import { readFileSync } from "node:fs";
import { expect, it } from "vitest";
import postcss from "postcss";
import tailwindcss from "tailwindcss";
import config from "../../tailwind.config";

// Same cwd-relative path as text-contrast.test.ts (Vitest runs from frontend/).
const css = readFileSync("src/styles/index.css", "utf8");

it("defines motion tokens at the DESIGN.md durations", () => {
  expect(css).toMatch(/--dur-fast:\s*140ms/);
  expect(css).toMatch(/--dur:\s*200ms/);
  expect(css).toMatch(/--ease:\s*cubic-bezier\(0\.2,\s*0,\s*0,\s*1\)/);
});

it("exposes motion tokens as Tailwind utilities", async () => {
  const { css: out } = await postcss([tailwindcss({ ...config, content: [{ raw: "duration-fast duration-base ease-standard", extension: "html" }] })]).process("@tailwind utilities;", { from: undefined });
  expect(out).toContain(".duration-fast");
  expect(out).toContain(".duration-base");
  expect(out).toContain(".ease-standard");
});

it("defines the type scale and focus ring classes", () => {
  for (const cls of [".t-page", ".t-section", ".t-card", ".t-kpi", ".t-label", ".t-body", ".t-table", ".focus-ring"]) {
    expect(css).toContain(cls);
  }
});
