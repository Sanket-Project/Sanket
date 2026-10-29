import {
  Bar,
  BarChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

interface Props {
  data: { category: string; count: number }[];
  accent?: string;
  height?: number;
}

export const CategoryBar = ({ data, accent = "var(--chart-actual)", height = 240 }: Props) => {
  if (!data.length) {
    return (
      <div className="text-center text-content-muted py-8 text-sm">
        No categories with data yet.
      </div>
    );
  }
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart
        data={data}
        margin={{ top: 6, right: 8, left: 0, bottom: 0 }}
        layout="vertical"
      >
        <XAxis type="number" hide />
        <YAxis
          dataKey="category"
          type="category"
          width={140}
          stroke="var(--text-muted)"
          tick={{ fontSize: 12, fill: "var(--text-muted)" }}
          tickLine={false}
          axisLine={false}
        />
        <Tooltip
          cursor={{ fill: "rgba(148,163,184,0.08)" }}
          contentStyle={{
            background: "var(--surface)",
            border: "1px solid var(--border)",
            borderRadius: 8,
            fontSize: 12,
            color: "var(--text)",
          }}
        />
        <Bar
          dataKey="count"
          fill={accent}
          radius={[4, 4, 4, 4]}
          isAnimationActive={false}
          animationDuration={800}
          animationEasing="ease-out"
        />
      </BarChart>
    </ResponsiveContainer>
  );
};
