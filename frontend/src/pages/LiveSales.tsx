import { useEffect } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import clsx from "clsx";
import {
  ShoppingCart,
  DollarSign,
  Package,
  Receipt,
  Clock,
  Plug,
  TrendingUp,
} from "lucide-react";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { PageLoader } from "@/components/ui/Spinner";
import { integrationsApi } from "@/api/integrations";
import { useWebSocket } from "@/hooks/useWebSocket";
import { fmtCompact, fmtRelative } from "@/utils/format";

const LIVE_KEY = ["integration", "shopify", "live"];

function Sparkline({ data }: { data: number[] }) {
  const max = Math.max(1, ...data);
  return (
    <div className="flex items-end gap-1 h-24">
      {data.map((v, i) => (
        <div
          key={i}
          className="flex-1 rounded-t bg-gradient-to-t from-emerald-500/70 to-emerald-400 dark:from-emerald-500/50 dark:to-emerald-400/80 transition-all duration-500"
          style={{ height: `${Math.max(2, (v / max) * 100)}%` }}
          title={`${v} units`}
        />
      ))}
    </div>
  );
}

function Kpi({
  label,
  value,
  icon,
  tone = "default",
}: {
  label: string;
  value: string;
  icon: React.ReactNode;
  tone?: "default" | "success" | "accent";
}) {
  const toneCls = {
    default: "text-slate-400",
    success: "text-emerald-500",
    accent: "text-violet-500",
  }[tone];
  return (
    <Card padding="md">
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{label}</span>
        <span className={toneCls}>{icon}</span>
      </div>
      <div className="text-2xl font-black text-slate-900 dark:text-white tabular-nums mt-2">{value}</div>
    </Card>
  );
}

export const LiveSalesPage = () => {
  const qc = useQueryClient();
  const { isConnected, subscribe } = useWebSocket();

  const { data, isLoading } = useQuery({
    queryKey: LIVE_KEY,
    queryFn: integrationsApi.shopifyLive,
    refetchInterval: 30_000, // polling fallback when WS isn't delivering
  });

  // Refetch instantly when a live sale event arrives over the websocket.
  useEffect(() => {
    return subscribe((evt) => {
      if (evt.type === "sale.created") {
        qc.invalidateQueries({ queryKey: LIVE_KEY });
      }
    });
  }, [subscribe, qc]);

  if (isLoading || !data) return <PageLoader />;

  return (
    <div className="space-y-4 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white flex items-center gap-2">
            <ShoppingCart size={22} className="text-emerald-500" />
            Live Sales
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Real-time order activity from your connected Shopify store.
          </p>
        </div>
        <span
          className={clsx(
            "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-bold",
            isConnected
              ? "text-emerald-700 bg-emerald-50 dark:bg-emerald-900/20 dark:text-emerald-300"
              : "text-slate-500 bg-slate-100 dark:bg-white/5",
          )}
        >
          <span className={clsx("h-2 w-2 rounded-full", isConnected ? "bg-emerald-500 animate-pulse" : "bg-slate-400")} />
          {isConnected ? "Live" : "Polling"}
        </span>
      </div>

      {!data.connected ? (
        /* Empty state */
        <Card padding="lg">
          <div className="flex flex-col items-center text-center py-10">
            <div className="h-14 w-14 rounded-2xl bg-slate-100 dark:bg-white/5 flex items-center justify-center text-slate-400 mb-4">
              <Plug size={26} />
            </div>
            <h3 className="text-base font-bold text-slate-800 dark:text-slate-100">No store connected</h3>
            <p className="text-sm text-slate-500 dark:text-slate-400 mt-1 max-w-sm">
              Connect a Shopify store to start monitoring live sales. Orders flow in automatically every few minutes (or instantly via webhooks once deployed).
            </p>
            <Link to="/workspace/integrations" className="mt-5">
              <Button variant="primary" icon={<Plug size={15} />}>Connect Shopify</Button>
            </Link>
          </div>
        </Card>
      ) : (
        <>
          {/* KPIs */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <Kpi label="Today's Revenue" value={data.today_revenue.toLocaleString(undefined, { maximumFractionDigits: 0 })} icon={<DollarSign size={16} />} tone="success" />
            <Kpi label="Units Sold Today" value={fmtCompact(data.today_units)} icon={<Package size={16} />} tone="accent" />
            <Kpi label="Orders Today" value={fmtCompact(data.today_orders)} icon={<Receipt size={16} />} />
            <Kpi label="Last Sale" value={data.last_sale_at ? fmtRelative(data.last_sale_at) : "—"} icon={<Clock size={16} />} />
          </div>

          {/* Sparkline + recent feed */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <Card className="lg:col-span-2" title="Units — last 24 hours" description="Hourly order volume">
              {data.sparkline_hourly.some((v) => v > 0) ? (
                <Sparkline data={data.sparkline_hourly} />
              ) : (
                <div className="h-24 flex items-center justify-center text-sm text-slate-400">
                  No sales in the last 24 hours yet.
                </div>
              )}
            </Card>

            <Card title="Recent Orders" description="Most recent line items">
              {data.recent.length === 0 ? (
                <div className="text-sm text-slate-400 py-6 text-center">Waiting for the first sale…</div>
              ) : (
                <div className="space-y-2 max-h-80 overflow-y-auto pr-1">
                  {data.recent.map((r, i) => (
                    <div
                      key={`${r.order_id}-${i}`}
                      className="flex items-center justify-between gap-3 p-2.5 rounded-xl bg-slate-50/70 dark:bg-white/5 border border-slate-200/60 dark:border-white/10"
                    >
                      <div className="min-w-0">
                        <p className="text-xs font-bold text-slate-700 dark:text-slate-200 truncate">
                          {r.sku_code ?? "—"}
                        </p>
                        <p className="text-[10px] text-slate-400 truncate">{r.description ?? r.order_id ?? ""}</p>
                      </div>
                      <div className="text-right shrink-0">
                        <p className="text-xs font-bold text-emerald-600 dark:text-emerald-400 flex items-center gap-1 justify-end">
                          <TrendingUp size={11} /> {r.units}×
                        </p>
                        <p className="text-[10px] text-slate-400">{fmtRelative(r.sale_time)}</p>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </div>

          <p className="text-[11px] text-slate-400 dark:text-slate-500">
            Updates arrive live over websocket when available, and are refreshed at least every 30s. Polling pulls new orders every 5 minutes; webhooks deliver instantly once SANKET is deployed on a public URL.
          </p>
        </>
      )}
    </div>
  );
};
