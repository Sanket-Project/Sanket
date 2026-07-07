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

export const CategoryBar = ({ data, accent = "#7C3AED", height = 240 }: Props) => {
  if (!data.length) {
    return (
      <div className="text-center text-slate-500 py-8 text-sm">
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
          stroke="#64748b"
          tick={{ fontSize: 12, fill: "#64748b" }}
          tickLine={false}
          axisLine={false}
        />
        <Tooltip
          cursor={{ fill: "rgba(148,163,184,0.08)" }}
          contentStyle={{
            background: "#ffffff",
            border: "1px solid #e2e8f0",
            borderRadius: 8,
            fontSize: 12,
            color: "#0f172a",
          }}
        />
        <Bar
          dataKey="count"
          fill={accent}
          radius={[4, 4, 4, 4]}
          isAnimationActive={true}
          animationDuration={800}
          animationEasing="ease-out"
        />
      </BarChart>
    </ResponsiveContainer>
  );
};
