import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { memo, useMemo } from "react";
import { format, parseISO } from "date-fns";
import type { ForecastRow } from "@/types/api";
import { fmtNumber } from "@/utils/format";
import { chartSummary, prepareHistory, type HistoryPoint } from "@/components/charts/forecastChartData";

interface Props {
  rows: ForecastRow[];
  /** Must use the same buckets as `rows` (weekly forecasts ⇒ weekly actuals). */
  history?: HistoryPoint[];
  accent?: string;
  height?: number;
  compact?: boolean;
  /** Unit of every plotted value, e.g. "units / week". */
  unitLabel?: string;
}

type ChartPoint = {
  date: string;
  actual: number | null;
  p50: number | null;
  band: [number, number] | null;
};

function ForecastTooltip({ active, payload, label }: {
  active?: boolean;
  payload?: Array<{ payload?: ChartPoint }>;
  label?: string;
}) {
  if (!active || !payload?.length || !label) return null;
  const point = payload[0]?.payload;
  if (!point) return null;
  return (
    <div className="min-w-44 rounded-xl border border-line-strong bg-surface p-3 text-xs shadow-md">
      <p className="font-semibold text-content">{format(parseISO(label), "MMM d, yyyy")}</p>
      <dl className="mt-2 space-y-1.5">
        {point.actual != null && (
          <div className="flex justify-between gap-6"><dt className="text-content-subtle">Actual</dt><dd className="font-mono font-semibold text-content">{fmtNumber(point.actual)}</dd></div>
        )}
        {point.p50 != null && (
          <div className="flex justify-between gap-6"><dt className="text-content-subtle">Expected</dt><dd className="font-mono font-semibold text-content">{fmtNumber(point.p50)}</dd></div>
        )}
        {point.band && (
          <div className="flex justify-between gap-6"><dt className="text-content-subtle">Expected range</dt><dd className="font-mono font-semibold text-content">{fmtNumber(point.band[0])}–{fmtNumber(point.band[1])}</dd></div>
        )}
      </dl>
    </div>
  );
}

export const ForecastChart = memo(function ForecastChart({
  rows,
  history,
  accent = "var(--chart-forecast)",
  height = 260,
  compact = false,
  unitLabel,
}: Props) {
  const validHistory = useMemo(() => prepareHistory(history), [history]);
  const data = useMemo<ChartPoint[]>(() => {
    const fcMap = new Map(rows.map((row) => [row.forecast_date, row]));
    const historyMap = new Map(validHistory.map((point) => [point.date.slice(0, 10), point.actual]));
    const dates = new Set([...fcMap.keys(), ...historyMap.keys()]);
    return Array.from(dates).sort().map((date) => {
      const forecast = fcMap.get(date);
      return {
        date,
        actual: historyMap.get(date) ?? null,
        p50: forecast?.p50 ?? null,
        band: forecast ? [forecast.p10, forecast.p90] : null,
      };
    });
  }, [rows, validHistory]);

  const forecastStart = rows[0]?.forecast_date;
  const hasActuals = validHistory.some((point) => point.actual !== null);
  const summary = useMemo(() => chartSummary(rows, validHistory), [rows, validHistory]);

  if (!data.length) {
    return <div className="grid h-56 place-items-center text-sm text-content-subtle">No forecast data yet.</div>;
  }

  return (
    <figure aria-label="Actual and expected demand chart" className="m-0">
      <figcaption className="sr-only">{summary}</figcaption>
      {!compact && (
        <div className="mb-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-content-muted" aria-hidden="true">
          {unitLabel && <span className="font-medium text-content-subtle">{unitLabel}</span>}
          {hasActuals && <span className="inline-flex items-center gap-2"><span className="h-0.5 w-7 rounded bg-[var(--chart-actual)]" />Actual</span>}
          {rows.length > 0 && <span className="inline-flex items-center gap-2"><span className="w-7 border-t-2 border-dashed" style={{ borderColor: accent }} />Expected</span>}
          {rows.length > 0 && <span className="inline-flex items-center gap-2"><span className="h-3 w-7 rounded-sm" style={{ background: accent, opacity: 0.12 }} />80% model interval</span>}
        </div>
      )}
      {rows.length > 0 && <details className={compact ? "sr-only" : "mb-2 text-xs text-content-subtle"}><summary className="cursor-pointer">About the model interval</summary><p className="mt-2">The P10–P90 band is nominally 80%; its coverage has not been validated for this forecast.</p></details>}
      <div aria-hidden="true">
        <ResponsiveContainer width="100%" height={height}>
          <ComposedChart data={data} margin={{ top: 8, right: 12, left: compact ? -18 : -4, bottom: 0 }}>
            <CartesianGrid stroke="var(--border)" vertical={false} />
            <XAxis
              dataKey="date"
              tickFormatter={(date) => format(parseISO(date), "MMM d")}
              tick={{ fontSize: 11, fill: "var(--text-subtle)" }}
              tickLine={false}
              axisLine={{ stroke: "var(--border-strong)" }}
              minTickGap={28}
            />
            <YAxis
              tick={{ fontSize: 11, fill: "var(--text-subtle)" }}
              tickLine={false}
              axisLine={false}
              width={44}
              tickFormatter={(value) => fmtNumber(value)}
              domain={[
                (dataMin: number) => Math.max(0, Math.floor(dataMin * 0.9)),
                (dataMax: number) => Math.ceil(dataMax * 1.1),
              ]}
            />
            <Tooltip content={<ForecastTooltip />} cursor={{ stroke: "var(--border-strong)", strokeWidth: 1 }} />
            <Area
              type="linear"
              dataKey="band"
              stroke="none"
              fill={accent}
              fillOpacity={0.12}
              isAnimationActive={false}
              tooltipType="none"
              connectNulls
            />
            <Line
              type="linear"
              dataKey="actual"
              stroke="var(--chart-actual)"
              strokeWidth={2}
              dot={false}
              // A null bucket has no records: leave a gap rather than imply a value.
              connectNulls={false}
              isAnimationActive={false}
              name="Actual"
            />
            <Line
              type="linear"
              dataKey="p50"
              stroke={accent}
              strokeWidth={2}
              strokeDasharray="6 5"
              strokeLinecap="round"
              dot={false}
              connectNulls
              isAnimationActive={false}
              name="Expected"
            />
            {hasActuals && forecastStart ? (
              <ReferenceLine
                x={forecastStart}
                stroke="var(--border-strong)"
                strokeDasharray="3 4"
              />
            ) : null}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
});
