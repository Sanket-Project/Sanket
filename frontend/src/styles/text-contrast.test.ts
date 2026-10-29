import { readFileSync } from "node:fs";
import postcss from "postcss";
import { expect, it } from "vitest";

const sheet = postcss.parse(readFileSync("src/styles/index.css", "utf8"));
const theme = (dark: boolean) => {
  const vars: Record<string, string> = {};
  sheet.walkRules(rule => {
    if (rule.selector === ":root" || (dark && rule.selector === ".dark")) rule.walkDecls(decl => { vars[decl.prop] = decl.value; });
  });
  const resolve = (value: string): string => value.includes("var(") ? resolve(value.replace(/var\((--[\w-]+)\)/g, (_, key: string) => vars[key] ?? "")) : value;
  const luminance = (token: string) => {
    const channels = resolve(vars[token]).match(/[\d.]+/g)!.map(Number).slice(0, 3).map(value => {
      const normalized = value / 255;
      return normalized <= 0.04045 ? normalized / 12.92 : ((normalized + 0.055) / 1.055) ** 2.4;
    });
    return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
  };
  return (foreground: string, background: string) => {
    const [high, low] = [luminance(foreground), luminance(background)].sort((a, b) => b - a);
    return (high + 0.05) / (low + 0.05);
  };
};

for (const dark of [false, true]) {
  it(`keeps normal-size labels and helper text readable in the ${dark ? "dark" : "light"} theme`, () => {
    const contrast = theme(dark);
    for (const text of ["--text", "--text-muted", "--text-subtle"]) for (const surface of ["--canvas", "--surface", "--surface-2"]) expect(contrast(text, surface), `${text} on ${surface}`).toBeGreaterThanOrEqual(4.5);
    expect(contrast("--accent-fg", "--accent")).toBeGreaterThanOrEqual(4.5);
    expect(contrast("--accent", "--accent-soft")).toBeGreaterThanOrEqual(4.5);
  });
}
