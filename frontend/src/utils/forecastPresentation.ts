import type { Decision } from "@/api/decisions";
import type { ForecastOmission, ForecastResponse } from "@/types/api";

/** Charts per page on the Forecasts screen; every SKU stays reachable. */
export const SKUS_PER_PAGE = 6;

const SOURCES: Record<string, { short: string; detail: string; isModel: boolean }> = {
  chronos_zero_shot: {
    short: "Chronos zero-shot",
    detail:
      "Amazon Chronos, a pretrained forecasting model, applied to your sales history. It is not trained on your data, and needs at least 8 weeks of history per SKU.",
    isModel: true,
  },
  timesfm_zero_shot: {
    short: "TimesFM zero-shot",
    detail: "Google TimesFM, a pretrained forecasting model, applied to your sales history. It is not trained on your data.",
    isModel: true,
  },
  trained: {
    short: "Model trained on your sales",
    detail: "A model trained on this workspace's own sales history.",
    isModel: true,
  },
  indicative: {
    short: "Indicative plan",
    detail:
      "Flat weekly average taken from open purchase recommendations while the forecast service is unavailable — not a model forecast.",
    isModel: false,
  },
};

/** What produced a forecast, in words — taken from the response, never assumed. */
export function describeSource(source?: string) {
  const known = source ? SOURCES[source] : undefined;
  return (
    known ?? {
      short: "Unknown source",
      detail: "The forecast service did not say which model produced this result.",
      isModel: false,
    }
  );
}

/** Why an active SKU has no forecast. */
export function omissionReason(o: Pick<ForecastOmission, "reason" | "observations">): string {
  switch (o.reason) {
    case "no_sales_history":
      return "Never sold — a forecast needs sales history; none is invented for new products";
    case "insufficient_history":
      return `Only ${o.observations} week${o.observations === 1 ? "" : "s"} of sales — needs at least 8`;
    case "series_cap":
      return "Over the per-run SKU limit — narrow the scope or raise the limit";
    case "not_in_model":
      return "Not part of the trained model";
    default:
      return o.reason;
  }
}

/**
 * When the forecast service is down, show each open recommendation's own
 * weekly demand figure as a flat line — exactly what the decision engine used,
 * with no trend, seasonality or shape added. Labelled as not a forecast.
 */
export function buildIndicativePlan(
  decisions: Decision[],
  horizon: number,
  start: Date = new Date(),
): ForecastResponse | null {
  const eligible = decisions.filter((d) => typeof d.inputs.demand_p50_over_window === "number" &&
    d.inputs.demand_p50_over_window > 0 && typeof d.inputs.protection_days === "number");
  if (!eligible.length) return null;

  const rows = eligible.flatMap((d) => {
    const weeks = Math.max(1, d.inputs.protection_days! / 7);
    const weekly = Math.round(d.inputs.demand_p50_over_window! / weeks);
    return Array.from({ length: horizon }, (_, i) => {
      const date = new Date(start);
      date.setUTCDate(start.getUTCDate() + (i + 1) * 7);
      return {
        sku_id: d.sku_id,
        forecast_date: date.toISOString().slice(0, 10),
        p10: weekly,
        p50: weekly,
        p90: weekly,
      };
    });
  });

  return {
    run_id: "indicative-decision-plan",
    n_predictions: rows.length,
    rows,
    source: "indicative",
    context_source: "open decision inputs",
  };
}
