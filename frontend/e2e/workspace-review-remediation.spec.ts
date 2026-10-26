/**
 * Workspace-review remediation journeys (docs/audit/2026-10-26-workspace-review).
 *
 * Runs ONLY against the isolated synthetic stack provisioned by
 * docs/audit/2026-10-26-workspace-review/remediation/provision_fixture.py and
 * served by run_fixture_backend.py (:8010) + run_fixture_frontend.mjs (:5174).
 * Opt in with E2E_REVIEW=1 E2E_BASE_URL=http://localhost:5174 E2E_SKIP_WEBSERVER=1.
 */
import { test, expect, type Page } from "@playwright/test";
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";

const evidenceDir = path.resolve("../docs/audit/2026-10-26-workspace-review/remediation");
const fixture = JSON.parse(readFileSync(path.join(evidenceDir, "fixture.json"), "utf8"));
const results: Record<string, unknown> = {};

type Workspace = { slug: string; email: string; password: string; tenant_id: string; recommendations: Record<string, string> };
const A: Workspace = fixture.workspaces.A;
const B: Workspace = fixture.workspaces.B;

const shot = (page: Page, name: string, fullPage = true) =>
  page.screenshot({ path: path.join(evidenceDir, `${name}.png`), fullPage });

async function signIn(page: Page, ws: Workspace) {
  await page.goto("/login");
  await page.locator("#signin-workspace").fill(ws.slug);
  await page.locator("#signin-email").fill(ws.email);
  await page.locator("#signin-password").fill(ws.password);
  await page.locator('form[aria-label="Sign in form"] button[type="submit"]').click();
  await page.waitForURL("**/workspace", { timeout: 30_000 });
}

/** Contrast ratio of an element's text against its effective (composited) background. */
async function contrast(page: Page, selector: string, pseudo?: string) {
  return page.evaluate(([sel, ps]) => {
    const el = document.querySelector(sel) as HTMLElement;
    const parse = (c: string) => (c.match(/[\d.]+/g) ?? ["0", "0", "0", "0"]).map(Number);
    const lum = ([r, g, b]: number[]) => {
      const f = (v: number) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; };
      return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
    };
    const layers: number[][] = [];
    for (let node: HTMLElement | null = el; node; node = node.parentElement) {
      const [r, g, b, a = 1] = parse(getComputedStyle(node).backgroundColor);
      if (a > 0) layers.push([r, g, b, a]);
      if (a >= 1) break;
    }
    let bg = [255, 255, 255];
    for (const [r, g, b, a] of layers.reverse()) bg = [r * a + bg[0] * (1 - a), g * a + bg[1] * (1 - a), b * a + bg[2] * (1 - a)];
    const [fr, fg, fb, fa = 1] = parse(getComputedStyle(el, ps || null).color);
    const fgc = [fr * fa + bg[0] * (1 - fa), fg * fa + bg[1] * (1 - fa), fb * fa + bg[2] * (1 - fa)];
    const [l1, l2] = [lum(fgc), lum(bg)].sort((x, y) => y - x);
    return Math.round(((l1 + 0.05) / (l2 + 0.05)) * 100) / 100;
  }, [selector, pseudo ?? ""] as const);
}

test.describe("Workspace review remediation (isolated synthetic stack)", () => {
  test.skip(process.env.E2E_REVIEW !== "1", "Explicit isolated-stack opt-in required");
  test.beforeAll(() => {
    expect(fixture.synthetic).toBe(true);
    expect(fixture.database).toBe("sanket_review_fixture");
    mkdirSync(evidenceDir, { recursive: true });
  });
  test.afterAll(() => writeFileSync(path.join(evidenceDir, "e2e-results.json"), JSON.stringify(results, null, 2)));

  test("F1: switching between same-industry accounts never shows the previous account's rows", async ({ page }) => {
    await signIn(page, A);
    await page.goto("/workspace/decisions");
    await expect(page.getByText("A-only: raise a purchase order for 40 units")).toBeVisible();
    // Mark this document: if the switch below caused a reload the marker would vanish.
    await page.evaluate(() => { (window as unknown as { __sameDocument: boolean }).__sameDocument = true; });

    await page.getByRole("button", { name: "Sign out" }).click();
    await page.waitForURL("**/login");
    await page.locator("#signin-workspace").fill(B.slug);
    await page.locator("#signin-email").fill(B.email);
    await page.locator("#signin-password").fill(B.password);
    await page.locator('form[aria-label="Sign in form"] button[type="submit"]').click();
    await page.waitForURL("**/workspace");
    await page.getByRole("link", { name: /^Decisions/ }).first().click();

    await expect(page.getByText("B-only: raise a purchase order for 15 units")).toBeVisible();
    await expect(page.getByText(/A-only/)).toHaveCount(0);
    const sameDocument = await page.evaluate(() => (window as unknown as { __sameDocument?: boolean }).__sameDocument === true);
    expect(sameDocument).toBe(true);
    results.f1 = { sameDocument, aRowsVisibleToB: 0 };
    await shot(page, "r01-account-switch-b-decisions");
  });

  test("F2: expired recommendations are excluded and cannot be accepted", async ({ page }) => {
    await signIn(page, A);
    const token = await page.evaluate(() => localStorage.getItem("sanket.dev.token"));
    const headers = { Authorization: `Bearer ${token}` };
    const open = await (await page.request.get("/api/v1/decisions?status=open", { headers })).json();
    const expired = await (await page.request.get("/api/v1/decisions?status=expired", { headers })).json();
    const accept = await page.request.post(`/api/v1/decisions/${A.recommendations.expired}/accept`, { headers, data: {} });
    const openIds = open.decisions.map((d: { id: string }) => d.id);
    expect(openIds).not.toContain(A.recommendations.expired);
    expect(expired.decisions.map((d: { id: string }) => d.id)).toContain(A.recommendations.expired);
    expect(accept.status()).toBe(409);
    results.f2 = { openExcludesExpired: true, acceptStatus: accept.status(), detail: (await accept.json()).detail };
  });

  test("F3/F6/F7: simulator withholds unknown money, flags advisory inputs and caps the horizon", async ({ page }) => {
    await signIn(page, A);
    const simulated = page.waitForResponse((r) => r.url().includes("/scenarios/simulate"));
    await page.goto("/workspace/scenarios");
    const body = await (await simulated).json();
    await expect(page.getByText("Advisory", { exact: true })).toBeVisible();
    await expect(page.getByText(/simulation stops at 12 weeks/)).toBeVisible();
    await expect(page.getByText(/SKUs missing unit cost/)).toBeVisible();
    await expect(page.getByRole("slider", { name: "Horizon" })).toHaveAttribute("max", "12");
    results.f3_f6_f7 = {
      horizon: body.config, readiness: body.readiness, valuation: body.valuation_coverage,
      baselineMargin: body.baseline.gross_margin, purchaseSpendImpact: body.impact.purchase_spend,
    };
    expect(body.baseline.gross_margin).toBeNull();
    await shot(page, "r02-scenario-desktop");
  });

  for (const width of [320, 390, 768]) {
    test(`F12: scenario page has no page-level horizontal overflow at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 844 });
      await signIn(page, A);
      await page.goto("/workspace/scenarios");
      await expect(page.getByText("Levers")).toBeVisible();
      await page.waitForTimeout(1500);
      const m = await page.evaluate(() => {
        const main = document.getElementById("main-content")!;
        const sliders = Array.from(document.querySelectorAll('input[type="range"]'));
        return {
          clientWidth: main.clientWidth,
          scrollWidth: main.scrollWidth,
          viewport: window.innerWidth,
          maxSliderRight: Math.max(...sliders.map((s) => s.getBoundingClientRect().right)),
        };
      });
      results[`f12_${width}`] = m;
      expect(m.scrollWidth).toBeLessThanOrEqual(m.clientWidth);
      expect(m.maxSliderRight).toBeLessThanOrEqual(m.viewport);
      await shot(page, `r03-scenario-${width}`);
    });
  }

  for (const theme of ["light", "dark"] as const) {
    test(`F10/F11: mobile drawer keyboard behaviour and search contrast (${theme})`, async ({ page }) => {
      await page.addInitScript((t) => localStorage.setItem("sanket.theme", t), theme);
      await page.setViewportSize({ width: 390, height: 844 });
      await signIn(page, A);
      const drawer = page.locator('aside[aria-label="Main navigation"]');
      await expect(drawer).toHaveAttribute("inert", "");

      const opener = page.getByRole("button", { name: "Open navigation" });
      await opener.focus();
      await page.keyboard.press("Enter");
      const search = page.getByRole("searchbox", { name: "Search navigation" });
      await expect(search).toBeFocused();
      await expect(page.locator("#app-main-column")).toHaveAttribute("inert", "");

      // Tab through every control: focus must never leave the drawer.
      const escaped: string[] = [];
      for (let i = 0; i < 30; i++) {
        await page.keyboard.press("Tab");
        const inside = await page.evaluate(() =>
          Boolean(document.activeElement?.closest('aside[aria-label="Main navigation"]')));
        if (!inside) escaped.push(await page.evaluate(() => document.activeElement?.outerHTML.slice(0, 80) ?? ""));
      }
      expect(escaped).toEqual([]);

      await search.focus();
      await page.keyboard.type("dec");
      const text = await contrast(page, 'input[aria-label="Search navigation"]');
      const placeholderInput = await page.evaluate(() => {
        const el = document.querySelector('input[aria-label="Search navigation"]') as HTMLInputElement;
        el.value = "";
        el.dispatchEvent(new Event("input", { bubbles: true }));
        return true;
      });
      const placeholder = await contrast(page, 'input[aria-label="Search navigation"]', "::placeholder");
      await shot(page, `r04-mobile-drawer-${theme}`, false);

      await page.keyboard.press("Escape");
      await expect(opener).toBeFocused();
      await expect(drawer).toHaveAttribute("inert", "");
      results[`f10_f11_${theme}`] = { textContrast: text, placeholderContrast: placeholder, escapedFocus: escaped.length, placeholderInput };
      expect(text).toBeGreaterThanOrEqual(4.5);
      expect(placeholder).toBeGreaterThanOrEqual(4.5);
    });
  }

  test("F15: new pages open at the top; Back restores the previous position", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 600 });
    await signIn(page, A);
    await page.goto("/workspace/inventory");
    await expect(page.getByText(/Stock decisions/)).toBeVisible();
    await page.evaluate(() => { document.getElementById("main-content")!.scrollTop = 500; });
    const before = await page.evaluate(() => document.getElementById("main-content")!.scrollTop);
    await page.getByRole("link", { name: /SYN-A-JEANS|raise a purchase order/i }).first().click();
    await page.waitForURL("**/workspace/decisions");
    const afterPush = await page.evaluate(() => document.getElementById("main-content")!.scrollTop);
    await page.goBack();
    await page.waitForURL("**/workspace/inventory");
    await expect(page.getByText(/Stock decisions/)).toBeVisible();
    await page.waitForTimeout(500);
    const afterBack = await page.evaluate(() => document.getElementById("main-content")!.scrollTop);
    results.f15 = { before, afterPush, afterBack };
    expect(afterPush).toBe(0);
    expect(afterBack).toBe(before);
  });

  test("F9/F14/F16: inventory refresh refetches cover; provenance, lead time and excess are explicit", async ({ page }) => {
    await signIn(page, A);
    await page.goto("/workspace/inventory");
    await expect(page.getByText(/Synthetic fixture · as of/).first()).toBeVisible();
    await expect(page.getByText(/Lead time assumed \(14-day default\)/).first()).toBeVisible();
    await expect(page.getByText("Excess", { exact: true }).first()).toBeVisible();
    await expect(page.getByText(/Pause reorders, review inbound stock/).first()).toBeVisible();
    await expect(page.getByText("Real", { exact: true })).toHaveCount(0);
    const coverage = page.waitForResponse((r) => r.url().includes("/inventory/coverage"));
    const decisions = page.waitForResponse((r) => r.url().includes("/decisions?"));
    await page.getByRole("button", { name: /^Refresh$/ }).click();
    results.f9 = { coverageRefetched: (await coverage).status(), decisionsRefetched: (await decisions).status() };
    await shot(page, "r05-inventory");
  });

  test("Dashboard: composition, honest forecast failure and weekly labelling", async ({ page }) => {
    // Registered before sign-in: the dashboard requests history as it mounts.
    const historyResponse = page.waitForResponse((r) => r.url().includes("/analytics/sales/timeseries"));
    await signIn(page, A);
    await expect(page.getByRole("link", { name: /low-confidence SKU/ })).toBeVisible();
    await expect(page.getByText(/not measured forecast accuracy/)).toBeVisible();
    await expect(page.getByText(/sum of per-SKU P10–P90 ranges/)).toBeVisible();
    await expect(page.getByText(/Forecast service unavailable|units \/ week/).first()).toBeVisible();
    const history = await historyResponse;
    results.f4 = { url: history.url() };
    expect(history.url()).toContain("granularity=week");
    await shot(page, "r06-dashboard");
  });
});
