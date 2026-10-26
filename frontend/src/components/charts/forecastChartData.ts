import { format, parseISO } from "date-fns";
import type { ForecastRow } from "@/types/api";
import { fmtNumber } from "@/utils/format";

/** One history bucket. `actual: null` means no records, not zero sales. */
export interface HistoryPoint {
  date: string;
  actual: number | null;
}

/**
 * History as the chart plots it.
 *
 * Observed zero-sales weeks are kept — dropping them made intermittent demand
 * look continuous. A null bucket (before the first recorded sale) stays a gap.
 * Negative values would be returns netted against sales; units are gross, so a
 * negative bucket is not demand and is excluded.
 */
export function prepareHistory(history: HistoryPoint[] | undefined): HistoryPoint[] {
  return (history ?? []).filter(
    (point) => point.actual === null || (Number.isFinite(point.actual) && point.actual >= 0),
  );
}

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? "" : "s"}`;

/** Screen-reader summary: the real extremes, not the first and last points. */
export function chartSummary(rows: ForecastRow[], history: HistoryPoint[]): string {
  if (!rows.length) return "No forecast data available.";
  const values = rows.map((row) => row.p50);
  const first = rows[0];
  const last = rows[rows.length - 1];
  const parts = [
    `Expected demand from ${format(parseISO(first.forecast_date), "MMM d")} to ` +
      `${format(parseISO(last.forecast_date), "MMM d, yyyy")}: lowest ${fmtNumber(Math.min(...values))}, ` +
      `highest ${fmtNumber(Math.max(...values))} units.`,
  ];
  const zero = history.filter((point) => point.actual === 0).length;
  const missing = history.filter((point) => point.actual === null).length;
  if (zero) parts.push(`History includes ${plural(zero, "week")} with zero sales.`);
  if (missing) parts.push(`${plural(missing, "week")} with no records ${missing === 1 ? "is" : "are"} shown as a gap.`);
  return parts.join(" ");
}
