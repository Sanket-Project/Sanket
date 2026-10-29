import { test, expect, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";

const evidence = path.resolve("../docs/audit/2026-10-29-premium-minimal");

// The real shell and stylesheet, isolated from customer data and authentication.
// Deliberately unavailable APIs exercise honest failure states, never fake health.
async function shell(page: Page, dark = false, screen?: string) {
  page.on("pageerror", error => console.error("Design harness:", error.message));
  await page.route("**/api/v1/**", route => route.fulfill({ status: 503, json: { detail: "Design test: source unavailable" } }));
  await page.route("**/__premium-review*", route => route.fulfill({ contentType: "text/html", body: `<!doctype html><html class="${dark ? "dark" : ""}"><head><meta name="viewport" content="width=device-width,initial-scale=1"></head><body><div id="root"></div><script type="module">
    import RefreshRuntime from '/@react-refresh';
    RefreshRuntime.injectIntoGlobalHook(window); window.$RefreshReg$ = () => {}; window.$RefreshSig$ = () => type => type; window.__vite_plugin_react_preamble_installed__ = true;
    await import('/e2e/design-harness.tsx');
  </script></body></html>` }));
  await page.goto(`/__premium-review${screen ? `?screen=${screen}` : ""}`);
  if (!screen) await expect(page.getByRole("heading", { name: "Planning workspace" })).toBeVisible();
}

for (const width of [390, 768, 1280, 1536]) {
  test(`light workspace has the approved palette and fits ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 960 });
    await shell(page);
    await expect(page.locator("#app-shell-root")).toHaveCSS("background-color", "rgb(248, 250, 252)");
    if (width >= 1024) {
      await expect(page.getByRole("complementary", { name: "Main navigation" })).toHaveCSS("background-color", "rgb(255, 255, 255)");
      await expect(page.getByRole("link", { name: "Dashboard", exact: true }).first()).toHaveCSS("color", "rgb(6, 72, 75)");
    } else {
      const opener = page.getByRole("button", { name: "Open navigation" });
      await opener.click();
      await expect(page.getByRole("searchbox", { name: "Search navigation" })).toBeFocused();
      await page.keyboard.press("Escape");
      await expect(opener).toBeFocused();
    }
    expect(await page.evaluate(() => {
      const main = document.getElementById("main-content")!;
      return main.scrollWidth <= main.clientWidth && document.documentElement.scrollWidth <= innerWidth;
    })).toBe(true);
    mkdirSync(evidence, { recursive: true });
    await page.screenshot({ path: path.join(evidence, `shell-light-${width}.png`) });
  });
}

test("failed alert sources do not claim that the business is healthy", async ({ page }) => {
  await shell(page);
  await page.getByRole("button", { name: "Open notifications" }).click();
  await expect(page.getByText("Alerts unavailable", { exact: true })).toBeVisible();
  await expect(page.getByText("All Systems Healthy", { exact: true })).toHaveCount(0);
});

test("dark mode and reduced motion keep the same usable hierarchy", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await shell(page, true);
  await expect(page.locator("#app-shell-root")).toHaveCSS("background-color", "rgb(16, 29, 37)");
  const button = page.getByRole("button", { name: "Review plan", exact: true });
  await expect(button).toHaveCSS("transition-duration", "0s");
  mkdirSync(evidence, { recursive: true });
  await page.screenshot({ path: path.join(evidence, "shell-dark-reduced-motion.png") });
});

test("static panels use the same compact radius without suggesting clickability", async ({ page }) => {
  await shell(page);
  const panel = page.locator('[aria-label="Business overview"]');
  await expect(panel).toHaveCSS("border-radius", "12px");
  const shadow = await panel.evaluate(el => getComputedStyle(el).boxShadow);
  await panel.hover();
  await expect(panel).toHaveCSS("box-shadow", shadow);
});

test("forecast legend visually distinguishes recorded demand from the prediction", async ({ page }) => {
  await shell(page, false, "ChartReview");
  const actual = page.getByText("Actual", { exact: true }).first().locator("span");
  await expect(actual).toHaveCSS("background-color", "rgb(18, 53, 72)");
  const expected = page.getByText("Expected", { exact: true }).first().locator("span");
  await expect(expected).toHaveCSS("border-top-color", "rgb(10, 153, 141)");
});

test("account popover closes with Escape and restores the trigger", async ({ page }) => {
  await shell(page);
  const trigger = page.getByRole("button", { name: "Open profile menu" });
  await trigger.click();
  await expect(page.getByRole("link", { name: "Subscription Plan" })).toBeVisible();
  await page.getByRole("link", { name: "Subscription Plan" }).focus();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("link", { name: "Subscription Plan" })).toHaveCount(0);
  await expect(trigger).toBeFocused();
});

const screens = ["Dashboard", "Products", "Skus", "Inventory", "Forecasts", "Decisions", "SalesAnalytics", "TrendAnalysis", "ROIDashboard", "FinancialImpact", "DataQuality", "ShortageAlerts", "Integrations", "Notifications", "Settings", "Profile", "Billing", "Webhooks", "LiveSales", "PharmaBatches", "ProductDetail", "SkuDetail", "Login", "ForgotPassword", "ResetPassword", "AcceptInvite", "Terms", "Privacy", "NotFound", "HybridForecasts", "Fashion", "Electronics", "Pharma", "Agriculture", "Hardware"];
screens.push("OnboardingIndustry", "OnboardingData", "OnboardingCalendar", "OnboardingTeam", "OnboardingBaseline", "ImportReview", "Landing");
for (const screen of screens) {
  for (const dark of [false, true]) {
    test(`${screen} ${dark ? "dark desktop" : "light mobile"} source-unavailable review`, async ({ page }) => {
      const errors: string[] = [];
      page.on("pageerror", error => errors.push(error.message));
      await page.setViewportSize({ width: dark ? 1280 : 390, height: 960 });
      await shell(page, dark, screen);
      await expect(page.locator("#root")).not.toBeEmpty();
      // All adapter requests have completed; this is the page's unavailable or
      // empty state, not a claim that populated production journeys passed.
      await page.waitForLoadState("networkidle");
      expect(errors).toEqual([]);
      expect(await page.evaluate(() => {
        const main = document.getElementById("main-content");
        return document.documentElement.scrollWidth <= innerWidth && (!main || main.scrollWidth <= main.clientWidth);
      })).toBe(true);
      if (["NotFound", "Terms", "Privacy"].includes(screen)) {
        await expect(page.getByRole("heading", { level: 1 })).toHaveCSS("color", dark ? "rgb(234, 243, 243)" : "rgb(16, 40, 63)");
      }
      if (screen === "Settings") {
        const profile = page.getByRole("tab", { name: "Profile", exact: true });
        await expect(profile).toBeVisible();
        await profile.focus();
        await page.keyboard.press("ArrowRight");
        await expect(page.getByRole("tab", { name: "Workspace", exact: true })).toBeFocused();
        await expect(page.getByRole("tab", { name: "Workspace", exact: true })).toHaveAttribute("aria-selected", "true");
      }
      if (screen === "HybridForecasts") {
        const emptyPanel = page.getByText("No hybrid projections active", { exact: true }).locator("..").locator("..");
        await expect(emptyPanel).toHaveCSS("background-image", "none");
      }
      if (screen.startsWith("Onboarding") && dark) await expect(page.getByRole("img", { name: "SANKET", exact: true })).toBeVisible();
      const oversized = page.locator('[class*="rounded-[20px]"][class*="bg-surface"]');
      for (const panel of await oversized.all()) await expect(panel).toHaveCSS("border-radius", "12px");
      mkdirSync(evidence, { recursive: true });
      await page.screenshot({ path: path.join(evidence, `${screen}-${dark ? "dark-desktop" : "light-mobile"}.png`), fullPage: true });
    });
  }
}

for (const screen of ["Profile", "Settings"]) {
  test(`${screen} avatar uses the readable dark accent foreground`, async ({ page }) => {
    await shell(page, true, screen);
    await expect(page.locator(".bg-gradient-accent span").first()).toHaveCSS("color", "rgb(11, 48, 47)");
  });
}

test("import action uses the readable dark accent foreground", async ({ page }) => {
  await shell(page, true, "ImportDialog");
  await expect(page.getByRole("button", { name: "Create item" })).toHaveCSS("color", "rgb(11, 48, 47)");
});

test("account popover avatar uses the readable dark accent foreground", async ({ page }) => {
  await shell(page, true);
  await page.getByRole("button", { name: "Open profile menu" }).click();
  await expect(page.locator('div.rounded-full[style*="var(--accent)"]')).toHaveCSS("color", "rgb(11, 48, 47)");
});

for (const width of [390, 768, 1280, 1672, 1680]) {
  test(`reference planning composition with synthetic review data at ${width}px`, async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    await page.setViewportSize({ width, height: 941 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/e2e/review.html?screen=Dashboard&fixture=planning");
    await expect(page.getByRole("heading", { name: "Turn demand signals into confident decisions." })).toBeVisible();
    await expect(page.getByRole("table", { name: "Recorded stock coverage and data confidence" })).toBeVisible();
    await page.evaluate(async () => { await document.fonts.ready; });
    expect(await page.locator(".planning-hero-art").evaluate((el: HTMLImageElement) => el.complete && el.naturalWidth > 0)).toBe(true);
    expect(await page.locator("#main-content").evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
    expect(errors).toEqual([]);
    if (width >= 1672) {
      expect((await page.locator(".planning-forecast").boundingBox())!.y).toBeLessThan(480);
      await expect(page.getByRole("heading", { name: "Decision readiness", exact: true })).toBeInViewport();
      await expect(page.getByText("Review stock coverage before placing an order", { exact: true })).toBeInViewport();
      await expect(page.getByRole("button", { name: "Review inventory", exact: true })).toBeInViewport();
    }
    mkdirSync(evidence, { recursive: true });
    await page.screenshot({ path: path.join(evidence, `reference-planning-${width}.png`), fullPage: true });
  });
}
