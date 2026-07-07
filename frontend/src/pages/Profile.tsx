import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import {
  User,
  Mail,
  ShieldCheck,
  Save,
  Lock,
  Building2,
  ArrowRight,
} from "lucide-react";
import toast from "react-hot-toast";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { useAuthStore } from "@/stores/auth";
import { industryDisplay } from "@/utils/colors";

export const ProfilePage = () => {
  const { userId, tenantId, role, email, fullName, defaultIndustry } = useAuthStore();
  const [displayName, setDisplayName] = useState(fullName ?? "");
  const [saving, setSaving] = useState(false);

  const handleSaveName = async (e: FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      const { firebaseAuth, firebaseEnabled } = await import("@/lib/firebase");
      if (firebaseEnabled && firebaseAuth?.currentUser) {
        const { updateProfile } = await import("firebase/auth");
        await updateProfile(firebaseAuth.currentUser, { displayName });
        toast.success("Display name updated");
      } else {
        toast.success("Display name saved");
      }
    } catch (err) {
      toast.error((err as { message?: string })?.message ?? "Failed to update name");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6 max-w-2xl">
      <div className="animate-fade-in stagger-1">
        <h1 className="text-3xl font-bold tracking-tight text-slate-800 dark:text-white">
          Your Profile
        </h1>
        <p className="text-slate-500 dark:text-slate-400 mt-1">
          Manage your personal details and account security.
        </p>
      </div>

      {/* Avatar + name edit */}
      <Card className="animate-fade-in stagger-2">
        <form onSubmit={handleSaveName} className="space-y-5" aria-label="Edit profile">
          <div className="flex items-center gap-5">
            {/* Initials avatar */}
            <div
              className="h-20 w-20 rounded-3xl bg-gradient-accent flex items-center justify-center shadow-xl shrink-0"
              aria-hidden="true"
            >
              <span className="text-3xl font-bold text-white select-none">
                {(displayName || email || "?")[0].toUpperCase()}
              </span>
            </div>
            <div className="space-y-1 min-w-0">
              <p className="font-bold text-slate-800 dark:text-white text-lg leading-tight truncate">
                {displayName || email || "—"}
              </p>
              <div className="flex flex-wrap items-center gap-2">
                <Badge variant="primary" className="text-[10px] uppercase tracking-wider font-bold">
                  {role ?? "user"}
                </Badge>
                {defaultIndustry && (
                  <Badge variant="info" className="text-[10px] font-medium capitalize">
                    {industryDisplay[defaultIndustry] ?? defaultIndustry}
                  </Badge>
                )}
              </div>
            </div>
          </div>

          <Input
            id="profile-display-name"
            label="Display name"
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            icon={<User size={14} className="text-slate-400" aria-hidden="true" />}
            placeholder="Your full name"
          />

          <div className="flex justify-end">
            <Button type="submit" loading={saving} icon={<Save size={14} />} size="sm">
              Save changes
            </Button>
          </div>
        </form>
      </Card>

      {/* Account details */}
      <Card title="Account Details" className="animate-fade-in stagger-3">
        <dl className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          <div className="space-y-1">
            <dt className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
              Email address
            </dt>
            <dd className="flex items-center gap-1.5 text-sm font-medium text-slate-700 dark:text-slate-200">
              <Mail size={13} className="text-slate-400 shrink-0" aria-hidden="true" />
              {email ?? "—"}
            </dd>
            <p className="text-[11px] text-slate-400">Managed by your identity provider.</p>
          </div>

          <div className="space-y-1">
            <dt className="text-[10px] font-bold uppercase tracking-wider text-slate-400">Role</dt>
            <dd className="flex items-center gap-1.5">
              <ShieldCheck size={13} className="text-violet-500 shrink-0" aria-hidden="true" />
              <Badge variant="primary" className="text-[10px] uppercase tracking-wider font-bold">
                {role ?? "—"}
              </Badge>
            </dd>
          </div>

          <div className="space-y-1">
            <dt className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
              User ID
            </dt>
            <dd>
              <code className="font-mono text-xs text-slate-600 dark:text-slate-300 bg-slate-50 dark:bg-slate-800 px-1.5 py-0.5 rounded border border-slate-200/60 dark:border-slate-700">
                {userId ?? "—"}
              </code>
            </dd>
          </div>

          <div className="space-y-1">
            <dt className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
              Tenant ID
            </dt>
            <dd>
              <code className="font-mono text-xs text-slate-600 dark:text-slate-300 bg-slate-50 dark:bg-slate-800 px-1.5 py-0.5 rounded border border-slate-200/60 dark:border-slate-700">
                {tenantId ?? "—"}
              </code>
            </dd>
          </div>
        </dl>
      </Card>

      {/* Security */}
      <Card title="Password & Security" className="animate-fade-in stagger-4">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div>
            <p className="text-sm font-semibold text-slate-700 dark:text-slate-200">
              Change your password
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

      {/* Quick links */}
      <Card title="More Settings" className="animate-fade-in stagger-4">
        <div className="space-y-2">
          {[
            { label: "Workspace settings", to: "/workspace/settings?tab=workspace", icon: <Building2 size={14} /> },
            { label: "Industry configuration", to: "/workspace/settings?tab=industry", icon: <User size={14} /> },
            { label: "Notification preferences", to: "/workspace/settings?tab=notifications", icon: <User size={14} /> },
          ].map((item) => (
            <Link
              key={item.to}
              to={item.to}
              className="flex items-center justify-between p-3 rounded-xl border border-line hover:bg-surface-2 transition-colors group"
            >
              <span className="flex items-center gap-2 text-sm font-medium text-content">
                <span className="text-slate-400 group-hover:text-violet-500 transition-colors" aria-hidden="true">
                  {item.icon}
                </span>
                {item.label}
              </span>
              <ArrowRight size={14} className="text-slate-400 group-hover:text-violet-500 transition-colors" aria-hidden="true" />
            </Link>
          ))}
        </div>
      </Card>
    </div>
  );
};
