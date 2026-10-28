import { test, expect } from "@playwright/test";
import { mkdirSync } from "node:fs";
import path from "node:path";

// Render the real page and stylesheet in isolation. All API data below is
// explicitly synthetic test data; no workspace or customer records are changed.
const evidence = path.resolve("../docs/audit/2026-10-28-sales-analytics");
const report = {
  industry: "fashion", currency: "INR", imported_at: "2026-10-28",
  sales: { period: "1–25 October 2026", net_amount: 1248000, net_units: 2840, rows: 75, stores: [
    { name: "Jubilee Hills", net_amount: 648000, net_units: 1430 },
    { name: "Banjara Hills", net_amount: 420000, net_units: 970 },
    { name: "Kondapur", net_amount: 180000, net_units: 440 },
  ] },
  gross_profit: { period: "1 January–25 October 2026", net_sales: 5000000, sales_ex_tax: 4500000,
    cogs_ex_tax: 3000000, profit: 1500000, margin_pct: 33.33, rows: 3,
    stores: [{ name: "Jubilee Hills", profit: 850000, sales_ex_tax: 2400000 }, { name: "Banjara Hills", profit: 650000, sales_ex_tax: 2100000 }],
    top_skus: [{ sku: "COTTON-KURTA-M", profit: 250000, units: 500 }] },
  purchases: { period: "January–October 2026", net_amount: 3000000, net_units: 5000, rows: 10,
    suppliers: [{ name: "Synthetic supplier", net_amount: 3000000, net_units: 5000 }] },
  limitations: ["Dated SKU sales are unavailable in these aggregate reports."], sources: ["Synthetic design review.xlsx"],
};
const bucket = { units_sold: 2840, gross_revenue: 1248000, net_revenue: 1248000, currency: "INR",
  revenue_by_currency: { INR: 1248000 }, returns: 12, transactions: 780, period_start: "2026-10-01", revenue_delta: 0.15, units_delta: 0.1 };

for (const mode of ["imported", "transactions"] as const) {
  for (const size of ["desktop", "mobile"] as const) {
    for (const dark of [false, true]) {
      test(`${mode} ${size} ${dark ? "dark" : "light"} stays readable`, async ({ page }) => {
        mkdirSync(evidence, { recursive: true });
        await page.setViewportSize(size === "mobile" ? { width: 375, height: 812 } : { width: 1440, height: 1000 });
        const errors: string[] = [];
        page.on("pageerror", error => { errors.push(error.message); console.error(error.message); });
        await page.route("**/__sales-design-review", route => route.fulfill({ contentType: "text/html", body: `<!doctype html><html class="${dark ? "dark" : ""}"><head><meta name="viewport" content="width=device-width, initial-scale=1"></head><body><main style="max-width:1200px;margin:auto;padding:24px"><p style="margin-bottom:16px">Synthetic design-review data</p><div id="root"></div></main><script type="module">
          import RefreshRuntime from '/@react-refresh';
          RefreshRuntime.injectIntoGlobalHook(window);
          window.$RefreshReg$ = () => {};
          window.$RefreshSig$ = () => (type) => type;
          window.__vite_plugin_react_preamble_installed__ = true;
          await import('/@vite/client');
          await import('/src/styles/index.css');
          const React = (await import('/node_modules/.vite/deps/react.js')).default;
          const { createRoot } = (await import('/node_modules/.vite/deps/react-dom_client.js')).default;
          const { QueryClient, QueryClientProvider } = await import('/node_modules/.vite/deps/@tanstack_react-query.js');
          const { MemoryRouter } = await import('/node_modules/.vite/deps/react-router-dom.js');
          const { useAuthStore } = await import('/src/stores/auth.ts');
          useAuthStore.setState({ industry: 'fashion' });
          const { SalesAnalyticsPage } = await import('/src/pages/SalesAnalytics.tsx');
          createRoot(document.getElementById('root')).render(React.createElement(QueryClientProvider, {client:new QueryClient({defaultOptions:{queries:{retry:false}}})}, React.createElement(MemoryRouter, null, React.createElement(SalesAnalyticsPage))));
        </script></body></html>` }));
        await page.route("**/api/v1/analytics/sales/**", route => {
          const endpoint = new URL(route.request().url()).pathname.split("/").pop();
          const data = endpoint === "client-reports" ? { status: mode === "imported" ? "available" : "unavailable", report: mode === "imported" ? report : null }
            : endpoint === "summary" ? { industry: "fashion", as_of: "2026-10-28T08:00:00Z", currency: "INR", currencies: ["INR"], today: bucket, week: bucket, month: bucket, year: bucket }
            : endpoint === "branches" ? { period_start: "2026-08-01", as_of: "2026-10-28", unassigned_records: 3, branches: report.sales.stores.map(row => ({ name: row.name, gross_revenue: row.net_amount, units_sold: row.net_units, currency: "INR", revenue_by_currency: { INR: row.net_amount } })) }
            : endpoint === "top-products" ? { products: [{ sku_id: "synthetic", product_name: "Cotton kurta", sku_code: "COTTON-KURTA-M", units_sold: 500, gross_revenue: 250000, currency: "INR", returns: 2 }] }
            : { currency: "INR", currencies: ["INR"], current_bucket: "2026-10-01", series: [
              { bucket: "2026-08-01", units_sold: 2000, gross_revenue: 800000, revenue_by_currency: { INR: 800000 } },
              { bucket: "2026-09-01", units_sold: 2400, gross_revenue: 1000000, revenue_by_currency: { INR: 1000000 } },
              { bucket: "2026-10-01", units_sold: 2840, gross_revenue: 1248000, revenue_by_currency: { INR: 1248000 } },
            ] };
          return route.fulfill({ json: data });
        });
        await page.goto("/__sales-design-review");
        await expect(page.getByRole("heading", { name: "Your sales, at a glance" })).toBeVisible();
        await expect(page.getByRole("region", { name: "Sales by branch" })).toBeVisible();
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        const hero = page.locator("main .rounded-\\[20px\\]").first();
        const colors = await hero.evaluate(element => ({ bg: getComputedStyle(element).backgroundColor, fg: getComputedStyle(element).color }));
        expect(colors.bg).not.toBe(colors.fg);
        await page.screenshot({ path: path.join(evidence, `${mode}-${size}-${dark ? "dark" : "light"}.png`), fullPage: true });
        if (mode === "transactions") {
          await expect(page.getByText(/Sales rose 25.0% in Sep 2026/)).toBeVisible();
          await page.getByText("See exact sales history").click();
          await expect(page.getByRole("table", { name: "Sales history, before returns" })).toBeVisible();
          await page.getByRole("button", { name: "Daily", exact: true }).click();
          await expect(page.getByRole("button", { name: "Daily", exact: true })).toHaveAttribute("aria-pressed", "true");
        }
        expect(errors).toEqual([]);
      });
    }
  }
}
