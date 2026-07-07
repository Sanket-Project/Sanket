import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { DollarSign, TrendingUp, Package, AlertTriangle, Warehouse } from "lucide-react";
import { Link } from "react-router-dom";
import { financialApi } from "@/api/financial";
import { Card } from "@/components/ui/Card";
import { KPICard } from "@/components/charts/KPICard";
import { PageLoader } from "@/components/ui/Spinner";
import { fmtCompact } from "@/utils/format";
import { useIndustryStore } from "@/stores/industry";
import { useFormattedCurrency } from "@/hooks/useFormattedCurrency";

export const FinancialImpactPage = () => {
  const industry = useIndustryStore((s) => s.activeIndustry);
  const [horizon, setHorizon] = useState(12);
  const { formatPrice } = useFormattedCurrency();
  const fmt = (n: number) => formatPrice(n, "USD", { compact: true });

  const { data: impact, isLoading: loadingImpact } = useQuery({
    queryKey: ["financial-impact", industry, horizon],
    queryFn: () => financialApi.impact(horizon),
  });

  const { data: costs, isLoading: loadingCosts } = useQuery({
    queryKey: ["cost-analysis", industry],
    queryFn: () => financialApi.costAnalysis(),
  });

  if (loadingImpact || loadingCosts) return <PageLoader />;

  const nEstimate = (costs?.skus ?? []).filter((s) => s.on_hand_source === "fallback").length;

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <div className="flex items-center gap-2 text-violet-600 text-sm font-medium uppercase tracking-wider">
            <DollarSign size={14} /> Financial Impact
          </div>
          <h1 className="text-3xl font-bold tracking-tight mt-1">Revenue at risk & inventory costs</h1>
          <p className="text-slate-500 mt-1">Quantifies the financial exposure of current forecast uncertainty</p>
        </div>
        <select
          value={horizon}
          onChange={(e) => setHorizon(Number(e.target.value))}
          className="text-sm border border-slate-200 rounded-lg px-3 py-1.5 bg-white"
        >
          {[4, 8, 12, 26].map((w) => (
            <option key={w} value={w}>{w}w horizon</option>
          ))}
        </select>
      </div>

      {/* Estimate data quality warning */}
      {nEstimate > 0 && (
        <div className="flex items-start gap-3 rounded-xl bg-amber-50 border border-amber-200 px-4 py-3">
          <AlertTriangle size={16} className="text-amber-500 mt-0.5 shrink-0" />
          <div className="flex-1">
            <span className="font-semibold text-amber-800 text-sm">
              {nEstimate} SKU{nEstimate !== 1 ? "s" : ""} using estimated stock
            </span>
            <p className="text-amber-700 text-xs mt-0.5">
              Holding costs for those rows are calculated from <code className="font-mono bg-amber-100 px-1 rounded">safety_stock × 2</code> — an estimate, not real warehouse data. Cost figures may be inaccurate.
            </p>
          </div>
          <Link
            to="/workspace/inventory"
            className="shrink-0 flex items-center gap-1.5 text-xs font-semibold text-amber-700 hover:text-amber-900 border border-amber-300 bg-amber-100 hover:bg-amber-200 rounded-lg px-3 py-1.5 transition-colors"
          >
            <Warehouse size={12} />
            Fix in Inventory
          </Link>
        </div>
      )}

      {/* KPI strip */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <KPICard
          label="Revenue at Risk"
          value={fmt(impact?.total_revenue_at_risk ?? 0)}
          icon={<TrendingUp size={16} />}
          tone="warning"
        />
        <KPICard
          label="Excess Inventory Cost"
          value={fmt(impact?.total_excess_cost ?? 0)}
          icon={<Package size={16} />}
          tone="default"
        />
        <KPICard
          label="Total Financial Impact"
          value={fmt(impact?.net_impact ?? 0)}
          icon={<AlertTriangle size={16} />}
          tone="danger"
        />
      </div>

      {/* Inventory cost breakdown */}
      {costs && (
        <Card title="Holding vs. stockout exposure" description="Annual cost estimate per SKU">
          <div className="grid grid-cols-3 gap-4 mb-4 text-sm">
            <div className="bg-blue-50 rounded-lg p-3">
              <p className="text-slate-500 text-xs">Annual Holding Cost</p>
              <p className="font-bold text-slate-800">{fmt(costs.totals.annual_holding_cost)}</p>
            </div>
            <div className="bg-orange-50 rounded-lg p-3">
              <p className="text-slate-500 text-xs">Stockout Exposure</p>
              <p className="font-bold text-slate-800">{fmt(costs.totals.stockout_exposure_cost)}</p>
            </div>
            <div className="bg-red-50 rounded-lg p-3">
              <p className="text-slate-500 text-xs">Combined Impact</p>
              <p className="font-bold text-red-700">{fmt(costs.totals.total_impact)}</p>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100">
                  {["SKU", "On-Hand", "Source", "Safety Stock", "Holding Cost", "Excess Holding", "Stockout Risk", "Total"].map((h) => (
                    <th key={h} className="text-left py-2 px-3 text-slate-500 font-medium text-xs">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(costs.skus ?? []).slice(0, 20).map((sku) => (
                  <tr key={sku.sku_id} className="border-b border-slate-50 hover:bg-slate-50/50">
                    <td className="py-2 px-3 font-mono text-xs text-slate-700">{sku.sku_code}</td>
                    <td className="py-2 px-3 tabular-nums">{fmtCompact(sku.on_hand_units ?? sku.safety_stock)}</td>
                    <td className="py-2 px-3">
                      {sku.on_hand_source === "fallback" ? (
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-amber-100 text-amber-700 border border-amber-200">
                          <AlertTriangle size={9} /> Estimate
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                          ✓ Real
                        </span>
                      )}
                    </td>
                    <td className="py-2 px-3">{fmtCompact(sku.safety_stock)}</td>
                    <td className="py-2 px-3 text-blue-600">{fmt(sku.holding_cost_annual)}</td>
                    <td className="py-2 px-3 text-indigo-500">{fmt(sku.excess_holding_cost ?? 0)}</td>
                    <td className="py-2 px-3 text-orange-600">{fmt(sku.stockout_exposure_cost)}</td>
                    <td className="py-2 px-3 font-semibold text-red-600">{fmt(sku.total_impact)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Revenue at risk per SKU */}
      {impact && impact.by_sku.length > 0 && (
        <Card title="Revenue at risk by SKU" description="P90 − P50 demand gap × unit price">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-100">
                  {["SKU", "P50 Demand", "P90 Demand", "Unit Price", "Revenue at Risk", "Excess Cost", "Net Impact"].map((h) => (
                    <th key={h} className="text-left py-2 px-3 text-slate-500 font-medium text-xs">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {impact.by_sku.slice(0, 20).map((row) => (
                  <tr key={row.sku_id} className="border-b border-slate-50 hover:bg-slate-50/50">
                    <td className="py-2 px-3 font-mono text-xs text-slate-700">{row.sku_code}</td>
                    <td className="py-2 px-3">{fmtCompact(row.p50_demand)}</td>
                    <td className="py-2 px-3">{fmtCompact(row.p90_demand)}</td>
                    <td className="py-2 px-3">{fmt(row.unit_price)}</td>
                    <td className="py-2 px-3 text-amber-600 font-medium">{fmt(row.revenue_at_risk)}</td>
                    <td className="py-2 px-3 text-blue-600">{fmt(row.excess_inventory_cost)}</td>
                    <td className="py-2 px-3 font-semibold text-red-600">{fmt(row.total_impact)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
};
