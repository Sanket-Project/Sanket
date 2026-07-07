import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { format, parseISO } from "date-fns";
import { Activity, ShoppingCart, DollarSign, Receipt } from "lucide-react";

import {
  salesAnalyticsApi,
  type TopProductPeriod,
  type SalesBucket,
} from "@/api/salesAnalytics";
import { Card } from "@/components/ui/Card";
import { KPICard } from "@/components/charts/KPICard";
import { PageLoader } from "@/components/ui/Spinner";
import { LiveIndicator } from "@/components/realtime/LiveIndicator";
import { useWebSocket } from "@/hooks/useWebSocket";
import { useIndustryStore } from "@/stores/industry";
import { fmtNumber, fmtCompact } from "@/utils/format";
import { useFormattedCurrency } from "@/hooks/useFormattedCurrency";

type Granularity = "day" | "week" | "month";

const GRANULARITY_LOOKBACK: Record<Granularity, number> = {
  day: 30,
  week: 180,
  month: 365,
};

interface LiveExtra {
  units: number;
  revenue: number;
  transactions: number;
}

const ZERO_LIVE: LiveExtra = { units: 0, revenue: 0, transactions: 0 };

export const SalesAnalyticsPage = () => {
  const industry = useIndustryStore((s) => s.activeIndustry);
  const { subscribe } = useWebSocket();
  const { formatPrice } = useFormattedCurrency();

  const [granularity, setGranularity] = useState<Granularity>("day");
  const [topPeriod, setTopPeriod] = useState<TopProductPeriod>("month");
  const [live, setLive] = useState<LiveExtra>(ZERO_LIVE);
  const [pulse, setPulse] = useState(false);

  const { data: summary, isLoading: loadingSummary, refetch: refetchSummary } = useQuery({
    queryKey: ["sales-summary", industry],
    queryFn: () => salesAnalyticsApi.summary(),
    refetchInterval: 60_000,
  });

  const { data: timeseries, isLoading: loadingSeries } = useQuery({
    queryKey: ["sales-timeseries", industry, granularity],
    queryFn: () => salesAnalyticsApi.timeseries(granularity, GRANULARITY_LOOKBACK[granularity]),
  });

  const { data: top, isLoading: loadingTop } = useQuery({
    queryKey: ["sales-top-products", industry, topPeriod],
    queryFn: () => salesAnalyticsApi.topProducts(topPeriod, 10),
  });

  // Reset the live overlay whenever the authoritative summary refetches, so we
  // don't double-count sales that the refetch has already absorbed.
  useEffect(() => {
    setLive(ZERO_LIVE);
  }, [summary?.as_of]);

  // Subscribe to sale.created events for instant "live" ticking.
  const refetchTimer = useRef<number | null>(null);
  useEffect(() => {
    const unsub = subscribe((event) => {
      if (event.type !== "sale.created") return;
      const d = event.data as { units_sold?: number; gross_revenue?: number };
      setLive((prev) => ({
        units: prev.units + (d.units_sold ?? 0),
        revenue: prev.revenue + (d.gross_revenue ?? 0),
        transactions: prev.transactions + 1,
      }));
      setPulse(true);
      window.setTimeout(() => setPulse(false), 700);
      // Reconcile with the backend shortly after the burst settles.
      if (refetchTimer.current) window.clearTimeout(refetchTimer.current);
      refetchTimer.current = window.setTimeout(() => refetchSummary(), 4_000);
    });
    return () => {
      unsub();
      if (refetchTimer.current) window.clearTimeout(refetchTimer.current);
    };
  }, [subscribe, refetchSummary]);

  const chartData = useMemo(
    () =>
      (timeseries?.series ?? []).map((p) => ({
        bucket: p.bucket,
        revenue: p.gross_revenue,
        units: p.units_sold,
      })),
    [timeseries],
  );

  if (loadingSummary) return <PageLoader />;

  const today = summary?.today;
  const liveRevenue = (today?.gross_revenue ?? 0) + live.revenue;
  const liveUnits = (today?.units_sold ?? 0) + live.units;
  const liveTxns = (today?.transactions ?? 0) + live.transactions;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-end justify-between">
        <div>
          <div className="flex items-center gap-2 text-violet-600 text-sm font-medium uppercase tracking-wider">
            <Activity size={14} /> Sales Analytics
          </div>
          <h1 className="text-3xl font-bold tracking-tight mt-1">Live sales & revenue</h1>
          <p className="text-slate-500 mt-1">
            Real-time view of what's selling across this company today, this week, month and year
          </p>
        </div>
        <LiveIndicator />
      </div>

      {/* Live "today" hero */}
      <Card padding="lg" className="relative overflow-hidden">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">
              Revenue today
            </p>
            <div
              className={
                "text-4xl font-black tracking-tight mt-1 transition-colors duration-300 " +
                (pulse ? "text-emerald-600" : "text-slate-900")
              }
            >
              {formatPrice(liveRevenue)}
            </div>
            <DeltaPill delta={today?.revenue_delta} />
          </div>
          <div>
            <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">
              Units sold today
            </p>
            <div
              className={
                "text-4xl font-black tracking-tight mt-1 transition-colors duration-300 " +
                (pulse ? "text-emerald-600" : "text-slate-900")
              }
            >
              {fmtNumber(liveUnits)}
            </div>
            <DeltaPill delta={today?.units_delta} />
          </div>
          <div>
            <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">
              Transactions today
            </p>
            <div className="text-4xl font-black tracking-tight mt-1 text-slate-900">
              {fmtNumber(liveTxns)}
            </div>
            <p className="text-[11px] text-slate-400 mt-2 font-medium">
              {today?.returns ? `${fmtNumber(today.returns)} returns` : "No returns today"}
            </p>
          </div>
        </div>
      </Card>

      {/* Period KPI strip */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <PeriodCard label="This Week" bucket={summary?.week} />
        <PeriodCard label="This Month" bucket={summary?.month} />
        <PeriodCard label="This Year" bucket={summary?.year} />
        <KPICard
          label="Avg Order Value"
          value={formatPrice(avgOrder(summary?.month))}
          icon={<Receipt size={16} />}
          subtitle="This month, gross / transaction"
        />
      </div>

      {/* Revenue trend */}
      <Card
        title="Revenue trend"
        description={`Gross revenue per ${granularity}`}
        action={
          <div className="flex gap-1 bg-slate-100 rounded-lg p-0.5">
            {(["day", "week", "month"] as Granularity[]).map((g) => (
              <button
                key={g}
                onClick={() => setGranularity(g)}
                className={
                  "px-3 py-1 text-xs font-medium rounded-md transition-colors capitalize " +
                  (granularity === g
                    ? "bg-white text-violet-700 shadow-sm"
                    : "text-slate-500 hover:text-slate-700")
                }
              >
                {g}
              </button>
            ))}
          </div>
        }
      >
        {loadingSeries ? (
          <div className="h-[300px] flex items-center justify-center text-slate-400 text-sm">
            Loading…
          </div>
        ) : chartData.length === 0 ? (
          <EmptyState />
        ) : (
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={chartData} margin={{ top: 10, right: 12, left: 0, bottom: 0 }}>
              <defs>
                <linearGradient id="rev" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#7C3AED" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#7C3AED" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 6" stroke="#e2e8f0" />
              <XAxis
                dataKey="bucket"
                tickFormatter={(d) => format(parseISO(d), granularity === "month" ? "MMM" : "MMM d")}
                stroke="#94a3b8"
                tick={{ fontSize: 11, fill: "#64748b" }}
                tickLine={false}
                minTickGap={24}
              />
              <YAxis
                stroke="#94a3b8"
                tick={{ fontSize: 11, fill: "#64748b" }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v) => fmtCompact(v as number)}
              />
              <Tooltip
                contentStyle={{
                  background: "#ffffff",
                  border: "1px solid #e2e8f0",
                  borderRadius: 8,
                  fontSize: 12,
                  color: "#0f172a",
                }}
                labelFormatter={(d) => format(parseISO(d as string), "MMM d, yyyy")}
                formatter={(value: number, name) => [
                  name === "revenue" ? formatPrice(value) : fmtNumber(value),
                  name === "revenue" ? "Revenue" : "Units",
                ]}
              />
              <Area
                type="monotone"
                dataKey="revenue"
                stroke="#7C3AED"
                strokeWidth={2.5}
                fill="url(#rev)"
                isAnimationActive
                animationDuration={900}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </Card>

      {/* Top products */}
      <Card
        title="Top selling products"
        description="What's moving and the revenue it's driving"
        action={
          <select
            value={topPeriod}
            onChange={(e) => setTopPeriod(e.target.value as TopProductPeriod)}
            className="text-sm border border-slate-200 rounded-lg px-3 py-1.5 bg-white"
          >
            <option value="today">Today</option>
            <option value="week">This week</option>
            <option value="month">This month</option>
            <option value="year">This year</option>
            <option value="all">All time</option>
          </select>
        }
      >
        {loadingTop ? (
          <div className="py-8 text-center text-slate-400 text-sm">Loading…</div>
        ) : (top?.products.length ?? 0) === 0 ? (
          <EmptyState />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100">
                  {["#", "Product", "SKU", "Units Sold", "Revenue", "Returns"].map((h) => (
                    <th key={h} className="text-left py-2 px-3 text-slate-500 font-medium text-xs">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(top?.products ?? []).map((p, i) => (
                  <tr key={p.sku_id} className="border-b border-slate-50 hover:bg-slate-50/50">
                    <td className="py-2 px-3 text-slate-400 tabular-nums">{i + 1}</td>
                    <td className="py-2 px-3 font-medium text-slate-800">{p.product_name}</td>
                    <td className="py-2 px-3 font-mono text-xs text-slate-500">{p.sku_code}</td>
                    <td className="py-2 px-3 tabular-nums font-semibold">{fmtNumber(p.units_sold)}</td>
                    <td className="py-2 px-3 text-emerald-600 font-medium">{formatPrice(p.gross_revenue)}</td>
                    <td className="py-2 px-3 text-slate-500 tabular-nums">{fmtNumber(p.returns)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
};

// ── small presentational helpers ─────────────────────────────────────────────

const avgOrder = (b?: SalesBucket): number => {
  if (!b || b.transactions === 0) return 0;
  return b.gross_revenue / b.transactions;
};

const PeriodCard = ({ label, bucket }: { label: string; bucket?: SalesBucket }) => {
  const { formatPrice } = useFormattedCurrency();
  return (
    <KPICard
      label={label}
      value={formatPrice(bucket?.gross_revenue ?? 0)}
      delta={bucket?.revenue_delta ?? undefined}
      icon={<DollarSign size={16} />}
      subtitle={`${fmtNumber(bucket?.units_sold ?? 0)} units · ${fmtNumber(bucket?.transactions ?? 0)} orders`}
    />
  );
};

const DeltaPill = ({ delta }: { delta?: number | null }) => {
  if (delta == null) {
    return <p className="text-[11px] text-slate-400 mt-2 font-medium">No prior baseline</p>;
  }
  const up = delta >= 0;
  return (
    <span
      className={
        "inline-flex items-center gap-1 mt-2 px-2 py-0.5 rounded-full text-[11px] font-bold " +
        (up ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700")
      }
    >
      {up ? "+" : ""}
      {(delta * 100).toFixed(1)}% vs prior period
    </span>
  );
};

const EmptyState = () => (
  <div className="py-10 flex flex-col items-center justify-center text-center">
    <ShoppingCart size={28} className="text-slate-300 mb-2" />
    <p className="text-sm font-medium text-slate-500">No sales recorded yet</p>
    <p className="text-xs text-slate-400 mt-1">
      Sales appear here as soon as your feed posts to{" "}
      <code className="font-mono bg-slate-100 px-1 rounded">/analytics/sales/ingest</code>
    </p>
  </div>
);
