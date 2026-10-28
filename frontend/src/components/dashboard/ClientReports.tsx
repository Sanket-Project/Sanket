import { Card } from "@/components/ui/Card";
import { BranchSales } from "@/components/charts/BranchSales";

export interface ClientReportData {
  industry: string;
  currency: string;
  imported_at: string;
  sales: { period: string; net_amount: number; net_units: number; rows: number; stores: { name: string; net_amount: number; net_units: number }[] };
  gross_profit: { period: string; net_sales: number; sales_ex_tax: number; cogs_ex_tax: number; profit: number; margin_pct: number | null; rows: number; stores: { name: string; profit: number; sales_ex_tax: number }[]; top_skus: { sku: string; profit: number; units: number }[] };
  purchases: { period: string; net_amount: number; net_units: number; rows: number; suppliers: { name: string; net_amount: number; net_units: number }[] };
  limitations: string[];
  sources: string[];
}

export function ClientReports({ report }: { report: ClientReportData }) {
  const money = (value: number) => new Intl.NumberFormat("en-IN", { style: "currency", currency: report.currency, maximumFractionDigits: 2 }).format(value);
  const count = (value: number) => value.toLocaleString("en-IN");
  const branches = report.sales.stores.filter(row => row.name.trim());
  const profitBranches = report.gross_profit.stores.filter(row => row.name.trim());
  return <div className="sales-overview sales-imported space-y-6">
    <header>
      <p className="text-sm font-medium uppercase tracking-wider text-[var(--accent)]">Sales Analytics · Imported reports</p>
      <h1 className="mt-2 font-heading text-3xl font-semibold tracking-tight text-content sm:text-4xl">Your sales, at a glance</h1>
      <p className="mt-2 text-sm text-content-muted">See how much you sold and where it came from.</p>
    </header>
    <Card className="!bg-[var(--accent)] !text-[var(--accent-fg)] !border-transparent !p-6 sm:!p-8">
      <div className="grid items-end gap-8 md:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div>
          <p className="text-sm opacity-80">Sales after returns</p>
          <p className="mt-3 break-words font-heading text-4xl font-semibold tracking-tight sm:text-5xl">{money(report.sales.net_amount)}</p>
          <p className="mt-4 text-sm opacity-80">{report.sales.period}</p>
        </div>
        <div className="border-t border-current/20 pt-5 md:border-l md:border-t-0 md:pl-8 md:pt-0">
          <p className="font-mono text-3xl font-semibold">{count(report.sales.net_units)}</p>
          <p className="mt-1 text-sm opacity-80">items sold, after returns</p>
          <p className="mt-4 text-xs leading-relaxed opacity-80">From your uploaded sales report. Growth is unavailable without a comparable earlier period.</p>
        </div>
      </div>
    </Card>
    <BranchSales period={report.sales.period} net rows={branches.map(row => ({ name: row.name, amount: row.net_amount, units: row.net_units, currency: report.currency }))} unassigned={report.sales.stores.length - branches.length} />
    <div className="pt-2">
      <h2 className="font-heading text-xl font-semibold text-content">Behind the sales</h2>
      <p className="mt-1 text-sm text-content-muted">Profit and purchases come from separate reports. Check each date range before comparing.</p>
    </div>
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="Gross profit" description={report.gross_profit.period}>
        <p className="font-mono text-2xl font-semibold text-content">{money(report.gross_profit.profit)}</p>
        <p className="mt-2 text-sm text-content-muted">What remains after the cost of goods, before other business expenses.</p>
        <p className="mt-2 text-sm text-content-muted">{report.gross_profit.margin_pct == null ? "Margin unavailable" : `${report.gross_profit.margin_pct.toFixed(2)}% margin on sales excluding tax`}</p>
      </Card>
      <Card title="Stock purchased" description={report.purchases.period}>
        <p className="font-mono text-2xl font-semibold text-content">{money(report.purchases.net_amount)}</p>
        <p className="mt-2 text-sm text-content-muted">What you bought from suppliers, after purchase returns.</p>
        <p className="mt-2 text-sm text-content-muted">{count(report.purchases.net_units)} net units · purchase returns included</p>
      </Card>
    </div>
    {profitBranches.length > 0 && <Card title="Profit by branch" description={report.gross_profit.period}>
      <p className="mb-4 text-sm text-content-muted">Sales excluding tax: {money(report.gross_profit.sales_ex_tax)} · Cost of goods excluding tax: {money(report.gross_profit.cogs_ex_tax)}</p>
      <ReportTable headings={["Branch", "Sales excl. tax", "Gross profit"]} rows={[...profitBranches].sort((a, b) => b.profit - a.profit).map(r => [r.name, money(r.sales_ex_tax), money(r.profit)])} />
    </Card>}
    <Card title="Products earning the most profit" description={report.gross_profit.period}>
      <p className="mb-4 text-sm text-content-muted">These are product codes (SKUs) ranked by reported gross profit, rather than items sold.</p>
        <ReportTable headings={["SKU", "Reported units", "Gross profit"]} rows={report.gross_profit.top_skus.map(r => [r.sku, count(r.units), money(r.profit)])} />
    </Card>
    <Card title="Supplier purchases" description={`${report.purchases.rows} invoice and purchase-return records. Amounts include reported taxes and discounts.`}>
      <ReportTable headings={["Supplier", "Net units", "Net purchases"]} rows={report.purchases.suppliers.map(r => [r.name, count(r.net_units), money(r.net_amount)])} />
    </Card>
    <Card title="About these numbers">
      <p className="mb-4 text-sm text-content-muted">Only figures present in your reports are shown. A sales-over-time chart needs dated sales records.</p>
      <ul className="list-disc space-y-2 pl-5 text-sm text-content-muted">{report.limitations.map(line => <li key={line}>{line}</li>)}</ul>
      <details className="mt-5 text-sm text-content-muted"><summary className="cursor-pointer py-2">Source files · imported {report.imported_at.slice(0, 10)}</summary><ul className="mt-2 space-y-1">{report.sources.map(source => <li key={source}>{source}</li>)}</ul></details>
    </Card>
  </div>;
}

function ReportTable({ headings, rows }: { headings: string[]; rows: string[][] }) {
  return <div className="overflow-x-auto"><table className="w-full text-left text-sm text-content">
    <thead><tr className="border-b border-line">{headings.map((heading, i) => <th scope="col" key={heading} className={`px-3 py-3 font-medium text-content-muted ${i ? "text-right" : ""}`}>{heading}</th>)}</tr></thead>
    <tbody>{rows.map((row) => <tr key={row[0]} className="border-b border-line last:border-0">{row.map((cell, i) => <td key={i} className={`px-3 py-3 ${i ? "whitespace-nowrap text-right tabular-nums" : "min-w-48"}`}>{cell}</td>)}</tr>)}</tbody>
  </table></div>;
}
