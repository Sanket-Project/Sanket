import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ForecastChart } from "@/components/charts/ForecastChart";
import { chartSummary, prepareHistory } from "@/components/charts/forecastChartData";
import type { ForecastRow } from "@/types/api";

// jsdom has no ResizeObserver; recharts' ResponsiveContainer needs one to mount.
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver;

const row = (date: string, p50: number): ForecastRow => ({
  sku_id: "portfolio", forecast_date: date, p10: p50 * 0.8, p50, p90: p50 * 1.2,
});

describe("prepareHistory (deep audit F5)", () => {
  it("keeps an observed zero-sales week instead of dropping it", () => {
    const points = prepareHistory([
      { date: "2026-09-28", actual: 3 },
      { date: "2026-10-05", actual: 0 },
      { date: "2026-10-12", actual: 4 },
    ]);
    expect(points.map((p) => p.actual)).toEqual([3, 0, 4]);
  });

  it("keeps a no-records week as a gap, distinct from zero", () => {
    const points = prepareHistory([
      { date: "2026-09-28", actual: null },
      { date: "2026-10-05", actual: 0 },
    ]);
    expect(points[0].actual).toBeNull();
    expect(points[1].actual).toBe(0);
  });

  it("excludes negative (net-of-returns) values rather than plotting them as demand", () => {
    expect(prepareHistory([{ date: "2026-10-05", actual: -2 }])).toEqual([]);
  });
});

describe("chartSummary (deep audit F16)", () => {
  it("reports the true lowest and highest expected values, not the endpoints", () => {
    const summary = chartSummary(
      [row("2026-10-26", 5), row("2026-11-02", 40), row("2026-11-09", 2)],
      [],
    );
    expect(summary).toMatch(/lowest 2/);
    expect(summary).toMatch(/highest 40/);
    expect(summary).not.toMatch(/ranging from 5 to 2/);
  });

  it("states how many history weeks were zero and how many have no records", () => {
    const summary = chartSummary([row("2026-10-26", 5)], [
      { date: "2026-10-05", actual: 0 },
      { date: "2026-10-12", actual: null },
      { date: "2026-10-19", actual: 6 },
    ]);
    expect(summary).toMatch(/1 week with zero sales/);
    expect(summary).toMatch(/1 week with no records/);
  });
});

describe("ForecastChart", () => {
  it("names the unit of measure when one is given", () => {
    render(<ForecastChart rows={[row("2026-10-26", 5)]} unitLabel="units / week" />);
    expect(screen.getByText("units / week")).toBeInTheDocument();
  });
});
