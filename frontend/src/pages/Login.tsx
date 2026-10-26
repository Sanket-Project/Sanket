import { useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { Lock, Mail, Building2, Workflow, ArrowRight, CheckCircle2 } from "@/components/ui/icons";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import toast from "react-hot-toast";
import { GoogleAuthProvider, signInWithPopup, signOut } from "firebase/auth";
import { useAuthStore } from "@/stores/auth";
import { firebaseAuth, firebaseEnabled } from "@/lib/firebase";
import { Button } from "@/components/ui/Button";
import { LogoMark } from "@/components/ui/Logo";
import { Input } from "@/components/ui/Input";
import { getErrorMessage } from "@/utils/errors";

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

export const LoginPage = () => {
  const navigate = useNavigate();
  const location = useLocation() as { state?: { from?: string } };
  const isAuth = useAuthStore((s) => s.isAuthenticated);
  const login = useAuthStore((s) => s.login);
  const reduceMotion = Boolean(useReducedMotion());
  const [tenant_slug, setSlug] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (isAuth) return <Navigate to="/workspace" replace />;
  const destination = location.state?.from?.startsWith("/workspace") ? location.state.from : "/workspace";
  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login({ tenant_slug, email, password });
      toast.success("Welcome back!");
      navigate(destination, { replace: true });
    } catch (err) { setError(extractAuthError(err)); }
    finally { setLoading(false); }
  };
  const handleGoogleSignIn = async () => {
    if (!firebaseAuth) return;
    setError(null);
    setLoading(true);
    try {
      const cred = await signInWithPopup(firebaseAuth, new GoogleAuthProvider());
      await useAuthStore.getState().verifySession(await cred.user.getIdToken(true));
      navigate(destination, { replace: true });
    } catch (err) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 404 || status === 403) {
        await signOut(firebaseAuth);
        setError("Your account has not been invited. Contact your SANKET administrator.");
      } else { setError(extractAuthError(err)); }
    } finally { setLoading(false); }
  };
  return (
    <div className="min-h-screen bg-canvas lg:grid lg:grid-cols-[minmax(0,1.08fr)_minmax(480px,0.92fr)]">
      <a href="#login-form" className="sr-only focus:not-sr-only">Skip to main content</a>
      <NarrativePanel isSignUp={false} reduceMotion={reduceMotion} />
      <main id="login-form" className="flex min-h-screen items-center justify-center px-4 py-8 sm:px-8">
        <section className="w-full max-w-[520px] rounded-[28px] border border-line-strong bg-surface p-6 shadow-xl sm:p-8">
                  <form onSubmit={onSubmit} className="space-y-4" aria-label="Sign in form">
                    <header className="mb-6">
                      <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-content-subtle">Workspace access</p>
                      <h1 className="font-heading text-3xl font-semibold tracking-[-0.03em] text-content">Welcome back</h1>
                      <p className="mt-2 text-sm leading-6 text-content-subtle">Sign in to continue to your planning workspace.</p>
                    </header>

                    {firebaseEnabled && <Button
                      type="button"
                      variant="secondary"
                      onClick={handleGoogleSignIn}
                      disabled={loading}
                      className="min-h-11 w-full"
                      icon={<GoogleIcon />}
                      aria-label="Sign in with Google"
                    >
                      Continue with Google
                    </Button>}

                    {!firebaseEnabled && <Input
                      id="signin-workspace"
                      name="signin-workspace"
                      label="Workspace"
                      value={tenant_slug}
                      onChange={(e) => setSlug(e.target.value)}
                      icon={<Building2 size={15} aria-hidden="true" />}
                      placeholder="acme-co"
                      required
                      autoComplete="organization"
                    />}
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
          <p className="mt-6 text-center text-sm text-content-subtle">Access is by invitation. Contact your SANKET administrator for an account.</p>
        </section>
      </main>
    </div>
  );
};
