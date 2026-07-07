import {
  Area,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  CartesianGrid,
  Legend,
} from "recharts";
import { useMemo } from "react";
import { format, parseISO } from "date-fns";
import type { HybridForecastSeries } from "@/types/api";

interface Props {
  series: HybridForecastSeries;
  accent?: string;
  height?: number;
  showBaseline?: boolean;
}

export const ScenarioBands = ({
  series,
  accent = "#7C3AED",
  height = 340,
  showBaseline = true,
}: Props) => {
  const data = useMemo(() => {
    return series.ds.map((d, i) => ({
      date: d,
      p10: series.p10[i],
      p50: series.p50[i],
      p90: series.p90[i],
      baseline: series.baseline_p50[i] ?? null,
      band: [series.p10[i], series.p90[i]],
    }));
  }, [series]);

  return (
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart
        data={data}
        margin={{ top: 10, right: 12, left: 0, bottom: 0 }}
      >
        <defs>
          <linearGradient id={`band-${series.sku_id}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={accent} stopOpacity={0.45} />
            <stop offset="100%" stopColor={accent} stopOpacity={0.05} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 6" stroke="rgba(255,255,255,0.05)" />
        <XAxis
          dataKey="date"
          tickFormatter={(d) => format(parseISO(d), "MMM d")}
          stroke="rgba(255,255,255,0.4)"
          tick={{ fontSize: 11 }}
          tickLine={false}
        />
        <YAxis
          stroke="rgba(255,255,255,0.4)"
          tick={{ fontSize: 11 }}
          tickLine={false}
          axisLine={false}
        />
        <Tooltip
          contentStyle={{
            background: "#11141C",
            border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: 8,
            fontSize: 12,
          }}
          labelStyle={{ color: "#fff" }}
          labelFormatter={(d) => format(parseISO(d as string), "MMM d, yyyy")}
        />
        <Legend
          wrapperStyle={{ fontSize: 11, paddingTop: 8 }}
          iconType="line"
        />
        <Area
          type="monotone"
          dataKey="band"
          stroke="none"
          fill={`url(#band-${series.sku_id})`}
          isAnimationActive={false}
          name="P10–P90 band"
        />
        {showBaseline && (
          <Line
            type="monotone"
            dataKey="baseline"
            stroke="rgba(255,255,255,0.4)"
            strokeWidth={1.5}
            strokeDasharray="2 3"
            dot={false}
            isAnimationActive={false}
            name="Historical P50 (no trend)"
          />
        )}
        <Line
          type="monotone"
          dataKey="p50"
          stroke={accent}
          strokeWidth={2.5}
          dot={false}
          isAnimationActive={false}
          name="Hybrid P50 (trend-fused)"
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
};
