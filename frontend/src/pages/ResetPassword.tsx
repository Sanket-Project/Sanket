import { useState, useEffect, type FormEvent } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { Lock, Eye, EyeOff, CheckCircle2, XCircle, ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

/** 4-level password strength (same logic as Login.tsx) */
function getPasswordStrength(pw: string): { score: number; label: string; color: string } {
  if (!pw) return { score: 0, label: "", color: "" };
  let score = 0;
  if (pw.length >= 8) score++;
  if (pw.length >= 12) score++;
  if (/[A-Z]/.test(pw) && /[a-z]/.test(pw)) score++;
  if (/\d/.test(pw) && /[^A-Za-z0-9]/.test(pw)) score++;
  const labels = ["Weak", "Fair", "Good", "Strong"];
  const colors = ["bg-rose-500", "bg-amber-500", "bg-yellow-400", "bg-emerald-500"];
  return { score, label: labels[score - 1] ?? "Weak", color: colors[score - 1] ?? "bg-rose-500" };
}

export const ResetPasswordPage = () => {
  const [searchParams] = useSearchParams();
  const oobCode = searchParams.get("oobCode") ?? "";
  const mode = searchParams.get("mode") ?? "";

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const strength = getPasswordStrength(password);
  const mismatch = confirm.length > 0 && password !== confirm;
  const invalid = !oobCode || mode !== "resetPassword";

  useEffect(() => {
    if (invalid) {
      setError("This password-reset link is invalid or has already been used. Please request a new one.");
    }
  }, [invalid]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (mismatch) return;
    if (strength.score < 1) {
      setError("Password must be at least 8 characters.");
      return;
    }
    setError(null);
    setLoading(true);
    try {
      const { confirmPasswordReset } = await import("firebase/auth");
      const { firebaseAuth, firebaseEnabled } = await import("@/lib/firebase");
      if (!firebaseEnabled || !firebaseAuth) {
        throw new Error("Password reset requires Firebase authentication.");
      }
      await confirmPasswordReset(firebaseAuth, oobCode, password);
      setDone(true);
    } catch (err) {
      const code = (err as { code?: string })?.code;
      if (code === "auth/expired-action-code") {
        setError("This reset link has expired. Please request a new one.");
      } else if (code === "auth/invalid-action-code") {
        setError("This reset link is invalid or has already been used.");
      } else if (code === "auth/weak-password") {
        setError("Password is too weak. Use at least 8 characters with a mix of letters, numbers, and symbols.");
      } else {
        setError((err as { message?: string })?.message ?? "Failed to reset password. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4 relative overflow-hidden bg-slate-50 dark:bg-ink-900 transition-colors duration-300">
      {/* Skip link */}
      <a
        href="#reset-password-form"
        className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50 focus:px-4 focus:py-2 focus:bg-violet-600 focus:text-white focus:rounded-lg focus:text-sm focus:font-semibold"
      >
        Skip to main content
      </a>

      {/* Decorative orbs */}
      <div className="absolute top-1/4 left-1/4 w-72 h-72 rounded-full bg-violet-500/15 blur-3xl pointer-events-none" aria-hidden="true" />
      <div className="absolute bottom-1/4 right-1/4 w-72 h-72 rounded-full bg-cyan-500/10 blur-3xl pointer-events-none" aria-hidden="true" />

      <main
        id="reset-password-form"
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

        {done ? (
          /* Success state */
          <div className="text-center space-y-4" role="alert" aria-live="polite">
            <div className="flex justify-center">
              <CheckCircle2 size={48} className="text-emerald-500" aria-hidden="true" />
            </div>
            <h1 className="text-2xl font-bold text-slate-800 dark:text-white font-heading">
              Password updated
            </h1>
            <p className="text-sm text-slate-500 dark:text-slate-400">
              Your password has been reset successfully. You can now sign in with your new password.
            </p>
            <Link
              to="/login"
              className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-violet-600 dark:text-violet-400 hover:underline"
            >
              <ArrowLeft size={14} aria-hidden="true" />
              Go to sign in
            </Link>
          </div>
        ) : invalid ? (
          /* Invalid link state */
          <div className="text-center space-y-4" role="alert" aria-live="polite">
            <div className="flex justify-center">
              <XCircle size={48} className="text-rose-500" aria-hidden="true" />
            </div>
            <h1 className="text-2xl font-bold text-slate-800 dark:text-white font-heading">
              Invalid reset link
            </h1>
            <p className="text-sm text-slate-500 dark:text-slate-400">
              This password-reset link is invalid or has already been used.
            </p>
            <Link
              to="/forgot-password"
              className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-violet-600 dark:text-violet-400 hover:underline"
            >
              Request a new link
            </Link>
          </div>
        ) : (
          /* Reset form */
          <form onSubmit={onSubmit} className="space-y-5" aria-label="Reset password form" noValidate>
            <div className="space-y-1">
              <h1 className="text-2xl font-bold text-slate-800 dark:text-white font-heading">
                Set new password
              </h1>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                Choose a strong password of at least 8 characters.
              </p>
            </div>

            {error && (
              <div
                role="alert"
                aria-live="assertive"
                className="rounded-lg bg-rose-50 dark:bg-rose-900/20 border border-rose-200 dark:border-rose-800 px-4 py-2.5 text-xs text-rose-700 dark:text-rose-300"
              >
                {error}
              </div>
            )}

            {/* New password */}
            <div className="space-y-1">
              <div className="relative">
                <Input
                  id="new-password"
                  label="New password"
                  type={showPw ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  icon={<Lock size={14} className="text-slate-400" aria-hidden="true" />}
                  placeholder="Min. 8 characters"
                  required
                  autoComplete="new-password"
                  aria-required="true"
                  aria-describedby="pw-strength"
                  className="pr-10"
                />
                <button
                  type="button"
                  aria-label={showPw ? "Hide password" : "Show password"}
                  onClick={() => setShowPw((v) => !v)}
                  className="absolute right-3 top-[38px] text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors"
                >
                  {showPw ? <EyeOff size={15} aria-hidden="true" /> : <Eye size={15} aria-hidden="true" />}
                </button>
              </div>
              {password.length > 0 && (
                <div id="pw-strength" aria-live="polite" className="space-y-1">
                  <div className="flex gap-1 h-1.5">
                    {[1, 2, 3, 4].map((i) => (
                      <div
                        key={i}
                        className={`flex-1 rounded-full transition-colors duration-300 ${
                          strength.score >= i ? strength.color : "bg-slate-200 dark:bg-slate-700"
                        }`}
                      />
                    ))}
                  </div>
                  <p className="text-[10px] text-slate-400">
                    Strength: <span className="font-semibold">{strength.label}</span>
                  </p>
                </div>
              )}
            </div>

            {/* Confirm password */}
            <div className="relative">
              <Input
                id="confirm-password"
                label="Confirm new password"
                type={showConfirm ? "text" : "password"}
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                icon={<Lock size={14} className="text-slate-400" aria-hidden="true" />}
                placeholder="Re-enter new password"
                required
                autoComplete="new-password"
                aria-required="true"
                error={mismatch ? "Passwords do not match" : undefined}
                className="pr-10"
              />
              <button
                type="button"
                aria-label={showConfirm ? "Hide confirm password" : "Show confirm password"}
                onClick={() => setShowConfirm((v) => !v)}
                className="absolute right-3 top-[38px] text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 transition-colors"
              >
                {showConfirm ? <EyeOff size={15} aria-hidden="true" /> : <Eye size={15} aria-hidden="true" />}
              </button>
            </div>

            <Button
              type="submit"
              loading={loading}
              className="w-full"
              size="md"
              disabled={mismatch || strength.score === 0}
              aria-busy={loading}
            >
              Reset password
            </Button>

            <div className="text-center">
              <Link
                to="/login"
                className="inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-violet-600 dark:hover:text-violet-400 font-medium transition-colors"
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
