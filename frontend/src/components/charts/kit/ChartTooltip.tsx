// src/components/charts/kit/ChartTooltip.tsx
/** `range` is a single series holding a `[low, high]` tuple, e.g. a P10–P90 band drawn as one Area. */
export type TooltipSeries = { key: string; label: string; kind: "actual" | "expected" | "range" | "range-low" | "range-high" | "other"; format?: (v: number) => string };

const ORDER: Record<TooltipSeries["kind"], number> = { actual: 0, expected: 1, range: 2, "range-low": 3, "range-high": 4, other: 5 };

interface Props {
  active?: boolean;
  label?: string | number;
  payload?: { dataKey?: string | number; value?: unknown }[];
  series: TooltipSeries[];
  labelFormatter?: (label: string) => string;
  unit?: string;
}

const isNum = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);

/** Formats one tooltip value; anything that is not a finite number (or, for a range, a pair of them) is "—". */
function formatValue(v: unknown, s: TooltipSeries, unit?: string): string {
  const fmt = (n: number) => (s.format ? s.format(n) : n.toLocaleString("en-IN"));
  const suffix = unit ? ` ${unit}` : "";
  if (s.kind === "range") {
    if (!Array.isArray(v) || v.length !== 2 || !isNum(v[0]) || !isNum(v[1])) return "—";
    return `${fmt(v[0])}–${fmt(v[1])}${suffix}`;
  }
  return isNum(v) ? `${fmt(v)}${suffix}` : "—";
}

export const ChartTooltip = ({ active, label, payload, series, labelFormatter, unit }: Props) => {
  if (!active || !payload) return null;
  const values = new Map(payload.map((p) => [String(p.dataKey), p.value]));
  const rows = [...series].sort((a, b) => ORDER[a.kind] - ORDER[b.kind]);
  return (
    <div className="min-w-44 rounded-xl border border-line bg-surface px-3 py-2.5 text-xs shadow-md">
      {label !== undefined && <p className="mb-1.5 font-medium text-content">{labelFormatter ? labelFormatter(String(label)) : label}</p>}
      <ul className="space-y-1">
        {rows.map((s) => (
          <li key={s.key} className="flex justify-between gap-4"><span className="text-content-muted">{s.label}</span><span className="tabular-nums font-medium text-content">{formatValue(values.get(s.key), s, unit)}</span></li>
        ))}
      </ul>
    </div>
  );
};
