const DAY = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
const MONTH = new Intl.DateTimeFormat("en-GB", { month: "short", year: "numeric", timeZone: "UTC" });

export function formatDateTick(iso: string, granularity: "day" | "week" | "month"): string {
  const d = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return iso;
  return (granularity === "month" ? MONTH : DAY).format(d);
}

export function formatCompact(n: number): string {
  const abs = Math.abs(n);
  const trim = (v: number) => String(Number(v.toFixed(1)));
  if (abs >= 1_000_000) return `${trim(n / 1_000_000)}M`;
  if (abs >= 1_000) return `${trim(n / 1_000)}k`;
  return String(n);
}

export const GRID_PROPS = { vertical: false, stroke: "var(--border)", strokeDasharray: "0" } as const;
export const AXIS_PROPS = { tick: { fontSize: 12, fill: "var(--text-subtle)" }, tickLine: false, axisLine: false } as const;
