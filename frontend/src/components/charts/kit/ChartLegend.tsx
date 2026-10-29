// src/components/charts/kit/ChartLegend.tsx
export const ChartLegend = ({ items }: { items: { label: string; color: string; style: "solid" | "dashed" | "band" }[] }) => (
  <ul aria-label="Legend" className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-content-muted">
    {items.map((i) => (
      <li key={i.label} className="inline-flex items-center gap-1.5">
        {i.style === "band"
          ? <span aria-hidden="true" className="h-2.5 w-4 rounded-sm opacity-30" style={{ background: i.color }} />
          : <span aria-hidden="true" className="w-4 border-t-2" style={{ borderColor: i.color, borderStyle: i.style === "dashed" ? "dashed" : "solid" }} />}
        {i.label}
      </li>
    ))}
  </ul>
);
