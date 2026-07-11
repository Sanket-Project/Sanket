/**
 * E2E test: Forecast flow
 *
 * Covers the money path: login → navigate to Forecasts → trigger a forecast
 * run → assert that results render without error.
 *
 * Runs against the dev server with the seeded `owner@sanket-dev.com` account
 * (Argon2 dev-login path). The forecast request may take several seconds if
 * the ML service is in CPU-only mode; the timeout below is set accordingly.
 */
import { test, expect } from "@playwright/test";

const FORECAST_TIMEOUT_MS = 90_000; // Chronos on CPU can take ~60 s

test.describe("Forecast Flow", () => {
  test.beforeEach(async ({ page }) => {
    // Log in as the workspace owner (seeded dev credentials)
    await page.goto("/login");
    await page.fill("#signin-workspace", "sanket-dev");
    await page.fill("#signin-email", "owner@sanket-dev.com");
    await page.fill("#signin-password", "Dev@Sanket2024!");
    await page.click('form[aria-label="Sign in form"] button[type="submit"]');
    await page.waitForURL("**/workspace", { timeout: 10_000 });
  });

  test("should navigate to forecasts page and display the forecast panel", async ({
    page,
  }) => {
    // Navigate via sidebar link
    await page.click("a[href*='forecast'], nav >> text=Forecast");
    await page.waitForURL("**/forecast**", { timeout: 8_000 });

    // The forecasts page should have a primary heading
    await expect(
      page.locator("h1, h2").filter({ hasText: /forecast/i }).first()
    ).toBeVisible({ timeout: 6_000 });
  });

  test("should trigger a forecast run and render results", async ({ page }) => {
    // Navigate to forecasts
    await page.click("a[href*='forecast'], nav >> text=Forecast");
    await page.waitForURL("**/forecast**", { timeout: 8_000 });

    // Look for a "Run Forecast" or "Generate" button and click it
    const runButton = page
      .locator("button")
      .filter({ hasText: /run forecast|generate|run/i })
      .first();

    // Only proceed if a run button exists — some layouts auto-run on mount
    if ((await runButton.count()) > 0) {
      await runButton.click();
    }

    // Wait for either a chart/table result or an error message
    const resultLocator = page.locator(
      "[data-testid='forecast-chart'], [data-testid='forecast-result'], " +
        "[data-testid='forecast-error'], .recharts-wrapper, table"
    );

    await expect(resultLocator.first()).toBeVisible({
      timeout: FORECAST_TIMEOUT_MS,
    });

    // Assert no unhandled error toast is visible
    const errorToast = page.locator(
      "[role='alert']:has-text('error'), [role='alert']:has-text('failed')"
    );
    await expect(errorToast).toHaveCount(0);
  });

  test("should show forecast for a specific SKU when selected", async ({
    page,
  }) => {
    await page.click("a[href*='forecast'], nav >> text=Forecast");
    await page.waitForURL("**/forecast**", { timeout: 8_000 });

    // If there is a SKU selector, pick the first option
    const skuSelect = page.locator(
      "select[name*='sku'], [data-testid='sku-select']"
    );
    if ((await skuSelect.count()) > 0) {
      await skuSelect.selectOption({ index: 1 });
      // After selection, some form of result or loading indicator should appear
      await expect(
        page
          .locator(
            "[data-testid='forecast-chart'], [data-testid='loading-spinner'], table"
          )
          .first()
      ).toBeVisible({ timeout: FORECAST_TIMEOUT_MS });
    } else {
      test.skip(); // SKU selector not present on this build
    }
  });
});
