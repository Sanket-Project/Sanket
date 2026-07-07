import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { Mail, ArrowLeft, CheckCircle2 } from "lucide-react";
import { sendPasswordResetEmail } from "firebase/auth";
import { firebaseAuth, firebaseEnabled } from "@/lib/firebase";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

export const ForgotPasswordPage = () => {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (!firebaseEnabled || !firebaseAuth) {
        throw new Error("Password reset requires Firebase authentication.");
      }
      await sendPasswordResetEmail(firebaseAuth, email);
      setSent(true);
    } catch (err) {
      const msg =
        (err as { message?: string })?.message ||
        "Failed to send reset email. Please try again.";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4 relative overflow-hidden bg-slate-50 dark:bg-ink-900 transition-colors duration-300">
      {/* Skip link */}
      <a
        href="#forgot-password-form"
        className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50 focus:px-4 focus:py-2 focus:bg-violet-600 focus:text-white focus:rounded-lg focus:text-sm focus:font-semibold"
      >
        Skip to main content
      </a>

      {/* Decorative orbs */}
      <div className="absolute top-1/4 left-1/4 w-72 h-72 rounded-full bg-violet-500/15 blur-3xl pointer-events-none" aria-hidden="true" />
      <div className="absolute bottom-1/4 right-1/4 w-72 h-72 rounded-full bg-cyan-500/10 blur-3xl pointer-events-none" aria-hidden="true" />

      <main
        id="forgot-password-form"
        className="relative w-full max-w-md glass-strong rounded-3xl shadow-2xl overflow-hidden bg-white/70 dark:bg-[#0d1321]/80 border border-slate-200/50 dark:border-white/10 p-10"
        role="main"
      >
        {/* Brand */}
        <div className="flex items-center gap-2 mb-8" aria-hidden="true">
          <div className="inline-flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-accent shadow-lg shadow-accent-primary/20">
            <span className="text-lg font-bold text-white font-heading">P</span>
          </div>
          <span className="text-xl font-bold tracking-tight text-slate-800 dark:text-white font-heading">SANKET</span>
        </div>

        {sent ? (
          /* Success state */
          <div className="text-center space-y-4" role="alert" aria-live="polite">
            <div className="flex justify-center">
              <CheckCircle2 size={48} className="text-emerald-500" aria-hidden="true" />
            </div>
            <h1 className="text-2xl font-bold text-slate-800 dark:text-white font-heading">
              Check your email
            </h1>
            <p className="text-sm text-slate-500 dark:text-slate-400 leading-relaxed">
              We sent a password reset link to{" "}
              <strong className="text-slate-700 dark:text-slate-200">{email}</strong>.
              The link expires in 1 hour.
            </p>
            <p className="text-xs text-slate-400">
              Didn't receive it? Check your spam folder, or{" "}
              <button
                type="button"
                onClick={() => { setSent(false); setEmail(""); }}
                className="text-violet-600 dark:text-violet-400 font-medium hover:underline"
              >
                try a different address
              </button>
              .
            </p>
            <Link
              to="/login"
              className="mt-4 inline-flex items-center gap-2 text-sm text-violet-600 dark:text-violet-400 font-semibold hover:underline"
            >
              <ArrowLeft size={14} aria-hidden="true" />
              Back to sign in
            </Link>
          </div>
        ) : (
          /* Request form */
          <form onSubmit={onSubmit} className="space-y-5" aria-label="Forgot password form" noValidate>
            <div className="space-y-1">
              <h1 className="text-2xl font-bold text-slate-800 dark:text-white font-heading">
                Forgot password?
              </h1>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Enter the email associated with your account and we'll send you a reset link.
              </p>
            </div>

            <Input
              id="forgot-email"
              label="Email address"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              icon={<Mail size={14} className="text-slate-400" aria-hidden="true" />}
              placeholder="you@company.com"
              required
              autoComplete="email"
              aria-required="true"
              error={error ?? undefined}
            />

            <Button
              type="submit"
              loading={loading}
              className="w-full"
              size="md"
              aria-busy={loading}
            >
              Send reset link
            </Button>

            <div className="text-center">
              <Link
                to="/login"
                className="inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-violet-600 dark:hover:text-violet-400 font-medium transition-colors"
                aria-label="Return to sign in page"
              >
                <ArrowLeft size={12} aria-hidden="true" />
                Back to sign in
              </Link>
            </div>
          </form>
        )}
      </main>
    </div>
  );
};
