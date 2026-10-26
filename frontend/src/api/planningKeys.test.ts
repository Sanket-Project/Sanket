import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";
import { INTEGRATION_CATALOG_KEY, PLANNING_KEYS, invalidatePlanningData } from "@/api/planningKeys";

// Deep audit F9: refresh and import refetched one or two queries and left
// coverage, decisions and readiness built from the old stock.

describe("invalidatePlanningData", () => {
  it("marks every planning query stale, whatever its key suffix", async () => {
    const qc = new QueryClient();
    const seeded = PLANNING_KEYS.map((root) => [...root, "fashion", "detail"]);
    seeded.forEach((key) => qc.setQueryData(key, { cached: true }));
    qc.setQueryData(["billing", "status"], { cached: true });

    await invalidatePlanningData(qc);

    seeded.forEach((key) => expect(qc.getQueryState(key)?.isInvalidated, key.join("/")).toBe(true));
    expect(qc.getQueryState(["billing", "status"])?.isInvalidated).toBe(false);
  });

  it("covers stock, coverage, decisions, forecasts, readiness and the integration catalog", () => {
    const roots = PLANNING_KEYS.map((key) => key[0]);
    for (const root of [
      "inventory-levels", "inventory-coverage", "decisions",
      "dashboard-history", "forecast-confidence", "data-quality", "roi-summary",
    ]) {
      expect(roots).toContain(root);
    }
    expect(PLANNING_KEYS).toContainEqual(INTEGRATION_CATALOG_KEY);
  });

  it("never re-runs forecast generation as a side effect of invalidation", () => {
    // ["dashboard-forecast"] is POST /forecasts/generate — an ML inference run.
    expect(PLANNING_KEYS.map((key) => key[0])).not.toContain("dashboard-forecast");
  });
});
