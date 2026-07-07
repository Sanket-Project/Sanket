import { useState, useEffect, useRef } from "react";
import {
  LogOut,
  User as UserIcon,
  Bell,
  Shield,
  Mail,
  Building,
  Briefcase,
  ExternalLink,
  AlertOctagon,
  AlertTriangle,
  Info,
  CheckCircle2,
  Sun,
  Moon,
  Menu,
} from "lucide-react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuthStore } from "@/stores/auth";
import { IndustrySwitcher } from "@/components/layout/IndustrySwitcher";
import { Button } from "@/components/ui/Button";
import { useIndustryContext } from "@/hooks/useIndustryContext";
import { Badge } from "@/components/ui/Badge";
import { useCurrencyStore } from "@/stores/currency";
import { shortageAlertsApi } from "@/api/shortageAlerts";
import { useIndustryStore } from "@/stores/industry";
import { useSidebarStore } from "@/stores/sidebar";
import { fmtRelative } from "@/utils/format";

export const TopBar = () => {
  const { logout, role, decodeToken } = useAuthStore();
  const { data: ctx } = useIndustryContext();
  const navigate = useNavigate();

  const handleSignOut = async () => {
    navigate("/", { replace: true });
    await logout();
  };
  const { currency, setCurrency } = useCurrencyStore();
  const activeIndustry = useIndustryStore((s) => s.activeIndustry);
  const toggleMobile = useSidebarStore((s) => s.toggleMobile);
  const mobileOpen = useSidebarStore((s) => s.mobileOpen);
  const location = useLocation();

  const [darkMode, setDarkMode] = useState(() => {
    const theme = localStorage.getItem("sanket.theme");
    return theme ? theme === "dark" : document.documentElement.classList.contains("dark");
  });

  useEffect(() => {
    if (darkMode) {
      document.documentElement.classList.add("dark");
      localStorage.setItem("sanket.theme", "dark");
    } else {
      document.documentElement.classList.remove("dark");
      localStorage.setItem("sanket.theme", "light");
    }
  }, [darkMode]);

  const [showNotifications, setShowNotifications] = useState(false);
  const [showProfile, setShowProfile] = useState(false);

  const notificationRef = useRef<HTMLDivElement>(null);
  const profileRef = useRef<HTMLDivElement>(null);

  const decoded = decodeToken();

  // Use a shared query key so if the ShortageAlerts page is also mounted,
  // React Query deduplicates the request and serves from the same cache entry.
  const { data: openAlerts } = useQuery({
    queryKey: ["alerts", activeIndustry, "open", "all"],
    queryFn: () => shortageAlertsApi.list({ status: "open", hours: 168, limit: 200 }),
    refetchInterval: 30_000,
    enabled: !!activeIndustry,
    select: (data) => data.slice(0, 5),
  });

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as HTMLElement;
      if (notificationRef.current && !notificationRef.current.contains(target)) setShowNotifications(false);
      if (profileRef.current && !profileRef.current.contains(target)) setShowProfile(false);
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const SEVERITY_ICONS = {
    critical: <AlertOctagon size={15} className="text-rose-500 shrink-0 mt-0.5" />,
    warning: <AlertTriangle size={15} className="text-amber-500 shrink-0 mt-0.5" />,
    info: <Info size={15} className="text-cyan-500 shrink-0 mt-0.5" />,
  };

  const getBreadcrumbs = (pathname: string) => {
    const parts = pathname.split("/").filter(Boolean);
    if (parts.length <= 1) return [{ label: "Dashboard", href: "/workspace" }];
    const list: { label: string; href?: string }[] = [];
    const sub = parts[1];
    if (sub === "products") {
      list.push({ label: "Core", href: "/workspace" }, { label: "Products", href: "/workspace/products" });
      if (parts[2]) list.push({ label: "Detail" });
    } else if (sub === "skus") {
      list.push({ label: "Core", href: "/workspace" }, { label: "SKUs", href: "/workspace/skus" });
      if (parts[2]) list.push({ label: "Detail" });
    } else if (sub === "inventory") {
      list.push({ label: "Core", href: "/workspace" }, { label: "Inventory" });
    } else if (sub === "signals") {
      list.push({ label: "Core", href: "/workspace" }, { label: "Signals" });
    } else if (sub === "trends") {
      list.push({ label: "Intelligence", href: "/workspace/trends" }, { label: "Market Trends" });
    } else if (sub === "forecasts") {
      list.push({ label: "Intelligence", href: "/workspace/forecasts" });
      list.push({ label: parts[2] === "hybrid" ? "Hybrid Forecasts" : "Forecasts" });
    } else if (sub === "alerts") {
      list.push({ label: "Intelligence", href: "/workspace/alerts" }, { label: "Shortage Alerts" });
    } else if (sub === "sales-analytics") {
      list.push({ label: "Analytics", href: "/workspace/sales-analytics" }, { label: "Sales Analytics" });
    } else if (sub === "financial") {
      list.push({ label: "Analytics", href: "/workspace/financial" }, { label: "Financial Impact" });
    } else if (sub === "forecast-accuracy") {
      list.push({ label: "Analytics", href: "/workspace/forecast-accuracy" }, { label: "Forecast Accuracy" });
    } else if (sub === "pharma") {
      list.push({ label: "Compliance", href: "/workspace/pharma/batches" }, { label: "GxP Batches" });
    } else if (sub === "live-sales") {
      list.push({ label: "Analytics", href: "/workspace/live-sales" }, { label: "Live Sales" });
    } else if (sub === "integrations") {
      list.push({ label: "Developer", href: "/workspace/integrations" }, { label: "Integrations" });
    } else if (sub === "webhooks") {
      list.push({ label: "Developer", href: "/workspace/webhooks" }, { label: "Webhooks" });
    } else if (sub === "profile") {
      list.push({ label: "Profile" });
    } else if (sub === "billing") {
      list.push({ label: "Billing" });
    } else if (sub === "settings") {
      list.push({ label: "Settings" });
    } else {
      list.push({ label: sub.charAt(0).toUpperCase() + sub.slice(1) });
    }
    return list;
  };

  const getInitials = (name: string) => {
    return name
      .split(" ")
      .map((n) => n[0])
      .join("")
      .substring(0, 2)
      .toUpperCase();
  };

  const userInitials = decoded?.name ? getInitials(decoded.name) : "JR";

  const iconBtn =
    "relative h-9 w-9 grid place-items-center rounded-xl border border-line bg-surface text-content-muted hover:text-content hover:bg-surface-2 hover:border-line-strong transition-all duration-200 shadow-sm active:scale-95 shrink-0";

  return (
    <header className="h-14 px-6 flex items-center justify-between relative z-30 shrink-0 transition-all duration-300 ease-in-out border-b border-line bg-surface lg:rounded-2xl lg:border lg:bg-surface/75 lg:backdrop-blur-md lg:shadow-sm lg:px-6">
      {/* Left: workspace selector + breadcrumbs */}
      <div className="flex items-center gap-4 min-w-0">
        <button
          onClick={toggleMobile}
          className="lg:hidden h-9 w-9 grid place-items-center rounded-xl border border-line bg-surface text-content-muted hover:text-content hover:bg-surface-2 transition-all duration-150 tactile-press shrink-0"
          aria-label={mobileOpen ? "Close navigation" : "Open navigation"}
          aria-expanded={mobileOpen}
          aria-haspopup="true"
        >
          <Menu size={18} aria-hidden="true" />
        </button>
        <IndustrySwitcher />
        <div className="h-6 w-px bg-line hidden md:block" />
        <div className="hidden md:flex items-center gap-1.5 text-[13px] font-medium select-none min-w-0">
          {getBreadcrumbs(location.pathname).map((bc, idx, arr) => (
            <div key={idx} className="flex items-center gap-1.5">
              {bc.href ? (
                <Link to={bc.href} className="text-content-subtle hover:text-content transition-colors">
                  {bc.label}
                </Link>
              ) : (
                <span className="font-heading font-semibold text-content">{bc.label}</span>
              )}
              {idx < arr.length - 1 && <span className="text-content-subtle">/</span>}
            </div>
          ))}
        </div>
        {ctx?.is_gxp && (
          <Badge variant="success" className="hidden lg:inline-flex">
            GxP · 21 CFR Part 11
          </Badge>
        )}
      </div>

      {/* Right: controls */}
      <div className="flex items-center gap-2.5">
        {/* Currency */}
        <button
          onClick={() => setCurrency(currency === "USD" ? "INR" : "USD")}
          className="h-9 px-3 flex items-center gap-1.5 rounded-xl border border-line bg-surface text-content-muted hover:text-content hover:bg-surface-2 transition-all duration-150 tactile-press shrink-0"
          title="Switch currency profile"
          aria-label={`Switch to ${currency === "USD" ? "INR" : "USD"} currency`}
        >
          <span className="font-mono text-xs font-semibold" style={{ color: "var(--accent)" }}>
            {currency === "USD" ? "$" : "₹"}
          </span>
          <span className="text-xs font-semibold tracking-wide">{currency}</span>
        </button>

        {/* Dark mode */}
        <button
          onClick={() => setDarkMode(!darkMode)}
          className={iconBtn}
          title={darkMode ? "Light mode" : "Dark mode"}
          aria-label={darkMode ? "Switch to light mode" : "Switch to dark mode"}
          aria-pressed={darkMode}
        >
          {darkMode ? <Sun size={16} className="text-amber-500" aria-hidden="true" /> : <Moon size={16} aria-hidden="true" />}
        </button>

        {/* Notifications */}
        <div className="relative" ref={notificationRef}>
          <button
            onClick={() => {
              setShowNotifications(!showNotifications);
              setShowProfile(false);
            }}
            className={`${iconBtn} hover-bell-shake ${showNotifications ? "!bg-surface-2 !text-content" : ""}`}
            title="Notifications"
            aria-label="Open notifications"
            aria-expanded={showNotifications}
            aria-haspopup="true"
          >
            <Bell size={16} aria-hidden="true" />
            {openAlerts && openAlerts.length > 0 && (
              <span className="absolute top-2 right-2 h-1.5 w-1.5 rounded-full bg-rose-500 ring-2 ring-[var(--surface)]" />
            )}
          </button>

          {showNotifications && (
            <div className="absolute right-0 mt-2 w-80 rounded-2xl border border-line bg-surface shadow-lg overflow-hidden animate-slide-up z-50">
              <div className="px-4 py-3 border-b border-line flex items-center justify-between">
                <span className="text-[11px] font-semibold uppercase tracking-wider text-content-subtle">
                  System Warnings
                </span>
                {openAlerts && openAlerts.length > 0 && <Badge variant="warning">{openAlerts.length} open</Badge>}
              </div>
              <div className="max-h-[300px] overflow-y-auto">
                {openAlerts && openAlerts.length > 0 ? (
                  <div className="divide-y divide-line">
                    {openAlerts.map((alert) => (
                      <Link
                        key={alert.id}
                        to="/workspace/alerts"
                        onClick={() => setShowNotifications(false)}
                        className="flex gap-3 p-4 hover:bg-surface-2 transition-colors text-left items-start group"
                      >
                        {SEVERITY_ICONS[alert.severity as keyof typeof SEVERITY_ICONS] || SEVERITY_ICONS.info}
                        <div className="flex-1 min-w-0">
                          <p className="text-[13px] font-semibold text-content leading-snug group-hover:text-[var(--accent)] transition-colors">
                            {alert.title}
                          </p>
                          <p className="text-xs text-content-muted mt-0.5 line-clamp-2 leading-normal">{alert.message}</p>
                          <p className="text-[11px] font-medium text-content-subtle mt-1.5">{fmtRelative(alert.fired_at)}</p>
                        </div>
                      </Link>
                    ))}
                  </div>
                ) : (
                  <div className="flex flex-col items-center justify-center py-10 px-4 text-center">
                    <CheckCircle2 size={24} className="text-emerald-500 mb-2" />
                    <p className="text-[13px] font-semibold text-content">All Systems Healthy</p>
                    <p className="text-xs text-content-subtle mt-1 max-w-[220px] leading-relaxed">
                      No active inventory shortages or trend volatility risks detected.
                    </p>
                  </div>
                )}
              </div>
              <Link
                to="/workspace/alerts"
                onClick={() => setShowNotifications(false)}
                className="block text-center py-3 text-[11px] font-semibold uppercase tracking-wider text-content-muted hover:text-[var(--accent)] bg-surface-2 border-t border-line transition-colors"
              >
                View all alerts
              </Link>
            </div>
          )}
        </div>

        <div className="w-px h-5 bg-line mx-0.5 shrink-0 hidden sm:block" />

        {/* Role */}
        <span
          className="hidden sm:inline-flex items-center px-2.5 py-1 rounded-lg text-[10px] font-bold uppercase tracking-widest border border-line bg-surface-2 text-content-muted"
        >
          {role}
        </span>

        {/* Profile */}
        <div className="relative" ref={profileRef}>
          <button
            onClick={() => {
              setShowProfile(!showProfile);
              setShowNotifications(false);
            }}
            className="h-9 w-9 rounded-full grid place-items-center text-white shadow-sm ring-2 ring-[var(--surface)] hover:ring-[var(--accent-ring)] transition-all duration-200 active:scale-95 shrink-0 font-semibold text-xs tracking-wider"
            style={{ background: "var(--accent)" }}
            aria-label="Open profile menu"
            aria-expanded={showProfile}
            aria-haspopup="true"
          >
            {userInitials}
          </button>

          {showProfile && (
            <div className="absolute right-0 mt-2 w-72 rounded-2xl border border-line bg-surface shadow-lg overflow-hidden animate-slide-up z-50">
              <div className="p-4 flex flex-col items-center text-center border-b border-line">
                <div className="h-12 w-12 rounded-full grid place-items-center text-white shadow-sm mb-2" style={{ background: "var(--accent)" }}>
                  <UserIcon size={20} />
                </div>
                <h4 className="font-heading font-semibold text-sm text-content leading-tight">
                  {decoded?.name || "Platform Owner"}
                </h4>
                <p className="text-xs text-content-subtle mt-1 break-all flex items-center gap-1 justify-center">
                  <Mail size={11} className="shrink-0" />
                  <span>{decoded?.email || "—"}</span>
                </p>
              </div>

              <div className="p-2 space-y-1.5">
                {[
                  { icon: Shield, label: "Security Role", value: (decoded?.role || role || "owner").toString().toUpperCase() },
                  { icon: Building, label: "Organization ID", value: decoded?.tid || "—", mono: true },
                  { icon: Briefcase, label: "Workspace Sector", value: ctx?.display_name || activeIndustry || "fashion" },
                ].map(({ icon: Icon, label, value, mono }) => (
                  <div key={label} className="flex items-center gap-2.5 px-2.5 py-2 rounded-xl border border-line bg-surface-2">
                    <Icon size={13} className="shrink-0" style={{ color: "var(--accent)" }} />
                    <div className="min-w-0">
                      <p className="text-[11px] uppercase font-semibold text-content-subtle leading-none">{label}</p>
                      <p className={`text-xs font-semibold text-content mt-1 truncate ${mono ? "font-mono" : ""}`} title={value}>
                        {value}
                      </p>
                    </div>
                  </div>
                ))}
              </div>

              <div className="px-2 pb-2 border-t border-line pt-2">
                {[
                  { to: "/workspace/billing", label: "Subscription Plan" },
                  { to: "/workspace/settings", label: "Platform Settings" },
                ].map(({ to, label }) => (
                  <Link
                    key={to}
                    to={to}
                    onClick={() => setShowProfile(false)}
                    className="flex items-center justify-between p-2.5 rounded-xl text-xs font-semibold text-content-muted hover:text-[var(--accent)] hover:bg-surface-2 transition-colors"
                  >
                    <span>{label}</span>
                    <ExternalLink size={12} className="text-content-subtle" />
                  </Link>
                ))}
              </div>

              <button
                onClick={() => {
                  setShowProfile(false);
                  handleSignOut();
                }}
                className="w-full py-3 text-xs font-semibold uppercase tracking-wider text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-500/10 border-t border-line transition-colors flex items-center justify-center gap-1.5 cursor-pointer"
              >
                <LogOut size={13} />
                <span>Sign out</span>
              </button>
            </div>
          )}
        </div>

        <Button
          variant="ghost"
          size="sm"
          icon={<LogOut size={13} />}
          onClick={() => handleSignOut()}
          className="hidden sm:inline-flex"
        >
          Sign out
        </Button>
      </div>
    </header>
  );
};
