import { useEffect, useRef, useState } from "react";
import { NavLink } from "react-router-dom";
import clsx from "clsx";
import { LogoMark } from "../ui/Logo";
import {
  LayoutDashboard,
  Package,
  Boxes,
  Radio,
  LineChart,
  Settings as SettingsIcon,
  ShieldCheck,
  TrendingUp,
  AlertOctagon,
  Warehouse,
  Plug,
  BarChart3,
  Target,
  FlaskConical,
  Award,
  Stethoscope,
  MessageCircle,
  ChevronLeft,
  ChevronRight,
  Search,
  X,
  type AppIcon,
} from "@/components/ui/icons";
import { useQuery } from "@tanstack/react-query";
import { useWorkspaceIndustry } from "@/hooks/useWorkspaceIndustry";
import { useSidebarStore } from "@/stores/sidebar";
import { buildApi, shortSha } from "@/api/build";
import { decisionsApi } from "@/api/decisions";

/**
 * The commit the running backend was built from.
 *
 * Deliberately visible rather than buried in an admin page: the failure this
 * guards against is a reviewer believing a fix is live when the running build
 * predates it, and that belief is only corrected by something they see without
 * looking for it. "unknown" means the build did not come from CI.
 */
const BuildStamp = () => {
  const { data } = useQuery({
    queryKey: ["build-info"],
    queryFn: buildApi.info,
    staleTime: 5 * 60_000,
    retry: false,
  });
  if (!data || import.meta.env.VITE_SHOW_BUILD_STAMP !== "true") return null;
  const sha = shortSha(data.git_sha);
  const untrusted = sha === "unknown" || sha === "dev-local";
  return (
    <p
      className={clsx(
        "px-4 pt-2 font-mono text-[10px] leading-none tracking-wide",
        untrusted ? "text-amber-500/70" : "text-content-muted/60 lg:text-[#BDD9D7]/40",
      )}
      title={
        untrusted
          ? `Backend build ${data.git_sha} — not produced by CI, so its provenance is unverified`
          : `Backend build ${data.git_sha}`
      }
    >
      build {sha}
    </p>
  );
};

const DESKTOP_QUERY = "(min-width: 1024px)";
const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select, textarea, [tabindex]:not([tabindex="-1"])';

/** Matches Tailwind's `lg` breakpoint, where the sidebar is a permanent rail. */
function useIsDesktop() {
  const [desktop, setDesktop] = useState(
    () => typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia(DESKTOP_QUERY).matches,
  );
  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;
    const mq = window.matchMedia(DESKTOP_QUERY);
    const onChange = () => setDesktop(mq.matches);
    mq.addEventListener?.("change", onChange);
    return () => mq.removeEventListener?.("change", onChange);
  }, []);
  return desktop;
}

const isApplePlatform = () =>
  typeof navigator !== "undefined" && /Mac|iPhone|iPad|iPod/i.test(navigator.platform || navigator.userAgent);

interface NavEntry {
  to: string;
  label: string;
  icon: AppIcon;
  exact?: boolean;
}

const NAV_PLAN: NavEntry[] = [
  { to: "/workspace", label: "Dashboard", icon: LayoutDashboard, exact: true },
  { to: "/workspace/decisions", label: "Decisions", icon: Target },
  { to: "/workspace/forecasts", label: "Forecasts", icon: LineChart },
  { to: "/workspace/scenarios", label: "Scenarios", icon: FlaskConical },
];

const NAV_STOCK: NavEntry[] = [
  { to: "/workspace/products", label: "Products", icon: Package },
  { to: "/workspace/skus", label: "SKUs", icon: Boxes },
  { to: "/workspace/inventory", label: "Inventory", icon: Warehouse },
  { to: "/workspace/alerts", label: "Shortage Alerts", icon: AlertOctagon },
];

const NAV_MEASURE: NavEntry[] = [
  { to: "/workspace/trends", label: "Trend Analysis", icon: TrendingUp },
  { to: "/workspace/sales-analytics", label: "Sales Analytics", icon: BarChart3 },
  { to: "/workspace/roi", label: "ROI Dashboard", icon: Award },
  { to: "/workspace/forecast-accuracy", label: "Forecast Accuracy", icon: BarChart3 },
];

const NAV_DATA: NavEntry[] = [
  { to: "/workspace/signals", label: "External Signals", icon: Radio },
  { to: "/workspace/data-quality", label: "Data Quality", icon: Stethoscope },
  { to: "/workspace/integrations", label: "Integrations", icon: Plug },
  { to: "/workspace/notifications", label: "WhatsApp Digest", icon: MessageCircle },
];

function NavItem({
  entry,
  collapsed,
  onNavigate,
  badge,
}: {
  entry: NavEntry;
  collapsed: boolean;
  onNavigate?: () => void;
  badge?: number;
}) {
  const { to, label, icon: Icon, exact } = entry;
  return (
    <NavLink
      to={to}
      end={exact}
      onClick={onNavigate}
      aria-label={collapsed ? label : undefined}
      className={({ isActive }) =>
        clsx(
          "group relative flex items-center rounded-xl text-sm font-medium transition-all duration-200 tactile-press",
          collapsed ? "justify-center h-10 w-10 mx-auto" : "gap-3 px-4 py-2.5 w-full",
          isActive
            ? "text-[var(--accent)] bg-[var(--accent-soft)] font-semibold shadow-sm lg:text-[#BDD9D7] lg:bg-white/[0.08]"
            : "text-content-muted hover:text-content hover:bg-surface-3 lg:text-[#BDD9D7]/70 lg:hover:text-white lg:hover:bg-white/[0.04]",
        )
      }
    >
      {({ isActive }) => (
        <>
          {isActive && !collapsed && (
            <span className="absolute left-0 top-1/2 -translate-y-1/2 h-5 w-[3px] rounded-r-full bg-[#BDD9D7] shadow-[0_0_8px_rgba(189,217,215,0.6)]" aria-hidden="true" />
          )}
          <Icon
            size={18}
            aria-hidden="true"
            className={clsx("shrink-0 transition-transform duration-150 group-hover:scale-105")}
          />
          {!collapsed && <span className="min-w-0 flex-1 truncate">{label}</span>}
          {!collapsed && badge != null && badge > 0 && (
            <span className="min-w-5 rounded-full bg-rose-500 px-1.5 py-0.5 text-center font-mono text-[10px] font-bold leading-none text-white" aria-label={`${badge} pending`}>
              {badge > 99 ? "99+" : badge}
            </span>
          )}
          {collapsed && (
            <span className="pointer-events-none absolute left-14 z-50 whitespace-nowrap rounded-lg border border-line bg-surface px-2.5 py-1.5 text-xs font-semibold text-content opacity-0 shadow-md transition-all duration-150 group-hover:translate-x-1 group-hover:opacity-100 lg:border-white/10 lg:bg-[#03363D] lg:text-[#BDD9D7]" aria-hidden="true">
              {label}
            </span>
          )}
        </>
      )}
    </NavLink>
  );
}

function SectionLabel({ children, collapsed }: { children: string; collapsed: boolean }) {
  if (collapsed) return <div className="my-2.5 mx-2 border-t border-line lg:border-white/10" />;
  return (
    <p className="px-4 mb-2 mt-5 text-[10px] font-bold uppercase tracking-widest text-content-subtle lg:text-[#BDD9D7]/40">
      {children}
    </p>
  );
}

export const Sidebar = () => {
  const industry = useWorkspaceIndustry();
  const { collapsed, toggle, setCollapsed, mobileOpen, setMobileOpen } = useSidebarStore();
  const [search, setSearch] = useState("");
  const searchRef = useRef<HTMLInputElement>(null);
  const asideRef = useRef<HTMLElement>(null);
  const openerRef = useRef<HTMLElement | null>(null);
  const isDesktop = useIsDesktop();
  const drawerOpen = !isDesktop && mobileOpen;
  const isPharma = industry === "pharma";
  const closeMobile = () => setMobileOpen(false);
  // Rail collapse is a desktop concept; the mobile drawer always shows full nav.
  const c = collapsed && !mobileOpen;

  const { data: decisionData } = useQuery({
    queryKey: ["decisions", industry, "open", "sidebar"],
    queryFn: () => decisionsApi.list({ status: "open", limit: 200 }),
    staleTime: 30_000,
    retry: false,
  });
  const openDecisionCount = decisionData?.decisions.length ?? 0;
  const riskCount = decisionData?.decisions.filter((decision) => {
    const cover = decision.inputs.days_of_cover;
    return decision.urgency === "critical" || decision.urgency === "high" ||
      (typeof cover === "number" && cover <= decision.inputs.lead_time_days);
  }).length ?? 0;
  const badgeFor = (to: string) => to.endsWith("/decisions") ? openDecisionCount : to.endsWith("/alerts") ? riskCount : undefined;
  const normalizedSearch = search.trim().toLowerCase();
  const filterEntries = (entries: NavEntry[]) => normalizedSearch
    ? entries.filter((entry) => entry.label.toLowerCase().includes(normalizedSearch))
    : entries;
  const visibleSections = [
    { label: "Plan", entries: filterEntries(NAV_PLAN) },
    { label: "Stock", entries: filterEntries(NAV_STOCK) },
    { label: "Measure", entries: filterEntries(NAV_MEASURE) },
    { label: "Data", entries: filterEntries(NAV_DATA) },
  ];

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "/") {
        e.preventDefault();
        toggle();
      }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setCollapsed(false);
        window.setTimeout(() => searchRef.current?.focus(), 50);
      }
      if (e.key === "Escape") setMobileOpen(false);
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [toggle, setCollapsed, setMobileOpen]);

  // Accessible drawer (deep audit F11): on open, remember the opener and move
  // focus inside; the page behind becomes inert. On close, restore focus. A
  // closed drawer on mobile is inert so it cannot be tabbed into off-screen.
  useEffect(() => {
    const aside = asideRef.current;
    const main = document.getElementById("app-main-column");
    if (isDesktop) {
      aside?.removeAttribute("inert");
      aside?.removeAttribute("aria-hidden");
      main?.removeAttribute("inert");
      return;
    }
    if (mobileOpen) {
      openerRef.current = document.activeElement as HTMLElement | null;
      aside?.removeAttribute("inert");
      aside?.removeAttribute("aria-hidden");
      main?.setAttribute("inert", "");
      window.setTimeout(() => searchRef.current?.focus(), 0);
      return;
    }
    aside?.setAttribute("inert", "");
    aside?.setAttribute("aria-hidden", "true");
    main?.removeAttribute("inert");
    const opener = openerRef.current;
    openerRef.current = null;
    if (opener?.isConnected) opener.focus();
  }, [mobileOpen, isDesktop]);

  const trapFocus = (event: React.KeyboardEvent<HTMLElement>) => {
    if (!drawerOpen || event.key !== "Tab" || !asideRef.current) return;
    // Only controls that can actually take focus count: the desktop-only
    // Collapse button is display:none here, and using it as the wrap point let
    // Tab escape the drawer.
    // Safari < 17.4 lacks checkVisibility; a display:none element has no boxes.
    const all = Array.from(asideRef.current.querySelectorAll<HTMLElement>(FOCUSABLE));
    const shown = all.filter((el) =>
      typeof el.checkVisibility === "function" ? el.checkVisibility() : el.getClientRects().length > 0,
    );
    // No element reporting a box means no layout information at all: use every control.
    const items = shown.length ? shown : all;
    if (!items.length) return;
    const first = items[0];
    const last = items[items.length - 1];
    const active = document.activeElement;
    if (event.shiftKey && (active === first || !asideRef.current.contains(active))) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && (active === last || !asideRef.current.contains(active))) {
      event.preventDefault();
      first.focus();
    }
  };

  // Swipe-left to close on mobile
  useEffect(() => {
    if (!mobileOpen) return;
    let startX = 0;
    const onTouchStart = (e: TouchEvent) => { startX = e.touches[0].clientX; };
    const onTouchEnd = (e: TouchEvent) => {
      const dx = e.changedTouches[0].clientX - startX;
      if (dx < -50) setMobileOpen(false); // swipe left ≥50px closes
    };
    document.addEventListener("touchstart", onTouchStart, { passive: true });
    document.addEventListener("touchend", onTouchEnd, { passive: true });
    return () => {
      document.removeEventListener("touchstart", onTouchStart);
      document.removeEventListener("touchend", onTouchEnd);
    };
  }, [mobileOpen, setMobileOpen]);

  return (
    <>
      {/* Mobile backdrop */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm lg:hidden animate-fade-in"
          onClick={closeMobile}
          aria-hidden
        />
      )}
      <aside
        ref={asideRef}
        aria-label="Main navigation"
        onKeyDown={trapFocus}
        className={clsx(
          "flex flex-col shrink-0 transition-all duration-300 ease-in-out",
          // Mobile drawer mode
          "fixed inset-y-0 left-0 z-50 w-[264px] h-screen border-r border-line sanket-sidebar",
          mobileOpen ? "translate-x-0 shadow-lg" : "-translate-x-full",
          // Desktop floating panel mode
          "lg:relative lg:translate-x-0 lg:z-20 lg:w-[var(--sb-w)] lg:h-full",
          "lg:rounded-2xl lg:border lg:shadow-md"
        )}
        style={{ ["--sb-w" as string]: collapsed ? "72px" : "244px" }}
      >
      {/* Logo */}
      <div
        className={clsx(
          "flex items-center border-b border-line lg:border-white/10 py-5 transition-all duration-300",
          c ? "px-3 justify-center" : "px-5 gap-3",
        )}
      >
        <LogoMark
          size={36}
          variant="tile"
          className="shrink-0 rounded-xl shadow-md"
        />
        {!c && (
          <div className="animate-slide-in flex-1 leading-none">
            <div className="font-display font-bold text-content lg:text-[#BDD9D7] tracking-tight text-sm">SANKET</div>
            <div className="mt-1.5 text-[9px] uppercase tracking-widest text-content-subtle lg:text-[#BDD9D7]/50 font-semibold">
              Predictive OS
            </div>
          </div>
        )}
        {drawerOpen && (
          <button
            type="button"
            onClick={closeMobile}
            aria-label="Close navigation"
            className="ml-auto grid h-9 w-9 place-items-center rounded-lg text-content-muted hover:bg-surface-3 hover:text-content lg:hidden"
          >
            <X size={18} aria-hidden="true" />
          </button>
        )}
      </div>

      {!c && (
        <div className="px-4 pt-4">
          <label className="relative block">
            <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-content-subtle lg:text-[#BDD9D7]/55" aria-hidden="true" />
            {/* Semantic tokens on the light mobile drawer; the teal-on-dark
                treatment applies only to the desktop rail (deep audit F10). */}
            <input
              ref={searchRef}
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Find a page…"
              aria-label="Search navigation"
              className="h-9 w-full rounded-xl border border-line bg-surface-2 pl-9 pr-14 text-xs text-content outline-none placeholder:text-content-muted focus:border-[var(--accent)] focus:ring-2 focus:ring-[var(--accent-soft)] lg:border-white/10 lg:bg-white/[0.06] lg:text-white lg:placeholder:text-[#BDD9D7]/60 lg:focus:border-[#BDD9D7]/45 lg:focus:ring-[#BDD9D7]/10"
            />
            <span className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 rounded border border-line px-1.5 py-0.5 font-mono text-[9px] text-content-subtle lg:border-white/10 lg:text-[#BDD9D7]/60" aria-hidden="true">{isApplePlatform() ? "⌘K" : "Ctrl K"}</span>
          </label>
        </div>
      )}

      {/* Navigation */}
      <nav className="flex-1 px-4 py-4 space-y-1 overflow-y-auto overflow-x-hidden">
        {visibleSections.map((section) => section.entries.length > 0 && (
          <div key={section.label}>
            <SectionLabel collapsed={c}>{section.label}</SectionLabel>
            {section.entries.map((entry) => (
              <NavItem key={entry.to} entry={entry} collapsed={c} onNavigate={closeMobile} badge={badgeFor(entry.to)} />
            ))}
          </div>
        ))}
        {!c && search.trim() && visibleSections.every((section) => section.entries.length === 0) && (
          <p className="px-4 py-6 text-center text-xs text-content-subtle lg:text-[#BDD9D7]/60">No page matches “{search}”.</p>
        )}

        {isPharma && (
          <>
            <SectionLabel collapsed={c}>Compliance</SectionLabel>
            <NavItem
              entry={{ to: "/workspace/pharma/batches", label: "GxP Batches", icon: ShieldCheck }}
              collapsed={c}
              onNavigate={closeMobile}
            />
          </>
        )}
      </nav>

      {/* Footer */}
      <div className="p-4 border-t border-line lg:border-white/10 flex flex-col gap-1.5">
        <NavItem entry={{ to: "/workspace/settings", label: "Settings", icon: SettingsIcon }} collapsed={c} onNavigate={closeMobile} />

        <button
          onClick={toggle}
          className={clsx(
            "group relative hidden lg:flex items-center rounded-xl text-sm font-medium text-content-muted hover:text-content hover:bg-surface-3 lg:text-[#BDD9D7]/80 lg:hover:text-white lg:hover:bg-white/5 transition-all duration-150 tactile-press",
            c ? "justify-center h-10 w-10 mx-auto" : "gap-3 px-4 py-2.5 w-full",
          )}
          title={c ? "Expand sidebar (Ctrl + /)" : "Collapse sidebar (Ctrl + /)"}
          aria-label={c ? "Expand sidebar" : "Collapse sidebar"}
          aria-expanded={!c}
        >
          {c ? <ChevronRight size={18} className="shrink-0" aria-hidden="true" /> : <ChevronLeft size={18} className="shrink-0" aria-hidden="true" />}
          {!c && <span className="animate-slide-in">Collapse</span>}
        </button>

        {!c && <BuildStamp />}
      </div>
      </aside>
    </>
  );
};
