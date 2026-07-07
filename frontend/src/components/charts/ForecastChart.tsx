import {
  Area,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  CartesianGrid,
} from "recharts";
import { memo, useMemo } from "react";
import { format, parseISO } from "date-fns";
import type { ForecastRow } from "@/types/api";
import { fmtNumber } from "@/utils/format";

interface Props {
  rows: ForecastRow[];
  history?: { date: string; actual: number }[];
  accent?: string;
  height?: number;
}

export const ForecastChart = memo(function ForecastChart({
  rows,
  history,
  accent = "#7C3AED",
  height = 320,
}: Props) {
  const data = useMemo(() => {
    const fcMap = new Map<string, ForecastRow>();
    rows.forEach((r) => fcMap.set(r.forecast_date, r));
    const allDates = new Set<string>([
      ...rows.map((r) => r.forecast_date),
      ...(history?.map((h) => h.date) ?? []),
    ]);
    return Array.from(allDates)
      .sort()
      .map((d) => {
        const f = fcMap.get(d);
        const h = history?.find((x) => x.date === d);
        return {
          date: d,
          actual: h?.actual ?? null,
          p10: f?.p10 ?? null,
          p50: f?.p50 ?? null,
          p90: f?.p90 ?? null,
          band: f ? [f.p10, f.p90] : null,
        };
      });
  }, [rows, history]);

  // Build a short text summary for screen readers
  const summary = useMemo(() => {
    if (rows.length === 0) return "No forecast data available.";
    const first = rows[0];
    const last = rows[rows.length - 1];
    return `Demand forecast from ${format(parseISO(first.forecast_date), "MMM d")} to ${format(
      parseISO(last.forecast_date),
      "MMM d, yyyy",
    )}. Median (P50) ranges from ${fmtNumber(first.p50)} to ${fmtNumber(last.p50)} units.`;
  }, [rows]);

  return (
    <figure aria-label="Demand forecast chart" className="m-0">
      {/* Visually hidden summary for screen readers */}
      <figcaption className="sr-only">{summary}</figcaption>
      <div aria-hidden="true">
        <ResponsiveContainer width="100%" height={height}>
          <ComposedChart data={data} margin={{ top: 10, right: 12, left: 0, bottom: 0 }}>
            <defs>
              <linearGradient id="band" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={accent} stopOpacity={0.4} />
                <stop offset="100%" stopColor={accent} stopOpacity={0.05} />
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 6" stroke="rgba(148,163,184,0.22)" vertical={false} />
            <XAxis
              dataKey="date"
              tickFormatter={(d) => format(parseISO(d), "MMM d")}
              stroke="rgba(148,163,184,0.4)"
              tick={{ fontSize: 11, fill: "#94a3b8" }}
              tickLine={false}
            />
            <YAxis
              stroke="rgba(148,163,184,0.4)"
              tick={{ fontSize: 11, fill: "#94a3b8" }}
              tickLine={false}
              axisLine={false}
              width={44}
            />
            <Tooltip
              contentStyle={{
                background: "var(--surface)",
                border: "1px solid var(--border-strong)",
                borderRadius: 12,
                fontSize: 12,
                color: "var(--text)",
                boxShadow: "var(--shadow-md)",
              }}
              labelStyle={{ color: "var(--text)", fontWeight: 600 }}
              labelFormatter={(d) => format(parseISO(d as string), "MMM d, yyyy")}
            />
            <Area
              type="monotone"
              dataKey="band"
              stroke="none"
              fill="url(#band)"
              isAnimationActive={true}
              animationDuration={1000}
              animationEasing="ease-out"
            />
            <Line
              type="monotone"
              dataKey="actual"
              stroke="#94a3b8"
              strokeWidth={2}
              dot={false}
              isAnimationActive={true}
              animationDuration={1200}
              animationEasing="ease-out"
              name="Actual"
            />
            <Line
              type="monotone"
              dataKey="p50"
              stroke={accent}
              strokeWidth={2.5}
              strokeDasharray="5 4"
              dot={false}
              isAnimationActive={true}
              animationDuration={1500}
              animationEasing="ease-out"
              name="Forecast (P50)"
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
});
