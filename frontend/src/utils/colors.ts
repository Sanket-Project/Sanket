import type { IndustryCode, SignalStatus, GxPBatchStatus } from "@/types/api";

/* ════════════════════════════════════════════════════════════════════════════
   Single source of truth for industry accents.
   These hexes MUST stay in sync with the [data-industry] blocks in
   styles/index.css (which drive the --accent CSS variable for the whole shell).
   ════════════════════════════════════════════════════════════════════════════ */

export interface IndustryTheme {
  /** Solid accent (light mode) */
  accent: string;
  /** Darker accent for hovers / strong text */
  accentStrong: string;
  /** Linear gradient used for hero icon tiles, logos, etc. */
  gradient: string;
  /** Human-readable workspace name */
  display: string;
}

export const INDUSTRY_THEME: Record<IndustryCode, IndustryTheme> = {
  fashion: {
    accent: "#03363D",
    accentStrong: "#022429",
    gradient: "linear-gradient(135deg, #03363D 0%, #1c525a 100%)",
    display: "Apparel & Fashion",
  },
  electronics: {
    accent: "#03363D",
    accentStrong: "#022429",
    gradient: "linear-gradient(135deg, #054c55 0%, #207e8c 100%)",
    display: "Consumer Electronics",
  },
  pharma: {
    accent: "#03363D",
    accentStrong: "#022429",
    gradient: "linear-gradient(135deg, #022b31 0%, #29a0b0 100%)",
    display: "Pharmaceuticals",
  },
  agrocenter: {
    accent: "#03363D",
    accentStrong: "#022429",
    gradient: "linear-gradient(135deg, #03363D 0%, #46929c 100%)",
    display: "Agricultural Inputs",
  },
  hardware: {
    accent: "#03363D",
    accentStrong: "#022429",
    gradient: "linear-gradient(135deg, #04444d 0%, #5ba7b2 100%)",
    display: "Hardware & Industrial Supply",
  },
};

export const industryTheme = (code: IndustryCode): IndustryTheme =>
  INDUSTRY_THEME[code] ?? INDUSTRY_THEME.fashion;

// ── Backwards-compatible flat maps (derive from INDUSTRY_THEME) ──────────────
export const industryAccent: Record<IndustryCode, string> = Object.fromEntries(
  (Object.keys(INDUSTRY_THEME) as IndustryCode[]).map((k) => [k, INDUSTRY_THEME[k].accent]),
) as Record<IndustryCode, string>;

export const industryGradient: Record<IndustryCode, string> = Object.fromEntries(
  (Object.keys(INDUSTRY_THEME) as IndustryCode[]).map((k) => [k, INDUSTRY_THEME[k].gradient]),
) as Record<IndustryCode, string>;

export const industryDisplay: Record<IndustryCode, string> = Object.fromEntries(
  (Object.keys(INDUSTRY_THEME) as IndustryCode[]).map((k) => [k, INDUSTRY_THEME[k].display]),
) as Record<IndustryCode, string>;

// ── Status badge styles (refined for light + dark) ───────────────────────────
export const signalStatusColor: Record<SignalStatus, string> = {
  pending: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-500/15 dark:text-amber-300 dark:border-amber-500/30",
  validated: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-500/15 dark:text-emerald-300 dark:border-emerald-500/30",
  rejected: "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-500/15 dark:text-rose-300 dark:border-rose-500/30",
  expired: "bg-slate-100 text-slate-600 border-slate-200 dark:bg-white/5 dark:text-slate-400 dark:border-white/10",
};

export const gxpStatusColor: Record<GxPBatchStatus, string> = {
  quarantine: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-500/15 dark:text-amber-300 dark:border-amber-500/30",
  released: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-500/15 dark:text-emerald-300 dark:border-emerald-500/30",
  rejected: "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-500/15 dark:text-rose-300 dark:border-rose-500/30",
  recalled: "bg-red-100 text-red-700 border-red-300 dark:bg-red-500/20 dark:text-red-300 dark:border-red-500/40",
  expired: "bg-slate-100 text-slate-600 border-slate-200 dark:bg-white/5 dark:text-slate-400 dark:border-white/10",
};
