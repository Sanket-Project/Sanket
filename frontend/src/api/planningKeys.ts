import type { QueryClient, QueryKey } from "@tanstack/react-query";

/** The one key every integration-catalog query uses. */
export const INTEGRATION_CATALOG_KEY = ["integration", "catalog"] as const;

/**
 * Query roots derived from stock, sales, SKU master data or the forecast run.
 *
 * Changing any input (a refresh, an import, an accepted recommendation) can
 * change every one of these, so they are invalidated together: refetching only
 * the screen the user clicked left coverage and decisions describing old stock.
 *
 * Deliberately excludes ["dashboard-forecast"]: its query runs
 * POST /forecasts/generate (an ML inference), which should happen only when a
 * user asks for it, not as a side effect of accepting a recommendation.
 */
export const PLANNING_KEYS: readonly QueryKey[] = [
  ["inventory-levels"],
  ["inventory-coverage"],
  ["cost-analysis"],
  ["decisions"],
  ["roi-summary"],
  ["dashboard-history"],
  ["forecasts"],
  ["forecast-confidence"],
  ["data-quality"],
  ["onboarding-readiness"],
  ["alerts"],
  ["financial-impact"],
  ["sales-summary"],
  ["sales-timeseries"],
  ["sales-top-products"],
  ["skus"],
  ["skus-list"],
  INTEGRATION_CATALOG_KEY,
];

export function invalidatePlanningData(qc: QueryClient): Promise<void> {
  return Promise.all(PLANNING_KEYS.map((queryKey) => qc.invalidateQueries({ queryKey }))).then(
    () => undefined,
  );
}
