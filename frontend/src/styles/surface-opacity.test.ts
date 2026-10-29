import { expect, it } from "vitest";
import postcss from "postcss";
import tailwindcss from "tailwindcss";
import palette from "../../tailwind.config";

it("generates translucent semantic surfaces used by overlays and selection states", async () => {
  const { css } = await postcss([tailwindcss({ ...palette, content: [{ raw: "bg-surface/80 bg-accent/10 border-line/50 text-content-muted/80", extension: "html" }] })]).process("@tailwind utilities;", { from: undefined });
  for (const utility of ["bg-surface\\/80", "bg-accent\\/10", "border-line\\/50", "text-content-muted\\/80"]) {
    expect(css).toContain(`.${utility}`);
  }
});
