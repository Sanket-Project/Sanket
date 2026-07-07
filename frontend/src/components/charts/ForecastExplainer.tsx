import { AlertCircle, Sparkles, CheckCircle2, Info } from "lucide-react";

/**
 * ForecastExplainer — always-visible inline quantile guide.
 * Replaces the old collapsible accordion with a clear 3-card layout
 * that's immediately readable without needing to click.
 */
export const ForecastExplainer = () => {
  return (
    <div className="glass rounded-2xl p-5 space-y-4">
      <div className="flex items-center gap-2">
        <Info size={14} className="text-violet-500 dark:text-violet-400" />
        <span className="text-sm font-bold text-slate-800 dark:text-slate-100">
          How to Read These Forecasts
        </span>
        <span className="text-[10px] text-slate-400 dark:text-slate-500 ml-1">
          — Each SKU gets three numbers, not one
        </span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {/* P10 */}
        <div className="rounded-xl border border-rose-200/70 dark:border-rose-800/40 bg-rose-50/40 dark:bg-rose-900/10 p-4">
          <div className="flex items-center gap-2 mb-2">
            <div className="h-7 w-7 rounded-lg bg-rose-100 dark:bg-rose-900/40 flex items-center justify-center">
              <AlertCircle size={13} className="text-rose-500 dark:text-rose-400" />
            </div>
            <div>
              <span className="text-[10px] font-black text-rose-600 dark:text-rose-400 uppercase tracking-wider">P10</span>
              <span className="text-[10px] text-slate-400 dark:text-slate-500 ml-1">Conservative</span>
            </div>
          </div>
          <p className="text-[11px] text-slate-600 dark:text-slate-300 leading-relaxed">
            <strong className="text-slate-800 dark:text-slate-100">90% chance demand exceeds this.</strong> Use it to
            avoid over-ordering — the safe minimum to commit to.
          </p>
          <div className="mt-2.5 flex items-center gap-1">
            <div className="h-1 w-1 rounded-full bg-rose-400" />
            <span className="text-[9px] font-semibold text-rose-500 dark:text-rose-400">Best for: avoiding excess stock</span>
          </div>
        </div>

        {/* P50 */}
        <div className="rounded-xl border border-violet-200/70 dark:border-violet-800/40 bg-violet-50/40 dark:bg-violet-900/10 p-4">
          <div className="flex items-center gap-2 mb-2">
            <div className="h-7 w-7 rounded-lg bg-violet-100 dark:bg-violet-900/40 flex items-center justify-center">
              <Sparkles size={13} className="text-violet-500 dark:text-violet-400" />
            </div>
            <div>
              <span className="text-[10px] font-black text-violet-600 dark:text-violet-400 uppercase tracking-wider">P50</span>
              <span className="text-[10px] text-slate-400 dark:text-slate-500 ml-1">Expected</span>
            </div>
          </div>
          <p className="text-[11px] text-slate-600 dark:text-slate-300 leading-relaxed">
            <strong className="text-slate-800 dark:text-slate-100">The median — your planning baseline.</strong> Demand is
            equally likely to be higher or lower than this number.
          </p>
          <div className="mt-2.5 flex items-center gap-1">
            <div className="h-1 w-1 rounded-full bg-violet-400" />
            <span className="text-[9px] font-semibold text-violet-500 dark:text-violet-400">Best for: everyday planning</span>
          </div>
        </div>

        {/* P90 */}
        <div className="rounded-xl border border-emerald-200/70 dark:border-emerald-800/40 bg-emerald-50/40 dark:bg-emerald-900/10 p-4">
          <div className="flex items-center gap-2 mb-2">
            <div className="h-7 w-7 rounded-lg bg-emerald-100 dark:bg-emerald-900/40 flex items-center justify-center">
              <CheckCircle2 size={13} className="text-emerald-500 dark:text-emerald-400" />
            </div>
            <div>
              <span className="text-[10px] font-black text-emerald-600 dark:text-emerald-400 uppercase tracking-wider">P90</span>
              <span className="text-[10px] text-slate-400 dark:text-slate-500 ml-1">Optimistic</span>
            </div>
          </div>
          <p className="text-[11px] text-slate-600 dark:text-slate-300 leading-relaxed">
            <strong className="text-slate-800 dark:text-slate-100">Only 10% chance demand exceeds this.</strong> Use it
            to size your safety stock so you're protected against demand spikes.
          </p>
          <div className="mt-2.5 flex items-center gap-1">
            <div className="h-1 w-1 rounded-full bg-emerald-400" />
            <span className="text-[9px] font-semibold text-emerald-600 dark:text-emerald-400">Best for: safety stock target</span>
          </div>
        </div>
      </div>

      {/* Pro tip */}
      <div className="flex items-start gap-2.5 p-3 rounded-xl bg-slate-50 dark:bg-slate-800/40 border border-slate-200/60 dark:border-slate-700/40">
        <Info size={13} className="text-violet-500 dark:text-violet-400 shrink-0 mt-0.5" />
        <p className="text-[11px] text-slate-500 dark:text-slate-400 leading-relaxed">
          <strong className="text-slate-700 dark:text-slate-200">Planner tip:</strong> The gap between P10 and P90 is your
          uncertainty window. A <em>wide gap</em> means high demand volatility — carry more safety stock.
          A <em>narrow gap</em> means predictable demand — you can run leaner.
        </p>
      </div>
    </div>
  );
};
