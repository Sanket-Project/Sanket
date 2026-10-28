import { describe, expect, it } from "vitest";

import type { Decision } from "@/api/decisions";
import { buildIndicativePlan, describeSource, omissionReason } from "@/utils/forecastPresentation";

describe("describeSource", () => {
  it("names the model the service actually used", () => {
    expect(describeSource("chronos_zero_shot").short).toBe("Chronos zero-shot");
    expect(describeSource("chronos_zero_shot").detail).toMatch(/not trained on your data/i);
    expect(describeSource("trained").short).toBe("Model trained on your sales");
  });

  it("never presents an indicative plan as a model", () => {
    const d = describeSource("indicative");
    expect(d.isModel).toBe(false);
    expect(d.detail).toMatch(/not a model forecast/i);
  });

  it("does not invent a model for an unknown source", () => {
    expect(describeSource(undefined).short).toBe("Unknown source");
  });

  it("identifies persisted hybrid and ensemble runs without calling them zero-shot", () => {
    expect(describeSource("hybrid-trend-fused").short).toBe("Hybrid forecast");
    expect(describeSource("ensemble").short).toBe("Model ensemble");
  });
});

describe("omissionReason", () => {
  it("explains why an SKU got no forecast", () => {
    expect(omissionReason({ reason: "no_sales_history", observations: 0 })).toMatch(/never sold/i);
    expect(omissionReason({ reason: "insufficient_history", observations: 3 })).toBe(
      "Only 3 weeks of sales — needs at least 8",
    );
    expect(omissionReason({ reason: "series_cap", observations: 40 })).toMatch(/limit/i);
  });
});

describe("buildIndicativePlan", () => {
  const decision = (sku: string, p50Window: number, days: number) =>
    ({ sku_id: sku, inputs: { demand_p50_over_window: p50Window, protection_days: days } }) as unknown as Decision;

  it("is a flat weekly average — no invented trend or seasonality", () => {
    const plan = buildIndicativePlan([decision("A", 70, 49)], 4, new Date("2026-10-26T00:00:00Z"));
    const p50s = plan!.rows.map((r) => r.p50);
    expect(new Set(p50s)).toEqual(new Set([10]));
    expect(plan!.source).toBe("indicative");
  });

  it("covers every SKU with a demand input, not only four", () => {
    const decisions = ["A", "B", "C", "D", "E", "F"].map((s) => decision(s, 70, 49));
    const plan = buildIndicativePlan(decisions, 2, new Date("2026-10-26T00:00:00Z"));
    expect(new Set(plan!.rows.map((r) => r.sku_id)).size).toBe(6);
  });

  it("returns nothing when no decision carries demand", () => {
    expect(buildIndicativePlan([decision("A", 0, 49)], 4)).toBeNull();
  });
});
