import { readFileSync } from "node:fs";
import { expect, it } from "vitest";

it("loads the authoritative TypeScript Vite config even with stale generated JS present", () => {
  const { scripts } = JSON.parse(readFileSync("package.json", "utf8"));
  for (const script of ["dev", "build", "preview"]) {
    expect(scripts[script]).toContain("--config vite.config.ts");
  }
});
