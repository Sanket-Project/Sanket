import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const rootCss = readFileSync("src/styles/index.css", "utf8");
const landingCss = readFileSync("src/styles/landing.css", "utf8");
const liveConsoleCss = readFileSync("src/pages/landing/live-console.css", "utf8");
const html = readFileSync("index.html", "utf8");

function userFacingSources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return userFacingSources(path);
    if (!/\.(css|tsx)$/.test(name) || /\.test\./.test(name)) return [];
    return [readFileSync(path, "utf8")];
  });
}

describe("application typography contract", () => {
  it("loads the three approved families once from the document head", () => {
    const fontStylesheets = html.match(/href="https:\/\/fonts\.googleapis\.com\/css2\?[^"]+"/g) ?? [];

    expect(fontStylesheets).toHaveLength(1);
    expect(fontStylesheets[0]).toContain("family=IBM+Plex+Mono");
    expect(fontStylesheets[0]).toContain("family=IBM+Plex+Sans");
    expect(fontStylesheets[0]).toContain("family=Space+Grotesk");
  });

  it("uses IBM Plex Sans for UI, Space Grotesk for headings, and IBM Plex Mono for data", () => {
    expect(rootCss).toMatch(/body,[\s\S]*font-family:\s*"IBM Plex Sans"/);
    expect(rootCss).toMatch(/\.font-heading, \.font-display[\s\S]*font-family:\s*"Space Grotesk"/);
    expect(rootCss).toMatch(/\.font-mono, \.tabular, \.metric[\s\S]*font-family:\s*"IBM Plex Mono"/);
    expect(liveConsoleCss).toContain('--lc-font-display: "Space Grotesk"');
    expect(liveConsoleCss).toContain('--lc-font-body: "IBM Plex Sans"');
    expect(liveConsoleCss).toContain('--lc-font-mono: "IBM Plex Mono"');
    expect(landingCss).toContain("font-family: 'IBM Plex Sans'");
  });

  it("contains no competing font families or component-level font overrides", () => {
    const source = [html, ...userFacingSources("src")].join("\n");

    expect(source).not.toMatch(
      /(?:Geist Sans|DM\+Serif\+Display|DM Serif Display|Instrument\+Serif|Instrument Serif|JetBrains\+Mono|JetBrains Mono|SF Pro Display)/,
    );
    expect(source).not.toMatch(/fontFamily\s*:/);
  });
});
