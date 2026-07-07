import { format, formatDistanceToNow, parseISO } from "date-fns";

export const fmtDate = (iso: string | Date | null | undefined, pattern = "MMM d, yyyy") => {
  if (!iso) return "—";
  const d = typeof iso === "string" ? parseISO(iso) : iso;
  return Number.isNaN(d.getTime()) ? "—" : format(d, pattern);
};

export const fmtDateTime = (iso: string | Date | null | undefined) =>
  fmtDate(iso, "MMM d, yyyy 'at' HH:mm");

export const fmtRelative = (iso: string | Date | null | undefined) => {
  if (!iso) return "—";
  const d = typeof iso === "string" ? parseISO(iso) : iso;
  return Number.isNaN(d.getTime()) ? "—" : formatDistanceToNow(d, { addSuffix: true });
};

const compactFmt = new Intl.NumberFormat("en-US", {
  notation: "compact",
  compactDisplay: "short",
  maximumFractionDigits: 1,
});

export const fmtCompact = (n: number | null | undefined) =>
  n == null ? "—" : compactFmt.format(n);

export const fmtNumber = (n: number | null | undefined, digits = 0) =>
  n == null
    ? "—"
    : n.toLocaleString("en-US", {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      });

export const fmtCurrency = (
  n: number | null | undefined,
  currency = "USD",
) =>
  n == null
    ? "—"
    : new Intl.NumberFormat("en-US", {
        style: "currency",
        currency,
        maximumFractionDigits: 0,
      }).format(n);

export const fmtPct = (n: number | null | undefined, digits = 1) =>
  n == null
    ? "—"
    : `${(n * 100).toLocaleString("en-US", {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      })}%`;
