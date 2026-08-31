import { test, expect } from "@playwright/test";

test.describe("SANKET Authentication Flow", () => {
  test("should successfully login with seeded credentials and reach the dashboard", async ({ page }) => {
    // Go to the login page
    await page.goto("/login");

    // Fill in the workspace slug, email, and password
    await page.fill("#signin-workspace", "sanket-dev");
    await page.fill("#signin-email", "owner@sanket-dev.com");
    await page.fill("#signin-password", "Dev@Sanket2024!");

    // Click the sign-in submit button. Scoped to the "Sign in form" — the page
    // also has a segmented tab toggle button whose label is also "Sign in",
    // which would otherwise make this locator ambiguous (strict-mode violation).
    await page.click('form[aria-label="Sign in form"] button[type="submit"]');

    // Successful login lands on /workspace (the AppShell layout route; Dashboard
    // is its index child, so the URL itself stays /workspace, not /dashboard).
    await page.waitForURL("**/workspace", { timeout: 10000 });

    // Assert that the dashboard UI elements are visible
    await expect(page.locator("aside")).toBeVisible();
    await expect(page.locator("nav")).toBeVisible();
  });

  test("should successfully login via sandbox button on landing page", async ({ page }) => {
    // Go to the landing page
    await page.goto("/");

    // Click the primary "Try Live Sandbox" button
    const sandboxButton = page.locator("button:has-text('Try Live Sandbox'), a:has-text('Try Live Sandbox')").first();
    await sandboxButton.click();

    // The modal no longer asks which industry to explore. It used to list all
    // five, but the choice was cosmetic — every visitor landed in the same
    // workspace regardless, and the picker only set client-side state.
    await expect(page.locator("text=Explore a Live Sandbox")).toBeVisible();
    await page.click("button:has-text('Launch the sandbox')");

    // The sandbox flow also lands on /workspace (see LandingPage.tsx handleSandbox).
    await page.waitForURL("**/workspace", { timeout: 10000 });

    // Assert that the dashboard layout is visible
    await expect(page.locator("aside")).toBeVisible();
  });
});
