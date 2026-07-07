import { useState } from "react";
import { useLocation } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Lock, Sparkles, Clock, Shield } from "lucide-react";
import toast from "react-hot-toast";
import { billingApi } from "@/api/billing";
import { useAuthStore } from "@/stores/auth";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { getErrorMessage } from "@/utils/errors";

const ALLOWED_REDIRECT_HOSTS = [
  "rzp.io",
  "razorpay.com",
  "api.razorpay.com",
  "checkout.razorpay.com",
];

function isSafeRedirectUrl(url: string): boolean {
  try {
    const parsed = new URL(url);
    return (
      (parsed.protocol === "https:" || parsed.protocol === "http:") &&
      ALLOWED_REDIRECT_HOSTS.some(
        (host) => parsed.hostname === host || parsed.hostname.endsWith(`.${host}`)
      )
    );
  } catch {
    return false;
  }
}

export const SubscriptionGate = ({ children }: { children: React.ReactNode }) => {
  const location = useLocation();
  const { email: userEmail, logout } = useAuthStore();
  const qc = useQueryClient();
  const [billingEmail, setBillingEmail] = useState(userEmail || "");
  const [selectedPlan, setSelectedPlan] = useState<{ id: string; trial_days: number } | null>(null);
  const [billingCycle, setBillingCycle] = useState<"monthly" | "yearly">("monthly");

  // 1. Fetch subscription status
  const { data: sub, isLoading: isSubLoading } = useQuery({
    queryKey: ["billing", "subscription"],
    queryFn: billingApi.getSubscription,
    // Refetch less aggressively during gate blocking
    staleTime: 60_000,
  });

  // 2. Subscribe mutation
  const subscribe = useMutation({
    mutationFn: (body: { plan_id: string; billing_email: string; trial_days: number }) =>
      billingApi.startSubscription(body),
    onSuccess: (r) => {
      qc.invalidateQueries({ queryKey: ["billing"] });
      setSelectedPlan(null);
      if (r.short_url) {
        if (!isSafeRedirectUrl(r.short_url)) {
          toast.error("Payment redirect URL failed validation — contact support");
          console.warn("Blocked unsafe billing redirect:", r.short_url);
          return;
        }
        toast.success("Redirecting to payment gateway…");
        window.location.href = r.short_url;
      } else {
        toast.success("Subscription activated successfully!");
      }
    },
    onError: (e: unknown) => {
      toast.error(getErrorMessage(e, "Failed to start subscription"));
    },
  });

  // Bypass on billing page so the user can manage subscriptions
  if (location.pathname === "/workspace/billing") {
    return <>{children}</>;
  }

  // Loading state
  if (isSubLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-canvas">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-line border-t-[var(--accent)]" />
      </div>
    );
  }

  const now = new Date();
  const isTrialActive = sub && sub.status === "trialing" && new Date(sub.current_period_end) > now;
  const isTrialExpired = sub && sub.status === "trialing" && new Date(sub.current_period_end) <= now;

  // Check if active subscription exists and is not expired
  const hasAccess = sub && (sub.status === "active" || isTrialActive);

  if (hasAccess) {
    return <>{children}</>;
  }

  // Otherwise, show the blocking SubscriptionGate overlay
  const handleSelectPlan = (planId: string, trialDays: number) => {
    setSelectedPlan({ id: planId, trial_days: trialDays });
  };

  const handleConfirmSubscription = (e: React.FormEvent) => {
    e.preventDefault();
    if (!billingEmail) {
      toast.error("Please enter a valid billing email");
      return;
    }
    if (selectedPlan) {
      subscribe.mutate({
        plan_id: selectedPlan.id,
        billing_email: billingEmail,
        trial_days: selectedPlan.trial_days,
      });
    }
  };

  const hasTrialHistory = !!sub;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-slate-950/20 dark:bg-slate-950/70 backdrop-blur-md overflow-y-auto p-4 md:p-10 select-none no-scrollbar">
      <style>{`
        .no-scrollbar::-webkit-scrollbar {
          display: none !important;
        }
        .no-scrollbar {
          -ms-overflow-style: none !important;
          scrollbar-width: none !important;
        }
      `}</style>
      <div className="w-full max-w-5xl rounded-3xl border border-line bg-surface shadow-2xl p-6 md:p-10 flex flex-col items-center justify-center text-center animate-fade-in my-auto">
        
        {/* Brand/Lock icon header */}
        <div className="flex items-center gap-2 mb-4">
          <div className="inline-flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-accent shadow-lg shadow-accent-primary/20 text-white font-bold text-lg font-heading">
            P
          </div>
          <span className="text-xl font-bold tracking-tight text-content font-heading">SANKET</span>
        </div>

        <div className="inline-flex h-12 w-12 items-center justify-center rounded-2xl bg-amber-500/10 text-amber-500 mb-4 animate-pulse">
          <Lock size={22} />
        </div>

        <h1 className="text-2xl md:text-3xl font-extrabold tracking-tight text-content font-heading leading-tight">
          Activate Your SANKET Workspace
        </h1>
        <p className="text-sm text-content-muted mt-2 max-w-xl leading-relaxed">
          Predictive demand forecasting, social signal tracking, and inventory optimization vertical modules require an active subscription profile. Choose a plan to unlock your access.
        </p>

        {/* Warning alerts */}
        {isTrialExpired ? (
          <div className="mt-6 w-full max-w-2xl bg-amber-500/10 border border-amber-500/30 text-amber-500 text-xs rounded-xl p-3 text-center">
            <strong>Your 14-day free trial has expired.</strong> Please complete a monthly or yearly payment below to restore access to the software.
          </div>
        ) : sub && !hasAccess ? (
          <div className="mt-6 w-full max-w-2xl bg-rose-500/10 border border-rose-500/30 text-rose-500 text-xs rounded-xl p-3 text-center">
            <strong>Access Blocked:</strong> An active subscription is required to access the workspace. Please select a plan below to complete payment.
          </div>
        ) : null}

        {/* Billing Cycle Toggle */}
        <div className="flex justify-center items-center gap-3 mt-6 mb-2">
          <span className={`text-xs font-semibold ${billingCycle === "monthly" ? "text-content" : "text-content-muted"}`}>
            Bill Monthly
          </span>
          <button
            onClick={() => setBillingCycle(c => c === "monthly" ? "yearly" : "monthly")}
            className="relative w-11 h-6 bg-slate-800 dark:bg-slate-700 rounded-full transition-colors duration-200 focus:outline-none ring-2 ring-accent/20"
          >
            <span
              className={`absolute top-0.5 left-0.5 bg-accent w-5 h-5 rounded-full transition-transform duration-200 transform ${
                billingCycle === "yearly" ? "translate-x-5" : ""
              }`}
            />
          </button>
          <span className={`text-xs font-semibold flex items-center gap-1.5 ${billingCycle === "yearly" ? "text-content" : "text-content-muted"}`}>
            Bill Yearly
            <span className="bg-emerald-500/25 text-emerald-500 dark:text-emerald-400 text-[10px] font-bold px-1.5 py-0.5 rounded-full animate-bounce">
              Save 16%
            </span>
          </span>
        </div>

        {/* Pricing Cards Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 w-full mt-8 text-left">
          
          {/* Option 1: 14-day Free Trial */}
          <div className={`p-5 rounded-2xl border border-line bg-surface-2 flex flex-col justify-between hover:border-accent/30 hover:bg-surface-2 transition duration-200 ${hasTrialHistory ? "opacity-60 pointer-events-none select-none" : ""}`}>
            <div>
              <div className="flex items-center gap-1.5 text-xs text-accent font-bold uppercase tracking-wider">
                <Clock size={12} />
                <span>Trial</span>
              </div>
              <h3 className="text-lg font-bold text-content mt-1 leading-tight">14-Day Free Trial</h3>
              <p className="text-xs text-content-subtle mt-1.5 leading-relaxed">
                Test-drive growth forecasting tools free for 14 days. Cancel anytime.
              </p>
              <div className="mt-4 flex items-baseline gap-1 text-content">
                <span className="text-2xl font-extrabold">Free</span>
                <span className="text-xs text-content-muted">then ₹4,995/mo</span>
              </div>
              <ul className="mt-4 space-y-1.5 text-[11px] text-content-muted font-medium">
                <li className="flex items-center gap-1.5"><Check size={12} className="text-emerald-500" /> 10,000 SKUs</li>
                <li className="flex items-center gap-1.5"><Check size={12} className="text-emerald-500" /> 5 User Seats</li>
              </ul>
            </div>
            <Button
              className="w-full mt-6"
              variant={hasTrialHistory ? "secondary" : "primary"}
              disabled={hasTrialHistory}
              onClick={() => handleSelectPlan("growth_monthly", 14)}
            >
              {hasTrialHistory ? "Trial Already Used" : "Start Free Trial"}
            </Button>
          </div>

          {/* Option 2: Growth Plan */}
          <div className="p-5 rounded-2xl border border-line bg-surface-2 flex flex-col justify-between hover:border-accent/30 hover:bg-surface-2 transition duration-200">
            <div>
              <div className="flex items-center gap-1.5 text-xs text-accent font-bold uppercase tracking-wider">
                <Sparkles size={12} />
                <span>Growth</span>
              </div>
              <h3 className="text-lg font-bold text-content mt-1 leading-tight">
                {billingCycle === "monthly" ? "Growth Monthly" : "Growth Yearly"}
              </h3>
              <p className="text-xs text-content-subtle mt-1.5 leading-relaxed">
                Unlock core predictive analytics immediately with standard billing.
              </p>
              <div className="mt-4 flex items-baseline gap-1 text-content">
                <span className="text-2xl font-extrabold">
                  {billingCycle === "monthly" ? "₹4,995" : "₹49,950"}
                </span>
                <span className="text-xs text-content-muted">
                  {billingCycle === "monthly" ? "/month" : "/year"}
                </span>
                {billingCycle === "yearly" && (
                  <span className="text-[10px] text-emerald-500 font-semibold ml-1">
                    (₹4,162/mo value)
                  </span>
                )}
              </div>
              <ul className="mt-4 space-y-1.5 text-[11px] text-content-muted font-medium">
                <li className="flex items-center gap-1.5"><Check size={12} className="text-emerald-500" /> 10,000 SKUs</li>
                <li className="flex items-center gap-1.5"><Check size={12} className="text-emerald-500" /> 5 User Seats</li>
              </ul>
            </div>
            <Button
              className="w-full mt-6"
              variant="secondary"
              onClick={() => handleSelectPlan(billingCycle === "monthly" ? "growth_monthly" : "growth_yearly", 0)}
            >
              Select Growth
            </Button>
          </div>

          {/* Option 3: Scale Plan */}
          <div className="p-5 rounded-2xl border-2 border-accent bg-accent/5 ring-4 ring-accent/5 flex flex-col justify-between hover:bg-accent/10 transition duration-200 relative">
            <span className="absolute -top-2.5 right-4 bg-accent text-accent-fg text-[9px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full shadow-sm">
              Popular
            </span>
            <div>
              <div className="flex items-center gap-1.5 text-xs text-accent font-bold uppercase tracking-wider">
                <Sparkles size={12} />
                <span>Scale</span>
              </div>
              <h3 className="text-lg font-bold text-content mt-1 leading-tight">
                {billingCycle === "monthly" ? "Scale Monthly" : "Scale Yearly"}
              </h3>
              <p className="text-xs text-content-subtle mt-1.5 leading-relaxed">
                Advanced models for scaling enterprise operations.
              </p>
              <div className="mt-4 flex items-baseline gap-1 text-content">
                <span className="text-2xl font-extrabold">
                  {billingCycle === "monthly" ? "₹14,995" : "₹149,950"}
                </span>
                <span className="text-xs text-content-muted">
                  {billingCycle === "monthly" ? "/month" : "/year"}
                </span>
                {billingCycle === "yearly" && (
                  <span className="text-[10px] text-emerald-500 font-semibold ml-1">
                    (₹12,495/mo value)
                  </span>
                )}
              </div>
              <ul className="mt-4 space-y-1.5 text-[11px] text-content-muted font-medium">
                <li className="flex items-center gap-1.5"><Check size={12} className="text-emerald-500" /> 100,000 SKUs</li>
                <li className="flex items-center gap-1.5"><Check size={12} className="text-emerald-500" /> 25 User Seats</li>
              </ul>
            </div>
            <Button
              className="w-full mt-6"
              variant="primary"
              onClick={() => handleSelectPlan(billingCycle === "monthly" ? "scale_monthly" : "scale_yearly", 0)}
            >
              Select Scale
            </Button>
          </div>

          {/* Option 4: Enterprise */}
          <div className="p-5 rounded-2xl border border-line bg-surface-2 flex flex-col justify-between hover:border-accent/30 hover:bg-surface-2 transition duration-200">
            <div>
              <div className="flex items-center gap-1.5 text-xs text-emerald-600 dark:text-emerald-400 font-bold uppercase tracking-wider">
                <Shield size={12} />
                <span>Enterprise</span>
              </div>
              <h3 className="text-lg font-bold text-content mt-1 leading-tight">Enterprise Custom</h3>
              <p className="text-xs text-content-subtle mt-1.5 leading-relaxed">
                SLA guarantees, SSO, dedicated infrastructure, and GxP compliance.
              </p>
              <div className="mt-4 flex items-baseline gap-1 text-content">
                <span className="text-2xl font-extrabold">Custom</span>
                <span className="text-xs text-content-muted">pricing</span>
              </div>
              <ul className="mt-4 space-y-1.5 text-[11px] text-content-muted font-medium">
                <li className="flex items-center gap-1.5"><Check size={12} className="text-emerald-500" /> Unlimited SKUs</li>
                <li className="flex items-center gap-1.5"><Check size={12} className="text-emerald-500" /> GxP Compliance</li>
              </ul>
            </div>
            <a
              href="mailto:enterprise@sanket-supply.com?subject=Enterprise%20Enquiry"
              className="w-full mt-6 inline-flex items-center justify-center px-4 py-2.5 rounded-xl bg-surface border border-line-strong hover:bg-surface-2 text-content text-xs font-semibold transition-colors shadow-sm text-center"
            >
              Contact Sales
            </a>
          </div>

        </div>

        {/* Footer/Logout button */}
        <div className="mt-8 pt-6 border-t border-line w-full flex items-center justify-between">
          <p className="text-[11px] text-content-subtle">
            Logged in as <span className="font-semibold text-content-muted">{userEmail}</span>. Not your account?
          </p>
          <button
            onClick={() => logout()}
            className="text-xs font-semibold uppercase tracking-wider text-rose-600 dark:text-rose-400 hover:underline cursor-pointer"
          >
            Sign Out
          </button>
        </div>

      </div>

      {/* Confirmation Modal */}
      {selectedPlan && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-2xl border border-line bg-surface p-6 shadow-xl animate-scale-in text-left">
            <h2 className="text-lg font-bold text-content font-heading">
              Confirm Subscription Setup
            </h2>
            <form onSubmit={handleConfirmSubscription} className="mt-4 space-y-4">
              <p className="text-xs text-content-muted leading-relaxed">
                Confirm your billing email to proceed. You will be redirected to our secure payment gateway to complete authorization.
              </p>
              <Input
                label="Billing Email"
                type="email"
                placeholder="you@company.com"
                value={billingEmail}
                onChange={(e) => setBillingEmail(e.target.value)}
                required
              />
              <div className="flex justify-end gap-2 pt-2">
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => setSelectedPlan(null)}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  variant="primary"
                  loading={subscribe.isPending}
                >
                  Proceed to Payment
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
