import type { HistoryPoint } from "@/components/charts/forecastChartData";

/**
 * Weekly actuals on the forecast's calendar (Monday 00:00 UTC buckets).
 *
 * The forecast is weekly, so plotting daily actuals beside it compared a day
 * of sales with a week of demand. The bucket containing "now" is still filling
 * up and would read as a sudden drop, so only complete weeks are returned.
 * `null` (no records yet) is kept distinct from an observed zero week.
 */
export function weeklyHistory(response: {
  current_bucket?: string | null;
  series: Array<{ bucket: string; units_sold: number | null }>;
}): HistoryPoint[] {
  return response.series
    .filter((point) => point.bucket !== response.current_bucket)
    .map((point) => ({ date: point.bucket, actual: point.units_sold }));
}
