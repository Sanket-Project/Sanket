import { Card } from "@/components/ui/Card";
import { useFormattedCurrency } from "@/hooks/useFormattedCurrency";
import { fmtNumber } from "@/utils/format";

export interface BranchSalesRow {
  name: string;
  amount: number | null;
  units: number;
  currency: string | null;
  revenue_by_currency?: Record<string, number>;
}

/** Direct labels keep the comparison readable without hover or color decoding. */
export function BranchSales({ rows, period, net = false, unassigned = 0, grouping = "branch" }: {
  rows: BranchSalesRow[];
  period: string;
  net?: boolean;
  unassigned?: number;
  grouping?: "branch" | "location";
}) {
  const { formatPrice } = useFormattedCurrency();
  const named = rows.filter(row => row.name.trim());
  if (!named.length) return null;
  const currencies = new Set(named.flatMap(row => row.revenue_by_currency
    ? Object.keys(row.revenue_by_currency) : row.currency ? [row.currency] : []));
  const byMoney = currencies.size === 1 && !currencies.has("unknown") && named.every(row => row.amount != null);
  const value = (row: BranchSalesRow) => byMoney ? row.amount! : row.units;
  const sorted = [...named].sort((a, b) => value(b) - value(a) || a.name.localeCompare(b.name));
  const max = Math.max(...sorted.map(row => Math.abs(value(row))), 1);
  const total = sorted.reduce((sum, row) => sum + value(row), 0);
  const hasNegative = sorted.some(row => value(row) < 0);
  const money = (row: BranchSalesRow) => row.amount == null
    ? Object.entries(row.revenue_by_currency ?? {}).map(([code, amount]) => formatPrice(amount, code)).join(" · ") || "Sales amount unavailable"
    : formatPrice(row.amount, row.currency);
  return <section aria-label={`Sales by ${grouping}`}>
    <Card title={`Sales by ${grouping}`} description={period}>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3 border-b border-line pb-5">
        <div>
          <p className="text-lg font-semibold text-content">{byMoney
            ? value(sorted[0]) > 0 ? `${sorted[0].name} has the highest sales.` : `No ${grouping} has positive sales in this period.`
            : `Compare items sold at each ${grouping}.`}</p>
          <p className="mt-1 text-sm text-content-muted">{net ? "Sales after returns." : "Sales before returns."} {byMoney ? "Longer bars mean larger amounts." : "Bars compare item counts; amounts are shown in their own currencies."}</p>
          {hasNegative && <p className="mt-2 text-sm text-content-muted">Negative values are shown with a minus sign; bar length shows their size.</p>}
        </div>
        <span className="rounded-full bg-surface-2 px-3 py-1 text-xs font-medium text-content-muted">{named.length} {named.length === 1 ? grouping : grouping === "branch" ? "branches" : "locations"}</span>
      </div>
      <ol className="max-h-[560px] space-y-6 overflow-y-auto pr-1">
        {sorted.map((row, index) => <li key={row.name} className="grid grid-cols-[1.5rem_minmax(0,1fr)] gap-3">
          <span aria-hidden="true" className="pt-0.5 font-mono text-xs text-content-subtle">{String(index + 1).padStart(2, "0")}</span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
              <p className="break-words font-medium text-content">{row.name}</p>
              <p className="font-mono text-sm font-semibold text-content">{money(row)}</p>
            </div>
            <div aria-hidden="true" className="my-2 h-2 overflow-hidden rounded-full bg-surface-3">
              <div className="h-full rounded-full bg-[var(--accent)]" style={{ width: `${Math.abs(value(row)) / max * 100}%`, opacity: value(row) < 0 ? 0.45 : 1 }} />
            </div>
            <div className="flex flex-wrap justify-between gap-2 text-xs text-content-muted">
              <span>{fmtNumber(row.units)} {net ? "items after returns" : "items sold"}{net && (row.amount ?? 0) < 0 ? " · Returns exceeded sales" : ""}</span>
              {byMoney && !hasNegative && total > 0 && <span>{Math.round(value(row) / total * 100)}% of {grouping} sales</span>}
            </div>
          </div>
        </li>)}
      </ol>
      {unassigned > 0 && <p className="mt-5 border-t border-line pt-4 text-sm text-content-muted">{fmtNumber(unassigned)} records have no {grouping} name and are excluded from this comparison.</p>}
    </Card>
  </section>;
}
