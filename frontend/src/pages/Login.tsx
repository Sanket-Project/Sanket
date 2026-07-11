import { useState, useEffect, useMemo, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import {
  Lock,
  Mail,
  Building2,
  User,
  Eye,
  EyeOff,
  TrendingUp,
  ShieldCheck,
  Workflow,
} from "lucide-react";
import toast from "react-hot-toast";
import clsx from "clsx";
import { GoogleAuthProvider, signInWithPopup } from "firebase/auth";
import { useAuthStore } from "@/stores/auth";
import { useIndustryStore } from "@/stores/industry";
import { firebaseAuth, firebaseEnabled } from "@/lib/firebase";
import { Button } from "@/components/ui/Button";
import { LogoMark } from "@/components/ui/Logo";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { authApi } from "@/api/auth";
import { getErrorMessage } from "@/utils/errors";

// ── Helpers ─────────────────────────────────────────────────────────────────

/** Map an axios (backend) or Firebase SDK auth error to a friendly message. */
function extractAuthError(e: unknown): string {
  const detail = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (detail != null) {
    return getErrorMessage(e, "Sign-in failed");
  }
  const code = (e as { code?: string })?.code;
  if (code) {
    switch (code) {
      case "auth/invalid-credential":
      case "auth/wrong-password":
      case "auth/user-not-found":
      case "auth/invalid-email":
        return "Invalid email or password";
      case "auth/too-many-requests":
        return "Too many attempts. Try again later.";
      case "auth/user-disabled":
        return "This account has been disabled.";
      case "auth/network-request-failed":
        return "Network error — please try again.";
      case "auth/popup-closed-by-user":
        return "Sign-in cancelled";
      case "auth/popup-blocked":
        return "Pop-up blocked — please allow pop-ups and try again.";
      default:
        return "Sign-in failed";
    }
  }
  return "Sign-in failed";
}

/** Password strength: returns 0–4. */
function passwordStrength(pwd: string): { score: number; label: string; color: string } {
  if (!pwd) return { score: 0, label: "", color: "" };
  let score = 0;
  if (pwd.length >= 8) score++;
  if (pwd.length >= 12) score++;
  if (/[A-Z]/.test(pwd) && /[a-z]/.test(pwd)) score++;
  if (/[0-9]/.test(pwd)) score++;
  if (/[^A-Za-z0-9]/.test(pwd)) score++;
  const clamped = Math.min(score, 4);
  const labels = ["", "Weak", "Fair", "Good", "Strong"];
  const colors = ["", "bg-rose-500", "bg-amber-400", "bg-blue-500", "bg-emerald-500"];
  return { score: clamped, label: labels[clamped], color: colors[clamped] };
}

const LegalConsent = ({ action }: { action: string }) => (
  <p className="text-center text-[11px] leading-relaxed text-content-subtle">
    By {action} you agree to our{" "}
    <Link to="/terms" target="_blank" rel="noopener noreferrer" className="font-medium text-content-muted underline-offset-2 hover:underline">
      Terms of Service
    </Link>{" "}
    and{" "}
    <Link to="/privacy" target="_blank" rel="noopener noreferrer" className="font-medium text-content-muted underline-offset-2 hover:underline">
      Privacy Policy
    </Link>
    .
  </p>
);

const GoogleIcon = () => (
  <svg className="h-4 w-4" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
    <path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4" />
    <path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853" />
    <path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" fill="#FBBC05" />
    <path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" fill="#EA4335" />
  </svg>
);

// ── Narrative panel (right) — restrained, no marketing decoration ────────────

const NARRATIVE = [
  {
    icon: <Workflow size={18} aria-hidden="true" />,
    title: "Plan, not guess",
    body: "Scenario compare, signal-aware forecasts, and overrides with a full audit trail.",
  },
  {
    icon: <TrendingUp size={18} aria-hidden="true" />,
    title: "Signals that move demand",
    body: "Weather, trends, competitors, and macro — folded into every plan automatically.",
  },
  {
    icon: <ShieldCheck size={18} aria-hidden="true" />,
    title: "Built for the enterprise",
    body: "Role-aware workspaces, GxP-grade audit, and tenant isolation by default.",
  },
];

const NarrativePanel = () => (
  <div className="relative hidden h-full flex-col justify-between overflow-hidden px-12 py-14 text-white lg:flex bg-[linear-gradient(160deg,#03363D_0%,#022429_100%)]">
    {/* Ambient decoration — a soft glow + faint grid, purely aesthetic */}
    <div aria-hidden className="pointer-events-none absolute -right-24 -top-24 h-80 w-80 rounded-full bg-[#BDD9D7]/10 blur-3xl" />
    <div aria-hidden className="pointer-events-none absolute -bottom-32 -left-16 h-72 w-72 rounded-full bg-[#BDD9D7]/[0.06] blur-3xl" />
    <div
      aria-hidden
      className="pointer-events-none absolute inset-0 opacity-[0.05]"
      style={{
        backgroundImage:
          "linear-gradient(to right, #fff 1px, transparent 1px), linear-gradient(to bottom, #fff 1px, transparent 1px)",
        backgroundSize: "44px 44px",
      }}
    />

    <div className="relative flex items-center gap-2.5">
      <LogoMark size={36} variant="tile" className="rounded-xl" />
      <span className="font-heading text-lg font-bold tracking-tight" style={{ color: "#ffffff" }}>SANKET</span>
    </div>

    <div className="relative max-w-md">
      <h2 className="font-heading text-[2rem] font-bold leading-[1.15] tracking-tight" style={{ color: "#ffffff" }}>
        The planning system of record for modern supply chains.
      </h2>
      <ul className="mt-9 space-y-6">
        {NARRATIVE.map((n) => (
          <li key={n.title} className="flex gap-3.5">
            <span className="mt-0.5 grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-white/10 text-[#BDD9D7] ring-1 ring-white/10">
              {n.icon}
            </span>
            <div>
              <div className="text-sm font-semibold text-white">{n.title}</div>
              <div className="mt-1 text-sm leading-relaxed text-white/70">{n.body}</div>
            </div>
          </li>
        ))}
      </ul>
    </div>

    <div className="relative flex items-center gap-3 font-mono text-xs text-white/60">
      <span>SOC 2-aligned</span>
      <span className="text-white/25">·</span>
      <span>Role-based access</span>
      <span className="text-white/25">·</span>
      <span>Tenant-isolated</span>
    </div>
  </div>
);

// ── Component ────────────────────────────────────────────────────────────────

export const LoginPage = () => {
  const navigate = useNavigate();
  const location = useLocation() as { search: string; state?: { from?: string } };
  const isAuth = useAuthStore((s) => s.isAuthenticated);
  const login = useAuthStore((s) => s.login);
  const setIndustry = useIndustryStore((s) => s.setIndustry);

  const [isSignUp, setIsSignUp] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get("mode") === "signup";
  });

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setIsSignUp(params.get("mode") === "signup");
  }, [location.search]);

  // Sign In state
  const [tenant_slug, setSlug] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  // Sign Up state
  const [signUpName, setSignUpName] = useState("");
  const [signUpSlug, setSignUpSlug] = useState("");
  const [signUpEmail, setSignUpEmail] = useState("");
  const [signUpPassword, setSignUpPassword] = useState("");
  const [signUpConfirmPassword, setSignUpConfirmPassword] = useState("");
  const [showSignUpPassword, setShowSignUpPassword] = useState(false);

  // Shared
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Google onboarding modal (first-time Google sign-in)
  const [googleModalOpen, setGoogleModalOpen] = useState(false);
  const [googlePendingToken, setGooglePendingToken] = useState<string | null>(null);
  const [googlePendingName, setGooglePendingName] = useState("");
  const [googleWorkspace, setGoogleWorkspace] = useState("");
  const [googleModalLoading, setGoogleModalLoading] = useState(false);
  const [googleModalError, setGoogleModalError] = useState<string | null>(null);

  const pwStrength = useMemo(() => passwordStrength(signUpPassword), [signUpPassword]);

  if (isAuth) return <Navigate to="/workspace" replace />;

  // ── Handlers (logic preserved) ──

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const r = await login({ tenant_slug, email, password });
      setIndustry(r.active_industry);
      toast.success("Welcome back!");
      navigate(location.state?.from ?? "/workspace", { replace: true });
    } catch (err) {
      setError(extractAuthError(err));
    } finally {
      setLoading(false);
    }
  };

  const onSignUpSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);

    if (signUpPassword !== signUpConfirmPassword) {
      setError("Passwords do not match");
      return;
    }
    if (pwStrength.score < 2) {
      setError("Password is too weak — use at least 8 characters with mixed case and numbers");
      return;
    }

    setLoading(true);
    try {
      await authApi.signUp({
        name: signUpName,
        email: signUpEmail,
        password: signUpPassword,
        tenant_slug: signUpSlug,
      });
      toast.success("Account created — check your inbox to verify your email.");
      const r = await login({
        tenant_slug: signUpSlug,
        email: signUpEmail,
        password: signUpPassword,
      });
      setIndustry(r.active_industry);
      // New tenant → guided setup rather than an empty workspace.
      navigate("/onboarding", { replace: true });
    } catch (err) {
      setError(extractAuthError(err));
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleSignIn = async () => {
    setError(null);
    if (!firebaseEnabled || !firebaseAuth) {
      setError("Google Sign-In is not available in this environment");
      return;
    }
    setLoading(true);
    try {
      const provider = new GoogleAuthProvider();
      const cred = await signInWithPopup(firebaseAuth, provider);
      const token = await cred.user.getIdToken(true);

      try {
        const verifySession = useAuthStore.getState().verifySession;
        const s = await verifySession(token);
        setIndustry(s.active_industry);
        toast.success("Welcome back!");
        navigate(location.state?.from ?? "/workspace", { replace: true });
      } catch (sessionErr: unknown) {
        const status = (sessionErr as { response?: { status?: number } })?.response?.status;
        const detail = (sessionErr as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
        if (status === 404 && detail === "google_account_not_provisioned") {
          const userEmail = cred.user.email ?? "";
          const domain = userEmail.split("@")[1]?.split(".")[0] ?? "";
          setGoogleWorkspace(domain.toLowerCase().replace(/[^a-z0-9]/g, "-").replace(/-+/g, "-").replace(/^-|-$/g, ""));
          setGooglePendingName(cred.user.displayName ?? "");
          setGooglePendingToken(token);
          setGoogleModalOpen(true);
          return;
        }
        setError(extractAuthError(sessionErr));
      }
    } catch (err) {
      setError(extractAuthError(err));
    } finally {
      setLoading(false);
    }
  };

  const handleGoogleSignUpSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!googlePendingToken) return;
    setGoogleModalError(null);
    setGoogleModalLoading(true);
    try {
      const s = await authApi.googleSignup({
        id_token: googlePendingToken,
        workspace_slug: googleWorkspace,
        name: googlePendingName,
      });
      useAuthStore.getState().setSession(s, googlePendingToken);
      setIndustry(s.active_industry);
      toast.success("Welcome to SANKET!");
      setGoogleModalOpen(false);
      // New tenant → guided setup.
      navigate("/onboarding", { replace: true });
    } catch (err: unknown) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Account setup failed — please try again.";
      setGoogleModalError(detail);
    } finally {
      setGoogleModalLoading(false);
    }
  };

  // ── Render ──

  return (
    <div className="grid min-h-screen grid-cols-1 bg-canvas lg:grid-cols-2">
      <a
        href="#login-form"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-accent focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-accent-fg"
      >
        Skip to main content
      </a>

      {/* Form column */}
      <main
        id="login-form"
        className="flex items-center justify-center px-6 py-8 sm:px-10"
        role="main"
      >
        <div className={clsx("w-full", isSignUp ? "max-w-md" : "max-w-sm")}>
          {/* Brand (mobile + small) */}
          <div className="mb-8 flex items-center gap-2.5 lg:hidden">
            <LogoMark size={36} variant="tile" className="rounded-xl" />
            <span className="font-heading text-lg font-bold tracking-tight text-content">SANKET</span>
          </div>

          {/* Segmented toggle */}
          <div className="tab-group-container mb-5 w-full">
            <button
              type="button"
              onClick={() => setIsSignUp(false)}
              className={clsx("flex-1", isSignUp ? "tab-item-inactive" : "tab-item-active")}
              aria-pressed={!isSignUp}
            >
              Sign in
            </button>
            <button
              type="button"
              onClick={() => setIsSignUp(true)}
              className={clsx("flex-1", isSignUp ? "tab-item-active" : "tab-item-inactive")}
              aria-pressed={isSignUp}
            >
              Create account
            </button>
          </div>

          {!isSignUp ? (
            <form onSubmit={onSubmit} className="space-y-4" aria-label="Sign in form" noValidate>
              <div>
                <h1 className="font-heading text-2xl font-bold tracking-tight text-content">Sign in</h1>
                <p className="mt-1 text-sm text-content-subtle">Access your planning workspace.</p>
              </div>

              <Input
                id="signin-workspace"
                name="signin-workspace"
                label="Workspace"
                value={tenant_slug}
                onChange={(e) => setSlug(e.target.value)}
                icon={<Building2 size={15} aria-hidden="true" />}
                placeholder="acme-co"
                required
                autoComplete="organization"
              />
              <Input
                id="signin-email"
                name="signin-email"
                label="Email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                icon={<Mail size={15} aria-hidden="true" />}
                placeholder="you@company.com"
                required
                autoComplete="email"
              />
              <div className="relative">
                <Input
                  id="signin-password"
                  name="signin-password"
                  label="Password"
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  icon={<Lock size={15} aria-hidden="true" />}
                  placeholder="••••••••"
                  required
                  autoComplete="current-password"
                  error={error ?? undefined}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute right-3 top-[34px] text-content-subtle transition hover:text-content"
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>

              <div className="-mt-1 text-right">
                <Link to="/forgot-password" className="text-xs font-medium text-content-muted hover:text-content hover:underline">
                  Forgot password?
                </Link>
              </div>

              <Button type="submit" loading={loading} className="w-full" aria-busy={loading}>
                Sign in
              </Button>

              <Divider />

              <Button
                type="button"
                variant="secondary"
                onClick={handleGoogleSignIn}
                disabled={loading}
                className="w-full"
                icon={<GoogleIcon />}
                aria-label="Sign in with Google"
              >
                Continue with Google
              </Button>

              <LegalConsent action="signing in" />
            </form>
          ) : (
            <form onSubmit={onSignUpSubmit} className="space-y-4" aria-label="Create account form" noValidate>
              <div>
                <h1 className="font-heading text-2xl font-bold tracking-tight text-content">Create your workspace</h1>
                <p className="mt-1 text-sm text-content-subtle">Start planning with predictive supply-chain intelligence.</p>
              </div>

              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <Input
                  id="signup-name"
                  name="signup-name"
                  label="Full name"
                  value={signUpName}
                  onChange={(e) => setSignUpName(e.target.value)}
                  icon={<User size={15} aria-hidden="true" />}
                  placeholder="Jane Smith"
                  required
                  autoComplete="name"
                />
                <Input
                  id="signup-workspace"
                  name="signup-workspace"
                  label="Workspace"
                  value={signUpSlug}
                  onChange={(e) => setSignUpSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""))}
                  icon={<Building2 size={15} aria-hidden="true" />}
                  placeholder="acme-co"
                  hint="Lowercase, numbers & hyphens"
                  required
                  autoComplete="off"
                />
              </div>
              <Input
                id="signup-email"
                name="signup-email"
                label="Email"
                type="email"
                value={signUpEmail}
                onChange={(e) => setSignUpEmail(e.target.value)}
                icon={<Mail size={15} aria-hidden="true" />}
                placeholder="you@company.com"
                required
                autoComplete="email"
              />
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                <div className="relative">
                  <Input
                    id="signup-password"
                    name="signup-password"
                    label="Password"
                    type={showSignUpPassword ? "text" : "password"}
                    value={signUpPassword}
                    onChange={(e) => setSignUpPassword(e.target.value)}
                    icon={<Lock size={15} aria-hidden="true" />}
                    placeholder="Min. 8 characters"
                    required
                    autoComplete="new-password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowSignUpPassword((v) => !v)}
                    className="absolute right-3 top-[34px] text-content-subtle transition hover:text-content"
                    aria-label={showSignUpPassword ? "Hide password" : "Show password"}
                  >
                    {showSignUpPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
                <Input
                  id="signup-confirm-password"
                  name="signup-confirm-password"
                  label="Confirm password"
                  type="password"
                  value={signUpConfirmPassword}
                  onChange={(e) => setSignUpConfirmPassword(e.target.value)}
                  icon={<Lock size={15} aria-hidden="true" />}
                  placeholder="Repeat password"
                  required
                  autoComplete="new-password"
                  error={
                    (error && isSignUp ? error : undefined) ||
                    (signUpConfirmPassword && signUpPassword !== signUpConfirmPassword
                      ? "Passwords do not match"
                      : undefined)
                  }
                />
              </div>

              {signUpPassword && (
                <div className="space-y-1" aria-live="polite">
                  <div className="flex gap-1">
                    {[1, 2, 3, 4].map((i) => (
                      <div
                        key={i}
                        className={clsx(
                          "h-1 flex-1 rounded-full transition-all duration-300",
                          i <= pwStrength.score ? pwStrength.color : "bg-surface-3",
                        )}
                      />
                    ))}
                  </div>
                  <p className="text-[11px] text-content-subtle">
                    Password strength:{" "}
                    <span className={clsx("font-semibold", pwStrength.score >= 3 ? "text-emerald-600" : pwStrength.score >= 2 ? "text-amber-500" : "text-rose-500")}>
                      {pwStrength.label}
                    </span>
                  </p>
                </div>
              )}

              <Button
                type="submit"
                loading={loading}
                disabled={!!(signUpPassword && signUpConfirmPassword && signUpPassword !== signUpConfirmPassword)}
                className="w-full"
              >
                Create workspace
              </Button>

              <Divider />

              <Button
                type="button"
                variant="secondary"
                onClick={handleGoogleSignIn}
                disabled={loading}
                className="w-full"
                icon={<GoogleIcon />}
                aria-label="Sign up with Google"
              >
                Continue with Google
              </Button>

              <LegalConsent action="creating an account" />
            </form>
          )}
        </div>
      </main>

      {/* Narrative column */}
      <NarrativePanel />

      {/* Google onboarding modal (first-time Google sign-in) */}
      <Modal
        open={googleModalOpen}
        onClose={() => {
          setGoogleModalOpen(false);
          setGooglePendingToken(null);
          setGoogleModalError(null);
        }}
        title="Name your workspace"
        size="sm"
        footer={
          <>
            <Button
              variant="secondary"
              onClick={() => {
                setGoogleModalOpen(false);
                setGooglePendingToken(null);
                setGoogleModalError(null);
              }}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              form="google-onboarding-form"
              loading={googleModalLoading}
              disabled={!googleWorkspace || googleWorkspace.length < 2 || !googlePendingName || googleModalLoading}
            >
              Create workspace
            </Button>
          </>
        }
      >
        <form id="google-onboarding-form" onSubmit={handleGoogleSignUpSubmit} className="space-y-4">
          <Input
            id="google-signup-name"
            name="google-signup-name"
            label="Your name"
            value={googlePendingName}
            onChange={(e) => setGooglePendingName(e.target.value)}
            icon={<User size={15} aria-hidden="true" />}
            placeholder="Jane Smith"
            required
            autoComplete="name"
          />
          <Input
            id="google-signup-workspace"
            name="google-signup-workspace"
            label="Workspace"
            value={googleWorkspace}
            onChange={(e) => setGoogleWorkspace(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""))}
            icon={<Building2 size={15} aria-hidden="true" />}
            placeholder="acme-co"
            hint="Lowercase letters, numbers and hyphens only · 2–63 characters"
            required
            autoComplete="off"
            error={googleModalError ?? undefined}
          />
        </form>
      </Modal>
    </div>
  );
};

const Divider = () => (
  <div className="flex items-center gap-3 py-0.5" aria-hidden="true">
    <div className="h-px flex-grow bg-line" />
    <span className="text-[10px] font-semibold uppercase tracking-wider text-content-subtle">or</span>
    <div className="h-px flex-grow bg-line" />
  </div>
);
