import { useState, useEffect, useMemo, useRef, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import {
  Lock,
  Mail,
  Building2,
  User,
  ShieldCheck,
  Workflow,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
} from "@/components/ui/icons";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import toast from "react-hot-toast";
import clsx from "clsx";
import { GoogleAuthProvider, signInWithPopup } from "firebase/auth";
import { useAuthStore } from "@/stores/auth";
import { firebaseAuth, firebaseEnabled } from "@/lib/firebase";
import { Button } from "@/components/ui/Button";
import { LogoMark } from "@/components/ui/Logo";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { authApi } from "@/api/auth";
import { getErrorMessage } from "@/utils/errors";
import { IndustryPicker } from "@/components/auth/IndustryPicker";
import type { IndustryCode } from "@/types/api";

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

// ── Narrative panel — a calm, instrument-grade product promise ───────────────

const NARRATIVE = ["Plan, not guess", "Signals that move demand", "Built for the enterprise"];

const NarrativePanel = ({ isSignUp, reduceMotion }: { isSignUp: boolean; reduceMotion: boolean }) => (
  <aside className="relative hidden min-h-screen overflow-hidden bg-[linear-gradient(145deg,#03363D_0%,#022429_72%,#021a1d_100%)] px-12 py-10 text-white lg:flex lg:flex-col xl:px-16 xl:py-12">
    <div aria-hidden className="pointer-events-none absolute -left-24 top-1/3 h-80 w-80 rounded-full bg-[#BDD9D7]/[0.08] blur-3xl" />
    <div
      aria-hidden
      className="pointer-events-none absolute inset-0 opacity-[0.045]"
      style={{
        backgroundImage:
          "linear-gradient(to right, #fff 1px, transparent 1px), linear-gradient(to bottom, #fff 1px, transparent 1px)",
        backgroundSize: "56px 56px",
      }}
    />

    <div className="relative flex items-center gap-3">
      <LogoMark size={40} variant="tile" className="rounded-xl ring-1 ring-white/10" />
      <div>
        <div className="font-heading text-lg font-bold tracking-tight text-white">SANKET</div>
        <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[#BDD9D7]/60">Predictive OS</div>
      </div>
    </div>

    <div className="relative my-auto max-w-xl py-12">
      <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.06] px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.16em] text-[#BDD9D7]">
        <span className="h-1.5 w-1.5 rounded-full bg-[#BDD9D7]" />
        Secure planning access
      </div>
      <AnimatePresence mode="wait">
        <motion.div
          key={isSignUp ? "signup-story" : "signin-story"}
          initial={reduceMotion ? false : { opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={reduceMotion ? { duration: 0 } : { duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
        >
          <h2 className="max-w-[15ch] font-heading text-4xl font-semibold leading-[1.08] tracking-[-0.035em] text-white xl:text-5xl">
            {isSignUp
              ? "Build a workspace around the signals that matter."
              : "Return to the decisions your supply chain is waiting on."}
          </h2>
          <p className="mt-5 max-w-lg text-base leading-7 text-white/65">
            One calm operating layer for demand signals, forecasts, scenarios, and the decisions they support.
          </p>
        </motion.div>
      </AnimatePresence>

      <div className="mt-10 rounded-[24px] border border-white/10 bg-white/[0.055] p-5 shadow-2xl shadow-black/10 backdrop-blur-sm">
        <div className="flex items-center justify-between border-b border-white/10 pb-4">
          <div>
            <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[#BDD9D7]/60">Planning flow</div>
            <div className="mt-1 text-sm font-semibold text-white">From signal to accountable action</div>
          </div>
          <Workflow size={20} className="text-[#BDD9D7]" aria-hidden="true" />
        </div>
        <div className="grid grid-cols-[1fr_auto_1fr_auto_1fr] items-center gap-2 py-5 text-center">
          {["Signals", "Forecast", "Decision"].map((label, index) => (
            <div key={label} className="contents">
              <div className="rounded-xl border border-white/10 bg-black/10 px-2 py-3 text-xs font-semibold text-white/80">{label}</div>
              {index < 2 && <ArrowRight size={15} className="text-[#BDD9D7]/55" aria-hidden="true" />}
            </div>
          ))}
        </div>
        <div className="flex flex-wrap gap-x-5 gap-y-2 border-t border-white/10 pt-4 text-xs text-white/55">
          {NARRATIVE.map((item) => (
            <span key={item} className="inline-flex items-center gap-1.5">
              <CheckCircle2 size={13} className="text-[#BDD9D7]" aria-hidden="true" />
              {item}
            </span>
          ))}
        </div>
      </div>
    </div>

    <div className="relative flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] text-white/45">
      <span>Role-aware</span><span aria-hidden="true">·</span>
      <span>Audit-ready</span><span aria-hidden="true">·</span>
      <span>Tenant-isolated</span>
    </div>
  </aside>
);

// ── Component ────────────────────────────────────────────────────────────────

export const LoginPage = () => {
  const navigate = useNavigate();
  const location = useLocation() as { search: string; state?: { from?: string } };
  const isAuth = useAuthStore((s) => s.isAuthenticated);
  const login = useAuthStore((s) => s.login);
  const reduceMotion = Boolean(useReducedMotion());

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

  // Sign Up state
  const [signUpName, setSignUpName] = useState("");
  const [signUpSlug, setSignUpSlug] = useState("");
  const [signUpEmail, setSignUpEmail] = useState("");
  const [signUpPassword, setSignUpPassword] = useState("");
  const [signUpConfirmPassword, setSignUpConfirmPassword] = useState("");
  const [signUpIndustry, setSignUpIndustry] = useState<IndustryCode | null>(null);
  const [signUpStep, setSignUpStep] = useState<"account" | "workspace">("account");
  const signUpHeadingRef = useRef<HTMLHeadingElement>(null);

  // Shared
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Google onboarding modal (first-time Google sign-in)
  const [googleModalOpen, setGoogleModalOpen] = useState(false);
  const [googlePendingToken, setGooglePendingToken] = useState<string | null>(null);
  const [googlePendingName, setGooglePendingName] = useState("");
  const [googleWorkspace, setGoogleWorkspace] = useState("");
  const [googleIndustry, setGoogleIndustry] = useState<IndustryCode | null>(null);
  const [googleModalLoading, setGoogleModalLoading] = useState(false);
  const [googleModalError, setGoogleModalError] = useState<string | null>(null);

  const pwStrength = useMemo(() => passwordStrength(signUpPassword), [signUpPassword]);

  useEffect(() => {
    if (isSignUp) signUpHeadingRef.current?.focus({ preventScroll: true });
  }, [isSignUp, signUpStep]);

  if (isAuth) return <Navigate to="/workspace" replace />;

  // ── Handlers (logic preserved) ──

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login({ tenant_slug, email, password });
      toast.success("Welcome back!");
      navigate(location.state?.from ?? "/workspace", { replace: true });
    } catch (err) {
      setError(extractAuthError(err));
    } finally {
      setLoading(false);
    }
  };

  const continueToWorkspace = () => {
    setError(null);
    if (!signUpName.trim() || !signUpEmail.trim() || !signUpPassword || !signUpConfirmPassword) {
      setError("Complete your account details to continue");
      return;
    }
    if (!/^\S+@\S+\.\S+$/.test(signUpEmail)) {
      setError("Enter a valid work email address");
      return;
    }
    if (signUpPassword !== signUpConfirmPassword) {
      setError("Passwords do not match");
      return;
    }
    if (pwStrength.score < 2) {
      setError("Password is too weak — use at least 8 characters with mixed case and numbers");
      return;
    }
    setSignUpStep("workspace");
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
    if (signUpSlug.trim().length < 2) {
      setError("Enter a workspace name with at least 2 characters");
      return;
    }
    // No default. Signup used to stamp every new workspace Fashion and grant
    // all five verticals alongside it; picking one for the customer here would
    // be the same mistake with a nicer form.
    if (!signUpIndustry) {
      setError("Choose the industry this workspace plans for");
      return;
    }

    setLoading(true);
    try {
      await authApi.signUp({
        name: signUpName,
        email: signUpEmail,
        password: signUpPassword,
        tenant_slug: signUpSlug,
        industry: signUpIndustry,
      });
      toast.success("Account created — check your inbox to verify your email.");
      await login({
        tenant_slug: signUpSlug,
        email: signUpEmail,
        password: signUpPassword,
      });
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
        await verifySession(token);
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
    // Same rule as the password path: creating a workspace means choosing its
    // industry. Without this the Google flow would be the one route that still
    // picked for the customer.
    if (!googleIndustry) {
      setGoogleModalError("Choose the industry this workspace plans for");
      return;
    }
    setGoogleModalLoading(true);
    try {
      const s = await authApi.googleSignup({
        id_token: googlePendingToken,
        workspace_slug: googleWorkspace,
        name: googlePendingName,
        industry: googleIndustry,
      });
      useAuthStore.getState().setSession(s, googlePendingToken);
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
    <div className="min-h-screen bg-canvas lg:grid lg:grid-cols-[minmax(0,1.08fr)_minmax(480px,0.92fr)]">
      <a
        href="#login-form"
        className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:bg-accent focus:px-4 focus:py-2 focus:text-sm focus:font-semibold focus:text-accent-fg"
      >
        Skip to main content
      </a>

      <NarrativePanel isSignUp={isSignUp} reduceMotion={reduceMotion} />

      <main
        id="login-form"
        className="relative flex min-h-screen items-center justify-center overflow-hidden px-4 py-6 sm:px-8 lg:px-10 xl:px-14"
        role="main"
      >
        <div aria-hidden className="pointer-events-none absolute -right-32 -top-24 h-72 w-72 rounded-full bg-white/70 blur-3xl" />
        <div aria-hidden className="pointer-events-none absolute -bottom-32 -left-24 h-80 w-80 rounded-full bg-[#BDD9D7]/35 blur-3xl" />
        <motion.div
          layout={reduceMotion ? false : "position"}
          transition={reduceMotion ? { duration: 0 } : { type: "spring", stiffness: 350, damping: 32 }}
          className="relative w-full max-w-[520px]"
        >
          <div className="mb-5 flex items-center justify-between px-1 lg:hidden">
            <div className="flex items-center gap-2.5">
              <LogoMark size={36} variant="tile" className="rounded-xl" />
              <div>
                <div className="font-heading text-base font-bold tracking-tight text-content">SANKET</div>
                <div className="text-[9px] font-semibold uppercase tracking-[0.16em] text-content-subtle">Predictive OS</div>
              </div>
            </div>
            <span className="inline-flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-content-subtle">
              <ShieldCheck size={13} aria-hidden="true" /> Secure
            </span>
          </div>

          <section className="rounded-[28px] border border-line-strong bg-surface p-5 shadow-[0_24px_70px_-28px_rgba(2,35,39,0.34)] sm:p-8">
            <div className="tab-group-container relative mb-7 flex w-full">
              <button
                type="button"
                onClick={() => {
                  setIsSignUp(false);
                  setError(null);
                }}
                className={clsx(
                  "z-10 min-h-10 flex-1 cursor-pointer select-none rounded-lg px-3.5 py-2 text-sm font-semibold transition-colors duration-200",
                  isSignUp ? "text-content-muted hover:text-content" : "text-accent",
                )}
                aria-pressed={!isSignUp}
              >
                Sign in
              </button>
              <button
                type="button"
                onClick={() => {
                  setIsSignUp(true);
                  setSignUpStep("account");
                  setError(null);
                }}
                className={clsx(
                  "z-10 min-h-10 flex-1 cursor-pointer select-none rounded-lg px-3.5 py-2 text-sm font-semibold transition-colors duration-200",
                  isSignUp ? "text-accent" : "text-content-muted hover:text-content",
                )}
                aria-pressed={isSignUp}
              >
                Create account
              </button>
              <motion.div
                className="absolute bottom-1 top-1 rounded-lg border border-border bg-surface shadow-sm"
                layoutId="activeTabIndicator"
                transition={reduceMotion ? { duration: 0 } : { type: "spring", stiffness: 380, damping: 30 }}
                style={{
                  left: isSignUp ? "calc(50% + 2px)" : "4px",
                  right: isSignUp ? "4px" : "calc(50% + 2px)",
                }}
              />
            </div>

            <AnimatePresence mode="wait">
              {!isSignUp ? (
                <motion.div
                  key="signin"
                  initial={reduceMotion ? false : { opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  transition={reduceMotion ? { duration: 0 } : { duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
                >
                  <form onSubmit={onSubmit} className="space-y-4" aria-label="Sign in form" noValidate>
                    <header className="mb-6">
                      <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-content-subtle">Workspace access</p>
                      <h1 className="font-heading text-3xl font-semibold tracking-[-0.03em] text-content">Welcome back</h1>
                      <p className="mt-2 text-sm leading-6 text-content-subtle">Sign in to continue to your planning workspace.</p>
                    </header>

                    <Button
                      type="button"
                      variant="secondary"
                      onClick={handleGoogleSignIn}
                      disabled={loading}
                      className="min-h-11 w-full"
                      icon={<GoogleIcon />}
                      aria-label="Sign in with Google"
                    >
                      Continue with Google
                    </Button>
                    <Divider />

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
                    <Input
                      id="signin-password"
                      name="signin-password"
                      label="Password"
                      type="password"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      icon={<Lock size={15} aria-hidden="true" />}
                      placeholder="••••••••"
                      required
                      autoComplete="current-password"
                      error={error ?? undefined}
                    />

                    <div className="-mt-1 flex justify-end">
                      <Link to="/forgot-password" className="text-xs font-semibold text-content-muted underline-offset-4 hover:text-content hover:underline">
                        Forgot password?
                      </Link>
                    </div>
                    <Button type="submit" loading={loading} className="min-h-11 w-full" aria-busy={loading}>
                      Sign in <ArrowRight size={15} aria-hidden="true" />
                    </Button>
                    <LegalConsent action="signing in" />
                  </form>
                </motion.div>
              ) : (
                <motion.div
                  key={`signup-${signUpStep}`}
                  initial={reduceMotion ? false : { opacity: 0, x: signUpStep === "workspace" ? 10 : -10 }}
                  animate={{ opacity: 1, x: 0 }}
                  exit={{ opacity: 0, x: signUpStep === "workspace" ? -10 : 10 }}
                  transition={reduceMotion ? { duration: 0 } : { duration: 0.18, ease: [0.16, 1, 0.3, 1] }}
                >
                  <div className="mb-6" aria-label="Workspace creation progress">
                    <div className="mb-2 flex items-center justify-between text-[10px] font-semibold uppercase tracking-[0.14em] text-content-subtle">
                      <span>Account</span>
                      <span>Workspace</span>
                    </div>
                    <div className="grid grid-cols-2 gap-2" aria-hidden="true">
                      <span className="h-1 rounded-full bg-accent" />
                      <span className={clsx("h-1 rounded-full transition-colors", signUpStep === "workspace" ? "bg-accent" : "bg-surface-3")} />
                    </div>
                    <p className="mt-2 text-xs text-content-subtle">Step {signUpStep === "account" ? "1" : "2"} of 2</p>
                  </div>

                  <form
                    onSubmit={signUpStep === "account" ? (e) => { e.preventDefault(); continueToWorkspace(); } : onSignUpSubmit}
                    className="space-y-4"
                    aria-label="Create account form"
                    noValidate
                  >
                    {signUpStep === "account" ? (
                      <>
                        <header className="mb-5">
                          <h1 ref={signUpHeadingRef} tabIndex={-1} className="font-heading text-3xl font-semibold tracking-[-0.03em] text-content outline-none">Create your account</h1>
                          <p className="mt-2 text-sm leading-6 text-content-subtle">Start with your details. Your planning environment comes next.</p>
                        </header>

                        <Button
                          type="button"
                          variant="secondary"
                          onClick={handleGoogleSignIn}
                          disabled={loading}
                          className="min-h-11 w-full"
                          icon={<GoogleIcon />}
                          aria-label="Sign up with Google"
                        >
                          Continue with Google
                        </Button>
                        <Divider />

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
                          id="signup-email"
                          name="signup-email"
                          label="Work email"
                          type="email"
                          value={signUpEmail}
                          onChange={(e) => setSignUpEmail(e.target.value)}
                          icon={<Mail size={15} aria-hidden="true" />}
                          placeholder="you@company.com"
                          required
                          autoComplete="email"
                        />
                        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                          <Input
                            id="signup-password"
                            name="signup-password"
                            label="Password"
                            type="password"
                            value={signUpPassword}
                            onChange={(e) => setSignUpPassword(e.target.value)}
                            icon={<Lock size={15} aria-hidden="true" />}
                            placeholder="Min. 8 characters"
                            required
                            autoComplete="new-password"
                          />
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
                            error={signUpConfirmPassword && signUpPassword !== signUpConfirmPassword ? "Passwords do not match" : undefined}
                          />
                        </div>

                        {signUpPassword && (
                          <div className="space-y-1.5" aria-live="polite">
                            <div className="flex gap-1">
                              {[1, 2, 3, 4].map((i) => (
                                <div
                                  key={i}
                                  className={clsx(
                                    "h-1 flex-1 rounded-full transition-colors duration-200",
                                    i <= pwStrength.score ? pwStrength.color : "bg-surface-3",
                                  )}
                                />
                              ))}
                            </div>
                            <p className="text-[11px] text-content-subtle">
                              Password strength: <span className={clsx("font-semibold", pwStrength.score >= 3 ? "text-emerald-600" : pwStrength.score >= 2 ? "text-amber-600" : "text-rose-600")}>{pwStrength.label}</span>
                            </p>
                          </div>
                        )}

                        {error && <p role="alert" className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2.5 text-xs font-medium text-rose-700">{error}</p>}
                        <Button type="submit" className="min-h-11 w-full">
                          Continue to workspace <ArrowRight size={15} aria-hidden="true" />
                        </Button>
                        <LegalConsent action="creating an account" />
                      </>
                    ) : (
                      <>
                        <header className="mb-5">
                          <h1 ref={signUpHeadingRef} tabIndex={-1} className="font-heading text-3xl font-semibold tracking-[-0.03em] text-content outline-none">Set up your workspace</h1>
                          <p className="mt-2 text-sm leading-6 text-content-subtle">Name your planning environment and choose the industry model it should use.</p>
                        </header>

                        <div className="flex items-center gap-3 rounded-xl border border-line bg-surface-2 px-3.5 py-3">
                          <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-accent-soft text-accent"><CheckCircle2 size={16} aria-hidden="true" /></span>
                          <div className="min-w-0">
                            <p className="text-xs font-semibold text-content">Account details ready</p>
                            <p className="truncate text-xs text-content-subtle">{signUpEmail}</p>
                          </div>
                        </div>

                        <Input
                          id="signup-workspace"
                          name="signup-workspace"
                          label="Workspace name"
                          value={signUpSlug}
                          onChange={(e) => setSignUpSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""))}
                          icon={<Building2 size={15} aria-hidden="true" />}
                          placeholder="acme-co"
                          hint="Lowercase letters, numbers and hyphens · 2–63 characters"
                          required
                          autoComplete="off"
                        />

                        <IndustryPicker
                          value={signUpIndustry}
                          onChange={(industry) => {
                            setSignUpIndustry(industry);
                            setError(null);
                          }}
                          disabled={loading}
                        />

                        {error && <p role="alert" className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2.5 text-xs font-medium text-rose-700">{error}</p>}
                        <div className="grid grid-cols-[auto_1fr] gap-3 pt-1">
                          <Button
                            type="button"
                            variant="secondary"
                            onClick={() => {
                              setError(null);
                              setSignUpStep("account");
                            }}
                            className="min-h-11 px-3"
                            aria-label="Back to account details"
                          >
                            <ArrowLeft size={15} aria-hidden="true" /> Back
                          </Button>
                          <Button type="submit" loading={loading} className="min-h-11 w-full">
                            Create workspace <ArrowRight size={15} aria-hidden="true" />
                          </Button>
                        </div>
                        <p className="text-center text-[11px] leading-relaxed text-content-subtle">Your industry selection locks after setup to keep forecasts and permissions consistent.</p>
                      </>
                    )}
                  </form>
                </motion.div>
              )}
            </AnimatePresence>
          </section>

          <p className="mt-4 text-center text-[11px] text-content-subtle lg:hidden">
            Role-aware · Audit-ready · Tenant-isolated
          </p>
        </motion.div>
      </main>

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
              disabled={!googleWorkspace || googleWorkspace.length < 2 || !googlePendingName || !googleIndustry || googleModalLoading}
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
          <IndustryPicker
            value={googleIndustry}
            onChange={setGoogleIndustry}
            disabled={googleModalLoading}
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
