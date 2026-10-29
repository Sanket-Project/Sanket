import { PageHeader } from "@/components/ui/PageHeader";
import { useState, type FormEvent } from "react";
import { useSearchParams, Link } from "react-router-dom";
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
} from "@/components/ui/icons";
import toast from "react-hot-toast";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useAuthStore } from "@/stores/auth";
import { useIndustryContext } from "@/hooks/useIndustryContext";
import { industryDisplay } from "@/utils/colors";
import { FocusProfileCard } from "@/components/settings/FocusProfileCard";
import { NetworkCard } from "@/components/settings/NetworkCard";
import { AISettings } from "@/components/ai/AISettings";
import { CommunicationPreferences } from "@/components/ai/CommunicationPreferences";

// ── Types ────────────────────────────────────────────────────────────────────

type Tab = "profile" | "workspace" | "industry" | "network" | "notifications";

const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: "profile", label: "Profile", icon: <User size={15} /> },
  { id: "workspace", label: "Workspace", icon: <Building2 size={15} /> },
  { id: "industry", label: "Industry", icon: <Globe size={15} /> },
  { id: "network", label: "Network", icon: <Building2 size={15} /> },
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
    <dt className="text-[10px] font-bold uppercase tracking-wider text-content-subtle">{label}</dt>
    <dd className="text-content dark:text-content font-medium">{value}</dd>
    {hint && <p className="text-[11px] text-content-subtle">{hint}</p>}
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
      className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 ${
        checked ? "bg-accent" : "bg-surface-3 dark:bg-surface-2"
      }`}
    >
      <span className="sr-only">{checked ? "On" : "Off"}</span>
      <span
        aria-hidden="true"
        className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-surface shadow-lg ring-0 transition-transform duration-200 ${
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
              <span className="text-2xl font-bold text-accent-fg">
                {(displayName || email || "?")[0].toUpperCase()}
              </span>
            </div>
            <div>
              <p className="font-semibold text-content dark:text-content text-sm">{email ?? "—"}</p>
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
            icon={<User size={14} className="text-content-subtle" aria-hidden="true" />}
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
                <Mail size={13} className="text-content-subtle shrink-0" aria-hidden="true" />
                {email ?? "—"}
              </span>
            }
            hint="Managed by your identity provider."
          />
          <Row
            label="User ID"
            value={
              <code className="font-mono text-xs text-content-muted dark:text-content-subtle bg-surface dark:bg-surface-2 px-1.5 py-0.5 rounded border border-line/60 dark:border-line">
                {userId ?? "—"}
              </code>
            }
          />
          <Row
            label="Tenant ID"
            value={
              <code className="font-mono text-xs text-content-muted dark:text-content-subtle bg-surface dark:bg-surface-2 px-1.5 py-0.5 rounded border border-line/60 dark:border-line">
                {tenantId ?? "—"}
              </code>
            }
          />
          <Row
            label="Role"
            value={
              <span className="flex items-center gap-1.5">
                <ShieldCheck size={13} className="text-accent shrink-0" aria-hidden="true" />
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
            <p className="text-sm font-semibold text-content dark:text-content">
              Password reset
            </p>
            <p className="text-xs text-content-subtle mt-0.5">
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
  const { tenantId, role, industry } = useAuthStore();

  return (
    <div className="space-y-6">
      <Card title="Workspace Details">
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-6">
          <Row
            label="Tenant ID"
            value={
              <code className="font-mono text-xs text-content-muted dark:text-content-subtle bg-surface dark:bg-surface-2 px-1.5 py-0.5 rounded border border-line/60 dark:border-line">
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
              industry ? (
                <span className="font-bold capitalize text-content dark:text-content">
                  {industryDisplay[industry] ?? industry}
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
          <p className="text-sm text-content-muted dark:text-content-subtle">
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

  // No "Available Industries" list here any more. It showed all five, labelled
  // "enabled for this workspace", which was both untrue and the wrong thing to
  // show: a workspace has exactly one industry and cannot move to another.
  return (
    <div className="space-y-6">
      <FocusProfileCard />

      {ctx && (
        <Card
          title="Workspace Industry"
          description="Set when this workspace was created; every member shares it"
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
                label="Forecasting approaches in the catalogue"
                value={
                  <div className="flex flex-wrap gap-1.5 mt-1">
                    <p className="w-full text-xs text-content-muted">
                      Not a list of what is running: forecasts come from Chronos zero-shot until a
                      model is trained on this workspace&apos;s data. Each forecast states the model used.
                    </p>
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
                label="Optimisation approaches in the catalogue"
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
        <p className="text-sm text-content-subtle">
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
        <PageHeader title="Settings" description={<> Manage your profile, workspace, and notification preferences. </>} />
      </div>

      {/* Tab bar */}
      <nav
        className="flex gap-1 overflow-x-auto p-1 bg-surface-2 rounded-2xl w-full animate-fade-in stagger-2"
        role="tablist"
        aria-label="Settings sections"
      >
        {TABS.map((tab) => (
          <button
            key={tab.id}
            role="tab"
            tabIndex={activeTab === tab.id ? 0 : -1}
            aria-selected={activeTab === tab.id}
            aria-controls={`settings-panel-${tab.id}`}
            id={`settings-tab-${tab.id}`}
            type="button"
            onClick={() => setTab(tab.id)}
            onKeyDown={(event) => {
              const index = TABS.findIndex(item => item.id === tab.id);
              const next = event.key === "Home" ? 0 : event.key === "End" ? TABS.length - 1 : event.key === "ArrowRight" ? (index + 1) % TABS.length : event.key === "ArrowLeft" ? (index - 1 + TABS.length) % TABS.length : -1;
              if (next < 0) return;
              event.preventDefault();
              setTab(TABS[next].id);
              document.getElementById(`settings-tab-${TABS[next].id}`)?.focus();
            }}
            className={`min-w-24 shrink-0 sm:flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-xl text-xs font-medium transition-colors duration-150 whitespace-nowrap ${
              activeTab === tab.id
                ? "bg-surface dark:bg-surface shadow-sm text-content dark:text-content"
                : "text-content-muted dark:text-content-subtle hover:text-content dark:hover:text-content"
            }`}
          >
            <span aria-hidden="true">{tab.icon}</span>
            <span>{tab.label}</span>
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
        {activeTab === "workspace" && <div className="space-y-4"><WorkspaceTab /><AISettings /></div>}
        {activeTab === "industry" && <IndustryTab />}
        {activeTab === "network" && <NetworkCard />}
        {activeTab === "notifications" && <div className="space-y-6"><CommunicationPreferences /><NotificationsTab /></div>}
      </div>
    </div>
  );
};
