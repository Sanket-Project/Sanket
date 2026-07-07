import { useEffect } from "react";
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
  Activity,
  Sparkles,
  AlertOctagon,
  Warehouse,
  Plug,
  ShoppingCart,
  DollarSign,
  BarChart3,
  ChevronLeft,
  ChevronRight,
  type LucideIcon,
} from "lucide-react";
import { useIndustryStore } from "@/stores/industry";
import { useSidebarStore } from "@/stores/sidebar";

interface NavEntry {
  to: string;
  label: string;
  icon: LucideIcon;
  exact?: boolean;
}

const NAV_MAIN: NavEntry[] = [
  { to: "/workspace", label: "Dashboard", icon: LayoutDashboard, exact: true },
  { to: "/workspace/products", label: "Products", icon: Package },
  { to: "/workspace/skus", label: "SKUs", icon: Boxes },
  { to: "/workspace/inventory", label: "Inventory", icon: Warehouse },
  { to: "/workspace/signals", label: "Signals", icon: Radio },
];

const NAV_INTELLIGENCE: NavEntry[] = [
  { to: "/workspace/trends", label: "Market Trends", icon: Activity },
  { to: "/workspace/forecasts", label: "Forecasts", icon: LineChart, exact: true },
  { to: "/workspace/forecasts/hybrid", label: "Hybrid Forecasts", icon: Sparkles },
  { to: "/workspace/alerts", label: "Shortage Alerts", icon: AlertOctagon },
];

const NAV_ANALYTICS: NavEntry[] = [
  { to: "/workspace/live-sales", label: "Live Sales", icon: ShoppingCart },
  { to: "/workspace/sales-analytics", label: "Sales Analytics", icon: Activity },
  { to: "/workspace/financial", label: "Financial Impact", icon: DollarSign },
  { to: "/workspace/forecast-accuracy", label: "Forecast Accuracy", icon: BarChart3 },
];

function NavItem({
  entry,
  collapsed,
  onNavigate,
}: {
  entry: NavEntry;
  collapsed: boolean;
  onNavigate?: () => void;
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
          {!collapsed && <span className="truncate">{label}</span>}
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
  const industry = useIndustryStore((s) => s.activeIndustry);
  const { collapsed, toggle, mobileOpen, setMobileOpen } = useSidebarStore();
  const isPharma = industry === "pharma";
  const closeMobile = () => setMobileOpen(false);
  // Rail collapse is a desktop concept; the mobile drawer always shows full nav.
  const c = collapsed && !mobileOpen;

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "/") {
        e.preventDefault();
        toggle();
      }
      if (e.key === "Escape") setMobileOpen(false);
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [toggle, setMobileOpen]);

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
        aria-label="Main navigation"
        className={clsx(
          "flex flex-col shrink-0 transition-all duration-300 ease-in-out",
          // Mobile drawer mode
          "fixed inset-y-0 left-0 z-50 w-[264px] h-screen border-r border-line sanket-sidebar",
          mobileOpen ? "translate-x-0 shadow-lg" : "-translate-x-full",
          // Desktop floating panel mode
          "lg:relative lg:translate-x-0 lg:z-20 lg:w-[var(--sb-w)] lg:h-full",
          "lg:rounded-[28px] lg:backdrop-blur-xl lg:border",
          "lg:shadow-[inset_0_1px_1px_rgba(255,255,255,0.12),0_12px_36px_rgba(3,54,61,0.25)]"
        )}
        style={{ ["--sb-w" as string]: collapsed ? "76px" : "260px" }}
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
          <div className="animate-slide-in leading-none">
            <div className="font-display font-bold text-content lg:text-[#BDD9D7] tracking-tight text-sm">SANKET</div>
            <div className="mt-1.5 text-[9px] uppercase tracking-widest text-content-subtle lg:text-[#BDD9D7]/50 font-semibold">
              Predictive OS
            </div>
          </div>
        )}
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-4 py-4 space-y-1 overflow-y-auto overflow-x-hidden">
        <SectionLabel collapsed={c}>Core</SectionLabel>
        {NAV_MAIN.map((e) => (
          <NavItem key={e.to} entry={e} collapsed={c} onNavigate={closeMobile} />
        ))}

        <SectionLabel collapsed={c}>Intelligence</SectionLabel>
        {NAV_INTELLIGENCE.map((e) => (
          <NavItem key={e.to} entry={e} collapsed={c} onNavigate={closeMobile} />
        ))}

        <SectionLabel collapsed={c}>Analytics</SectionLabel>
        {NAV_ANALYTICS.map((e) => (
          <NavItem key={e.to} entry={e} collapsed={c} onNavigate={closeMobile} />
        ))}

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
        <NavItem entry={{ to: "/workspace/integrations", label: "Integrations", icon: Plug }} collapsed={c} onNavigate={closeMobile} />
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
      </div>
      </aside>
    </>
  );
};
