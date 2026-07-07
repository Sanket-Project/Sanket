import { useState, type FormEvent } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  User,
  Building2,
  Globe,
  Bell,
  Save,
  Lock,
  Mail,
  ShieldCheck,
  Check,
} from "lucide-react";
import toast from "react-hot-toast";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useAuthStore } from "@/stores/auth";
import { useIndustryContext } from "@/hooks/useIndustryContext";
import { industryApi } from "@/api/industry";
import { industryDisplay } from "@/utils/colors";
import { FocusProfileCard } from "@/components/settings/FocusProfileCard";

// ── Types ────────────────────────────────────────────────────────────────────

type Tab = "profile" | "workspace" | "industry" | "notifications";

const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: "profile", label: "Profile", icon: <User size={15} /> },
  { id: "workspace", label: "Workspace", icon: <Building2 size={15} /> },
  { id: "industry", label: "Industry", icon: <Globe size={15} /> },
  { id: "notifications", label: "Notifications", icon: <Bell size={15} /> },
];

// ── Notification preferences (client-side toggle; no backend required yet) ──
type NotifPrefs = {
  forecast_ready: boolean;
  shortage_alert: boolean;
  batch_expiry: boolean;
  weekly_digest: boolean;
};

const DEFAULT_PREFS: NotifPrefs = {
  forecast_ready: true,
  shortage_alert: true,
  batch_expiry: true,
  weekly_digest: false,
};

function loadPrefs(): NotifPrefs {
  try {
    const raw = localStorage.getItem("sanket.notif.prefs");
    if (raw) return { ...DEFAULT_PREFS, ...(JSON.parse(raw) as Partial<NotifPrefs>) };
  } catch {
    /* ignore */
  }
  return { ...DEFAULT_PREFS };
}

function savePrefs(prefs: NotifPrefs) {
  try {
    localStorage.setItem("sanket.notif.prefs", JSON.stringify(prefs));
  } catch {
    /* ignore */
  }
}

// ── Row helper ───────────────────────────────────────────────────────────────

const Row = ({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) => (
  <div className="space-y-1">
    <dt className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{label}</dt>
    <dd className="text-slate-700 dark:text-slate-200 font-medium">{value}</dd>
    {hint && <p className="text-[11px] text-slate-400">{hint}</p>}
  </div>
);

// ── Toggle helper ────────────────────────────────────────────────────────────

const Toggle = ({
  id,
  label,
  description,
  checked,
  onChange,
}: {
  id: string;
  label: string;
  description: string;
  checked: boolean;
  onChange: (v: boolean) => void;
}) => (
  <div className="flex items-center justify-between gap-4 py-3 border-b border-line last:border-0">
    <div>
      <label htmlFor={id} className="text-sm font-semibold text-content cursor-pointer">
        {label}
      </label>
      <p className="text-xs text-content-subtle mt-0.5">{description}</p>
    </div>
    <button
      id={id}
      role="switch"
      type="button"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-violet-500 focus-visible:ring-offset-2 ${
        checked ? "bg-violet-600" : "bg-slate-200 dark:bg-slate-700"
      }`}
    >
      <span className="sr-only">{checked ? "On" : "Off"}</span>
      <span
        aria-hidden="true"
        className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition-transform duration-200 ${
          checked ? "translate-x-5" : "translate-x-0"
        }`}
      />
    </button>
  </div>
);

// ── Profile Tab ──────────────────────────────────────────────────────────────

const ProfileTab = () => {
  const { userId, tenantId, role, email, fullName } = useAuthStore();
  const [displayName, setDisplayName] = useState(fullName ?? "");
  const [saving, setSaving] = useState(false);

  const handleSaveName = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      // Update Firebase display name if available
      const { firebaseAuth, firebaseEnabled } = await import("@/lib/firebase");
      if (firebaseEnabled && firebaseAuth?.currentUser) {
        const { updateProfile } = await import("firebase/auth");
        await updateProfile(firebaseAuth.currentUser, { displayName });
        toast.success("Display name updated");
      } else {
        // Dev mode — optimistic update only
        toast.success("Display name saved");
      }
    } catch (err) {
      toast.error((err as { message?: string })?.message ?? "Failed to update name");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Avatar + name */}
      <Card title="Display Name">
        <form onSubmit={handleSaveName} className="space-y-4" aria-label="Update display name">
          <div className="flex items-center gap-4 mb-4">
            {/* Avatar initials */}
            <div
              className="h-16 w-16 rounded-2xl bg-gradient-accent flex items-center justify-center shadow-lg shrink-0"
              aria-hidden="true"
            >
              <span className="text-2xl font-bold text-white">
                {(displayName || email || "?")[0].toUpperCase()}
              </span>
            </div>
            <div>
              <p className="font-semibold text-slate-800 dark:text-white text-sm">{email ?? "—"}</p>
              <Badge variant="primary" className="mt-1 text-[10px] uppercase tracking-wider font-bold">
                {role ?? "user"}
              </Badge>
            </div>
          </div>

          <Input
            id="display-name"
            label="Display name"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            icon={<User size={14} className="text-slate-400" aria-hidden="true" />}
            placeholder="Your full name"
            aria-required="false"
          />

          <div className="flex justify-end">
            <Button type="submit" loading={saving} icon={<Save size={14} />} size="sm">
              Save name
            </Button>
          </div>
        </form>
      </Card>

      {/* Account details */}
      <Card title="Account Details">
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-6">
          <Row
            label="Email address"
            value={
              <span className="flex items-center gap-1.5">
                <Mail size={13} className="text-slate-400 shrink-0" aria-hidden="true" />
                {email ?? "—"}
              </span>
            }
            hint="Managed by your identity provider."
          />
          <Row
            label="User ID"
            value={
              <code className="font-mono text-xs text-slate-600 dark:text-slate-300 bg-slate-50 dark:bg-slate-800 px-1.5 py-0.5 rounded border border-slate-200/60 dark:border-slate-700">
                {userId ?? "—"}
              </code>
            }
          />
          <Row
            label="Tenant ID"
            value={
              <code className="font-mono text-xs text-slate-600 dark:text-slate-300 bg-slate-50 dark:bg-slate-800 px-1.5 py-0.5 rounded border border-slate-200/60 dark:border-slate-700">
                {tenantId ?? "—"}
              </code>
            }
          />
          <Row
            label="Role"
            value={
              <span className="flex items-center gap-1.5">
                <ShieldCheck size={13} className="text-violet-500 shrink-0" aria-hidden="true" />
                <Badge variant="primary" className="text-[10px] uppercase tracking-wider font-bold">
                  {role ?? "—"}
                </Badge>
              </span>
            }
          />
        </dl>
      </Card>

      {/* Password */}
      <Card title="Password & Security">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div>
            <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">
              Password reset
            </p>
            <p className="text-xs text-slate-400 mt-0.5">
              We'll send a secure reset link to your email address.
            </p>
          </div>
          <Link to="/forgot-password">
            <Button variant="secondary" icon={<Lock size={14} />} size="sm">
              Send reset link
            </Button>
          </Link>
        </div>
      </Card>
    </div>
  );
};

// ── Workspace Tab ────────────────────────────────────────────────────────────

const WorkspaceTab = () => {
  const { tenantId, role, defaultIndustry } = useAuthStore();

  return (
    <div className="space-y-6">
      <Card title="Workspace Details">
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-6">
          <Row
            label="Tenant ID"
            value={
              <code className="font-mono text-xs text-slate-600 dark:text-slate-300 bg-slate-50 dark:bg-slate-800 px-1.5 py-0.5 rounded border border-slate-200/60 dark:border-slate-700">
                {tenantId ?? "—"}
              </code>
            }
            hint="Unique workspace identifier. Immutable."
          />
          <Row
            label="Account role"
            value={
              <Badge variant="primary" className="text-[10px] uppercase tracking-wider font-bold">
                {role ?? "—"}
              </Badge>
            }
          />
          <Row
            label="Default industry"
            value={
              defaultIndustry ? (
                <span className="font-bold capitalize text-slate-700 dark:text-slate-200">
                  {industryDisplay[defaultIndustry] ?? defaultIndustry}
                </span>
              ) : (
                "—"
              )
            }
            hint="Set by workspace configuration."
          />
        </dl>
      </Card>

      <Card title="Subscription">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <p className="text-sm text-slate-500 dark:text-slate-400">
            Manage your plan, billing email, and payment method.
          </p>
          <Link to="/workspace/billing">
            <Button variant="secondary" size="sm">
              Go to Billing
            </Button>
          </Link>
        </div>
      </Card>
    </div>
  );
};

// ── Industry Tab ─────────────────────────────────────────────────────────────

const IndustryTab = () => {
  const { data: ctx } = useIndustryContext();
  const { data: available } = useQuery({
    queryKey: ["industries-available"],
    queryFn: industryApi.available,
  });

  return (
    <div className="space-y-6">
      <FocusProfileCard />

      {ctx && (
        <Card
          title="Active Industry Context"
          description="Resolved from your session and X-Industry-Code header"
        >
          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-6">
            <Row label="Code" value={<code className="font-mono text-xs">{ctx.code}</code>} />
            <Row
              label="Display Name"
              value={<span className="font-semibold">{ctx.display_name}</span>}
            />
            <Row label="Forecast Horizon" value={`${ctx.default_horizon_weeks} weeks`} />
            <Row
              label="Audit Level"
              value={
                <Badge variant={ctx.is_gxp ? "success" : "default"}>{ctx.audit_level}</Badge>
              }
            />
            <div className="sm:col-span-2">
              <Row
                label="Forecast Models"
                value={
                  <div className="flex flex-wrap gap-1.5 mt-1">
                    {ctx.forecast_models.map((m) => (
                      <Badge key={m} variant="info">
                        {m}
                      </Badge>
                    ))}
                  </div>
                }
              />
            </div>
            <div className="sm:col-span-2">
              <Row
                label="Optimization Models"
                value={
                  <div className="flex flex-wrap gap-1.5 mt-1">
                    {ctx.optimization_models.map((m) => (
                      <Badge key={m}>{m}</Badge>
                    ))}
                  </div>
                }
              />
            </div>
          </dl>
        </Card>
      )}

      {available && (
        <Card title="Available Industries" description="All industries enabled for this workspace">
          <ul className="space-y-2" role="list">
            {Object.entries(available).map(([code, info]) => (
              <li
                key={code}
                className="flex items-center justify-between p-3.5 rounded-xl bg-white/70 dark:bg-surface-2 border border-slate-200/60 dark:border-line shadow-sm transition-all duration-200 hover:-translate-y-px hover:shadow-md"
              >
                <div>
                  <div className="text-slate-800 dark:text-white font-bold text-sm leading-tight">
                    {info.display_name}
                  </div>
                  <div className="text-xs text-slate-400 mt-0.5 font-medium">
                    {info.default_horizon_weeks}w horizon ·{" "}
                    <span className={info.audit_level === "gxp" ? "text-emerald-600 font-semibold" : ""}>
                      {info.audit_level}
                    </span>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {ctx?.code === code && (
                    <span
                      className="h-5 w-5 rounded-full bg-emerald-100 dark:bg-emerald-900/40 text-emerald-600 dark:text-emerald-400 flex items-center justify-center"
                      aria-label="Active"
                      title="Currently active"
                    >
                      <Check size={11} aria-hidden="true" />
                    </span>
                  )}
                  <code className="font-mono text-xs text-slate-500 bg-slate-50 dark:bg-slate-800 px-1.5 py-0.5 rounded border border-slate-200/60 dark:border-slate-700">
                    {code}
                  </code>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
};

// ── Notifications Tab ────────────────────────────────────────────────────────

const NotificationsTab = () => {
  const [prefs, setPrefs] = useState<NotifPrefs>(loadPrefs);
  const [saved, setSaved] = useState(false);

  const toggle = (key: keyof NotifPrefs) => (val: boolean) => {
    const next = { ...prefs, [key]: val };
    setPrefs(next);
    savePrefs(next);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="space-y-6">
      <Card title="Email Notifications">
        <div role="group" aria-label="Email notification preferences">
          <Toggle
            id="notif-forecast"
            label="Forecast ready"
            description="Get notified when a new forecast run completes."
            checked={prefs.forecast_ready}
            onChange={toggle("forecast_ready")}
          />
          <Toggle
            id="notif-shortage"
            label="Shortage alerts"
            description="Immediate alert when a shortage risk is detected."
            checked={prefs.shortage_alert}
            onChange={toggle("shortage_alert")}
          />
          <Toggle
            id="notif-expiry"
            label="Batch expiry warnings"
            description="Reminder when batches are within 30 days of expiry."
            checked={prefs.batch_expiry}
            onChange={toggle("batch_expiry")}
          />
          <Toggle
            id="notif-digest"
            label="Weekly digest"
            description="A summary of forecast accuracy and supply signals every Monday."
            checked={prefs.weekly_digest}
            onChange={toggle("weekly_digest")}
          />
        </div>
        {saved && (
          <p
            className="text-xs text-emerald-600 dark:text-emerald-400 font-semibold mt-3 flex items-center gap-1"
            role="status"
            aria-live="polite"
          >
            <Check size={12} aria-hidden="true" /> Preferences saved
          </p>
        )}
      </Card>

      <Card title="In-App Alerts" description="Configure which alerts appear in the notification panel.">
        <p className="text-sm text-slate-400">
          Coming soon — full alert routing configuration will be available in a future update.
        </p>
      </Card>
    </div>
  );
};

// ── Main Settings Page ───────────────────────────────────────────────────────

export const SettingsPage = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const activeTab = (searchParams.get("tab") as Tab | null) ?? "profile";

  const setTab = (tab: Tab) => {
    setSearchParams({ tab }, { replace: true });
  };

  return (
    <div className="space-y-6 max-w-3xl">
      <div className="animate-fade-in stagger-1">
        <h1 className="text-3xl font-bold tracking-tight text-slate-800 dark:text-white">
          Settings
        </h1>
        <p className="text-slate-500 dark:text-slate-400 mt-1">
          Manage your profile, workspace, and notification preferences.
        </p>
      </div>

      {/* Tab bar */}
      <nav
        className="flex gap-1 p-1 bg-slate-100/80 dark:bg-surface-2 rounded-2xl w-full animate-fade-in stagger-2"
        role="tablist"
        aria-label="Settings sections"
      >
        {TABS.map((tab) => (
          <button
            key={tab.id}
            role="tab"
            aria-selected={activeTab === tab.id}
            aria-controls={`settings-panel-${tab.id}`}
            id={`settings-tab-${tab.id}`}
            type="button"
            onClick={() => setTab(tab.id)}
            className={`flex-1 flex items-center justify-center gap-1.5 px-2 py-2 rounded-xl text-xs font-semibold transition-all duration-200 whitespace-nowrap ${
              activeTab === tab.id
                ? "bg-white dark:bg-surface shadow-sm text-slate-800 dark:text-white"
                : "text-slate-500 dark:text-slate-400 hover:text-slate-700 dark:hover:text-slate-200"
            }`}
          >
            <span aria-hidden="true">{tab.icon}</span>
            <span className="hidden sm:inline">{tab.label}</span>
          </button>
        ))}
      </nav>

      {/* Tab panels */}
      <div
        id={`settings-panel-${activeTab}`}
        role="tabpanel"
        aria-labelledby={`settings-tab-${activeTab}`}
        className="animate-fade-in"
      >
        {activeTab === "profile" && <ProfileTab />}
        {activeTab === "workspace" && <WorkspaceTab />}
        {activeTab === "industry" && <IndustryTab />}
        {activeTab === "notifications" && <NotificationsTab />}
      </div>
    </div>
  );
};
