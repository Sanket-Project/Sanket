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
  accent = "#147D73",
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
        <CartesianGrid vertical={false} strokeDasharray="2 6" stroke="var(--line)" />
        <XAxis
          dataKey="date"
          tickFormatter={(d) => format(parseISO(d), "MMM d")}
          stroke="var(--text-subtle)"
          tick={{ fontSize: 11, fill: "var(--text-subtle)" }}
          tickLine={false}
        />
        <YAxis
          stroke="var(--text-subtle)"
          tick={{ fontSize: 11, fill: "var(--text-subtle)" }}
          tickLine={false}
          axisLine={false}
        />
        <Tooltip
          contentStyle={{
            background: "var(--surface)",
            color: "var(--text)",
            border: "1px solid var(--line)",
            borderRadius: 8,
            fontSize: 12,
          }}
          labelStyle={{ color: "var(--text)" }}
          labelFormatter={(d) => format(parseISO(d as string), "MMM d, yyyy")}
        />
        <Area
          type="monotone"
          dataKey="band"
          stroke="none"
          fill={accent}
          fillOpacity={0.1}
          isAnimationActive={false}
          name="Expected range"
        />
        {showBaseline && (
          <Line
            type="monotone"
            dataKey="baseline"
            stroke="var(--text-subtle)"
            strokeWidth={1.5}
            strokeDasharray="2 3"
            dot={false}
            isAnimationActive={false}
            name="Baseline"
          />
        )}
        <Line
          type="monotone"
          dataKey="p50"
          stroke={accent}
          strokeWidth={2.5}
          dot={false}
          isAnimationActive={false}
          name="Scenario demand"
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
};
