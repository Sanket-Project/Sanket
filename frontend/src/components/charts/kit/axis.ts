import { fmtCompact } from "@/utils/format";

const DAY = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: "UTC" });
const MONTH = new Intl.DateTimeFormat("en-GB", { month: "short", year: "numeric", timeZone: "UTC" });

export function formatDateTick(iso: string, granularity: "day" | "week" | "month"): string {
  const d = new Date(`${iso.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(d.getTime())) return iso;
  return (granularity === "month" ? MONTH : DAY).format(d);
}

export const formatCompact = (n: number): string => fmtCompact(n);

export function formatCurrencyTick(n: number, currency: string): string {
  return new Intl.NumberFormat("en-US", { style: "currency", currency, notation: "compact", maximumFractionDigits: 1 }).format(n);
}

export const GRID_PROPS = { vertical: false, stroke: "var(--border)", strokeDasharray: "0" } as const;
export const AXIS_PROPS = { tick: { fontSize: 12, fill: "var(--text-subtle)" }, tickLine: false, axisLine: false } as const;
