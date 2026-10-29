// src/components/charts/kit/ChartTooltip.tsx
export type TooltipSeries = { key: string; label: string; kind: "actual" | "expected" | "range-low" | "range-high" | "other"; format?: (v: number) => string };

const ORDER: Record<TooltipSeries["kind"], number> = { actual: 0, expected: 1, "range-low": 2, "range-high": 3, other: 4 };

interface Props {
  active?: boolean;
  label?: string | number;
  payload?: { dataKey?: string | number; value?: number | null }[];
  series: TooltipSeries[];
  labelFormatter?: (label: string) => string;
  unit?: string;
}

export const ChartTooltip = ({ active, label, payload, series, labelFormatter, unit }: Props) => {
  if (!active || !payload) return null;
  const values = new Map(payload.map((p) => [String(p.dataKey), p.value]));
  const rows = [...series].sort((a, b) => ORDER[a.kind] - ORDER[b.kind]);
  return (
    <div className="min-w-44 rounded-xl border border-line bg-surface px-3 py-2.5 text-xs shadow-md">
      {label !== undefined && <p className="mb-1.5 font-medium text-content">{labelFormatter ? labelFormatter(String(label)) : label}</p>}
      <ul className="space-y-1">
        {rows.map((s) => {
          const v = values.get(s.key);
          const shown = v === null || v === undefined ? "—" : `${s.format ? s.format(v) : v.toLocaleString("en-IN")}${unit ? ` ${unit}` : ""}`;
          return <li key={s.key} className="flex justify-between gap-4"><span className="text-content-muted">{s.label}</span><span className="tabular-nums font-medium text-content">{shown}</span></li>;
        })}
      </ul>
    </div>
  );
};
