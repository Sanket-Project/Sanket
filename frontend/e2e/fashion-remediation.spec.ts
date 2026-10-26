/** Real isolated services, synthetic data; opt in with E2E_REMEDIATION=1. */
import { test, expect } from "@playwright/test";
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import path from "node:path";
import ExcelJS from "exceljs";
import Papa from "papaparse";

const evidenceDir = path.resolve("../docs/audit/2026-10-26-fashion-remediation/e2e");
const fixtureFile = path.join(evidenceDir, "fixture.json");

test.describe("Synthetic fashion remediation", () => {
  test.skip(process.env.E2E_REMEDIATION !== "1", "Explicit isolated-stack opt-in required");
  test("import → replay → forecast → backtest → inventory → decision → scenario → export", async ({ page }) => {
    test.setTimeout(900_000);
    page.setDefaultTimeout(30_000);
    expect(new URL(String(test.info().project.use.baseURL)).origin).toBe("http://127.0.0.1:5174");
    mkdirSync(evidenceDir, { recursive: true });
    const fixture = JSON.parse(readFileSync(fixtureFile, "utf8"));
    expect(fixture.synthetic).toBe(true);
    const evidence: Record<string, unknown> = { synthetic: true };
    const screenshot = async (name: string) => page.screenshot({ path: path.join(evidenceDir, `${name}.png`), fullPage: true });
    const responseFor = (suffix: string) => page.waitForResponse((r) => r.url().includes(suffix) && r.request().method() === "POST", { timeout: 240_000 });

    await page.goto("/login");
    await page.locator("#signin-workspace").fill(fixture.slug);
    await page.locator("#signin-email").fill(fixture.email);
    await page.locator("#signin-password").fill(fixture.password);
    await page.locator('form[aria-label="Sign in form"] button[type="submit"]').click();
    await page.waitForURL("**/workspace", { timeout: 30_000 });

    await page.goto("/workspace/integrations");
    const importFile = async (filename: string) => {
      await page.getByRole("button").filter({ has: page.getByRole("heading", { name: /CSV/ }) }).first().click();
      await page.locator('input[type="file"]').setInputFiles(path.join(evidenceDir, filename));
      await page.getByRole("radio", { name: /Daily or weekly totals/ }).check();
      const uploaded = responseFor("/integrations/upload");
      await page.getByRole("button", { name: "Confirm & Import Data" }).click();
      const response = await uploaded;
      expect(response.status()).toBe(200);
      const body = await response.json();
      expect(body.identity_mode).toBe("period");
      expect(body.errors).toEqual([]);
      await page.getByRole("button", { name: "Close dialog" }).click();
      return body;
    };
    evidence.training = await importFile("synthetic-training-sales.csv");
    const replay = await importFile("synthetic-training-sales.csv");
    expect(replay.rows_inserted).toBe(0);
    expect(replay.rows_updated).toBe(0);
    expect(replay.rows_unchanged).toBeGreaterThan(0);
    await expect(page.getByText(/0 new · .* already imported · 0 corrected/).first()).toBeVisible();
    evidence.replay = replay;
    await screenshot("01-replay");
    evidence.heldout = await importFile("synthetic-heldout-sales.csv");

    const forecastResponse = responseFor("/forecasts/generate");
    await page.goto("/workspace/forecasts");
    const forecast = await forecastResponse;
    expect(forecast.status()).toBe(200);
    const forecastBody = await forecast.json();
    expect(forecastBody.source).toBe("chronos_zero_shot");
    expect(forecastBody.calendar).toBe("W-MON-UTC");
    expect(forecastBody.n_series).toBe(6);
    expect(forecastBody.rows).toHaveLength(72);
    expect(forecastBody.omitted).toContainEqual(expect.objectContaining({
      sku_id: fixture.skus["UNSOLD-5XL"].id, reason: "no_sales_history",
    }));
    evidence.forecast = forecastBody;
    await expect(page.getByText(/6 SKUs forecast/).first()).toBeVisible();
    await expect(page.getByText(/Chronos zero-shot/).first()).toBeVisible();
    await expect(page.getByText(/UNSOLD-5XL/)).toBeVisible();
    await expect(page.getByText(/Never sold — a forecast needs sales history/i).first()).toBeVisible();
    await expect(page.locator(".recharts-wrapper")).toHaveCount(6);
    await screenshot("02-forecasts");
    await page.locator(".recharts-wrapper").first().scrollIntoViewIfNeeded();
    await screenshot("02b-forecast-charts");
    await page.getByText(/Never sold — a forecast needs sales history/i).scrollIntoViewIfNeeded();
    await screenshot("02c-forecast-omission");

    await page.goto("/workspace/forecast-accuracy");
    await expect(page.getByRole("heading", { name: "Production accuracy", exact: true })).toBeVisible();
    await page.getByLabel(/Forecast as if it were/).fill("2026-08-31");
    const backtestResponse = responseFor("/forecasts/backtest");
    // This refresh occurs only AFTER the real CPU model completes, so it shares
    // the model-call budget; ordinary UI actions still have a 30-second limit.
    const accuracyResponse = page.waitForResponse((r) => r.url().includes("/forecast/accuracy") && r.request().method() === "GET", { timeout: 240_000 });
    await page.getByRole("button", { name: "Run backtest" }).click();
    const backtest = await backtestResponse;
    expect(backtest.status()).toBe(200);
    const backtestBody = await backtest.json();
    expect(backtestBody.calendar).toBe("W-MON-UTC");
    expect(backtestBody.rows).toHaveLength(48);
    const actuals = new Map<string, number>();
    const heldout = Papa.parse<Record<string, string>>(readFileSync(path.join(evidenceDir, "synthetic-heldout-sales.csv"), "utf8"), { header: true, skipEmptyLines: true });
    for (const row of heldout.data) {
      const key = `${fixture.skus[row.sku].id}:${row.date}`;
      actuals.set(key, (actuals.get(key) ?? 0) + Number(row.quantity));
    }
    let denominator = 0;
    let numerator = 0;
    for (const row of backtestBody.rows) {
      const key = `${row.sku_id}:${row.forecast_date.slice(0, 10)}`;
      expect(actuals.has(key)).toBe(true);
      const actual = actuals.get(key)!;
      numerator += Math.abs(row.p50 - actual);
      denominator += actual;
    }
    const independentlyComputedWape = numerator / denominator * 100;
    const accuracy = await (await accuracyResponse).json();
    const scored = accuracy.backtest.runs.find((r: { run_id: string }) => r.run_id === backtestBody.run_id);
    expect(scored).toBeDefined();
    expect(scored.cutoff).toBe("2026-08-31");
    expect(scored.points).toBe(48);
    expect(scored.skus).toBe(6);
    // The API rounds percentages to 2 decimals and stores predictions at 4 decimals.
    const roundingBound = 0.005 + backtestBody.rows.length * 0.00005 / denominator * 100;
    expect(Math.abs(scored.wape - independentlyComputedWape)).toBeLessThanOrEqual(roundingBound);
    evidence.backtest = { ...backtestBody, independentlyComputedWape, scored };
    await expect(page.getByText(/Backtest from 31 Aug 2026/).first()).toBeVisible({ timeout: 30_000 });
    await expect(page.getByText(`48 points · 6 SKUs · WAPE ${scored.wape.toFixed(1)}%`, { exact: false }).first()).toBeVisible();
    await page.getByText(/Backtest from 31 Aug 2026/).first().scrollIntoViewIfNeeded();
    await screenshot("03-accuracy");

    const coverageResponse = page.waitForResponse((r) => r.url().includes("/inventory/coverage") && r.status() === 200);
    await page.goto("/workspace/inventory");
    const coverage = await (await coverageResponse).json();
    const kurti = coverage.skus.find((s: { sku_code: string }) => s.sku_code === "KURTI-M");
    expect(kurti.locations).toHaveLength(2);
    expect(kurti.locations.every((l: { cover_days: number | null }) => l.cover_days !== null)).toBe(true);
    expect(kurti.locations[0].cover_days).not.toBe(kurti.locations[1].cover_days);
    evidence.coverage = coverage;
    await expect(page.getByText(/Store cover/).first()).toBeVisible();
    await expect(page.getByText(/Boduppal/).first()).toBeVisible();
    await expect(page.getByText(/Alwal/).first()).toBeVisible();
    await page.getByPlaceholder("Filter by SKU code or location…").fill("KURTI-M");
    await screenshot("04-inventory");

    await page.goto("/workspace/decisions");
    const refreshed = responseFor("/decisions/refresh");
    await page.getByRole("button", { name: "Recompute from latest forecast" }).click();
    const refresh = await refreshed;
    expect(refresh.status()).toBe(200);
    const refreshBody = await refresh.json();
    expect(refreshBody.generated).toBeGreaterThan(0);
    evidence.decisions = refreshBody;
    await page.getByRole("button", { name: "Show working" }).first().click();
    const accepted = page.waitForResponse((r) => /\/decisions\/[^/]+\/accept/.test(r.url()) && r.request().method() === "POST");
    await page.getByRole("button", { name: "Accept", exact: true }).first().click();
    const accept = await accepted;
    expect(accept.status()).toBe(200);
    evidence.accepted = await accept.json();
    await screenshot("05-decision");

    const presetsPromise = page.waitForResponse((r) => r.url().includes("/scenarios/presets"));
    await page.goto("/workspace/scenarios");
    const presetsResponse = await presetsPromise;
    const presets = await presetsResponse.json();
    const scenarioResponse = page.waitForResponse((r) => r.url().includes("/scenarios/simulate")
      && r.request().method() === "POST" && r.request().postDataJSON()?.preset === presets.presets[0].key);
    await page.getByRole("button", { name: presets.presets[0].label, exact: true }).click();
    const scenario = await scenarioResponse;
    expect(scenario.status()).toBe(200);
    evidence.scenario = await scenario.json();
    await screenshot("06-scenario");

    const finalForecast = responseFor("/forecasts/generate");
    await page.goto("/workspace/forecasts");
    expect((await finalForecast).status()).toBe(200);
    const downloadPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: "Excel", exact: true }).click();
    const download = await downloadPromise;
    const exportPath = path.join(evidenceDir, "forecast.xlsx");
    await download.saveAs(exportPath);
    const workbook = new ExcelJS.Workbook();
    await workbook.xlsx.readFile(exportPath);
    const headers = workbook.worksheets[0].getRow(1).values;
    expect(headers).toContain("Week start (Mon, UTC)");
    expect(headers).toContain("Week end (Sun)");
    workbook.worksheets[0].eachRow((row, index) => {
      if (index === 1) return;
      const start = new Date(`${row.getCell(3).text}T00:00:00Z`);
      const end = new Date(`${row.getCell(4).text}T00:00:00Z`);
      expect(start.getUTCDay()).toBe(1);
      expect(end.getUTCDay()).toBe(0);
      expect(end.getTime() - start.getTime()).toBe(6 * 24 * 60 * 60 * 1000);
    });
    evidence.export = { filename: download.suggestedFilename(), rows: workbook.worksheets[0].rowCount, headers };
    writeFileSync(path.join(evidenceDir, "journey-evidence.json"), JSON.stringify(evidence, null, 2));
    await screenshot("07-export");
  });
});
