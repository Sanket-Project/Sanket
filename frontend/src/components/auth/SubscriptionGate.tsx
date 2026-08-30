import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useLocation } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Lock, Sparkles, Clock, Shield } from "@/components/ui/icons";
import toast from "react-hot-toast";
import { billingApi } from "@/api/billing";
import { useAuthStore } from "@/stores/auth";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { LogoMark } from "@/components/ui/Logo";
import { getErrorMessage } from "@/utils/errors";
import { openRazorpayCheckout } from "@/utils/razorpay";

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
  // Payment succeeded at Razorpay but activation failed on our side. Sticky,
  // because the user needs a route to support rather than a transient toast.
  const [verifyFailed, setVerifyFailed] = useState(false);
  // Covers the Razorpay SDK <script> fetch as well as the API call, so the
  // button stays busy for the whole gap between click and modal.
  const [openingCheckout, setOpeningCheckout] = useState(false);

  const [showEnterpriseModal, setShowEnterpriseModal] = useState(false);
  const [contactName, setContactName] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [companySize, setCompanySize] = useState("");
  const [contactMessage, setContactMessage] = useState("");

  // 1. Fetch subscription status
  const { data: sub, isLoading: isSubLoading } = useQuery({
    queryKey: ["billing", "subscription"],
    queryFn: billingApi.getSubscription,
    staleTime: 60_000,
  });

  const { data: config } = useQuery({
    queryKey: ["billing", "config"],
    queryFn: billingApi.getConfig,
  });

  const verify = useMutation({
    mutationFn: (body: {
      razorpay_subscription_id: string;
      razorpay_payment_id: string;
      razorpay_signature: string;
    }) => billingApi.verifySubscription(body),
    onSuccess: () => {
      setVerifyFailed(false);
      toast.success("Payment verified! Subscription activated.");
      qc.invalidateQueries({ queryKey: ["billing"] });
    },
    onError: (e: unknown) => {
      // The customer may well have been charged — Razorpay redirected them
      // back, so a payment exists. A red toast that disappears in four seconds
      // is not an acceptable end state for "we took your money and your
      // workspace is still locked". Persist a recovery banner instead.
      setVerifyFailed(true);
      toast.error(getErrorMessage(e, "Payment verification failed"));
    },
  });

  // Handle redirect back from Razorpay hosted page
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const paymentId = params.get("razorpay_payment_id");
    const subId = params.get("razorpay_subscription_id");
    const sig = params.get("razorpay_signature");

    if (paymentId && subId && sig) {
      // Strip the payment id and signature from the URL *before* doing
      // anything else. They previously survived until the verify mutation
      // succeeded, which left them in browser history, in the Referer header
      // of every subresource this page loads, and in any analytics or CDN log
      // that records the full URL. On a verification failure they stayed
      // there permanently.
      window.history.replaceState({}, document.title, window.location.pathname);

      verify.mutate({
        razorpay_payment_id: paymentId,
        razorpay_subscription_id: subId,
        razorpay_signature: sig,
      });
    }
  }, []);

  // 2. Subscribe mutation
  const subscribe = useMutation({
    mutationFn: (body: { plan_id: string; billing_email: string; return_path?: string }) =>
      billingApi.startSubscription(body),
    onSuccess: async (r) => {
      qc.invalidateQueries({ queryKey: ["billing"] });
      setSelectedPlan(null);

      // A trial needs no payment — the server has already granted it.
      if (r.status === "trialing") {
        toast.success("Your 14-day free trial is active. Welcome aboard!");
        return;
      }

      // Try opening Razorpay JS SDK Checkout Popup if key is configured
      if (config?.configured && config.key_id && r.razorpay_subscription_id) {
        setOpeningCheckout(true);
        try {
          const opened = await openRazorpayCheckout({
            keyId: config.key_id,
            subscriptionId: r.razorpay_subscription_id,
            planName: selectedPlan?.id.replace(/_/g, " ").toUpperCase() || "Subscription",
            billingEmail,
            onSuccess: (res) => {
              verify.mutate(res);
            },
            onDismiss: () => {
              toast("Payment cancelled — your workspace is still locked.", { icon: "🔒" });
            },
          });
          if (opened) return;
        } finally {
          setOpeningCheckout(false);
        }
      }

      // Fallback to Razorpay Hosted Page redirect
      if (r.short_url) {
        if (!isSafeRedirectUrl(r.short_url)) {
          toast.error("Payment redirect URL failed validation — contact support");
          console.warn("Blocked unsafe billing redirect:", r.short_url);
          return;
        }
        toast.success("Redirecting to payment gateway…");
        window.location.href = r.short_url;
        return;
      }

      // No checkout modal and no hosted page: we could not collect payment.
      // This previously reported success, which is how an unpaid subscription
      // came to look like a completed purchase.
      console.error("No payment route available for subscription", r.id, "status:", r.status);
      toast.error(
        "We couldn't open the payment page. Your subscription is not active — please retry or contact support.",
      );
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
        // Path only — the server owns the origin. See api/billing.ts.
        return_path: window.location.pathname,
      });
    }
  };

  const handleEnterpriseSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!contactName || !companyName || !companySize || !contactMessage) {
      toast.error("Please fill in all required fields");
      return;
    }
    
    const emailTo = "enterprise@sanket-supply.com";
    const subject = encodeURIComponent(`Enterprise Custom Plan Enquiry - ${companyName}`);
    const bodyText = `Hello SANKET Enterprise Sales Team,

I would like to enquire about the Enterprise Custom plan for our workspace.

Here are our details:
- Contact Name: ${contactName}
- Work Email: ${userEmail || "Not provided"}
- Company Name: ${companyName}
- Expected SKUs: ${companySize}

Forecasting & Inventory Requirements:
${contactMessage}

Best regards,
${contactName}`;

    const body = encodeURIComponent(bodyText);
    const mailtoUrl = `mailto:${emailTo}?subject=${subject}&body=${body}`;

    window.location.href = mailtoUrl;

    toast.success("Opening email client to send your enquiry!");
    setShowEnterpriseModal(false);
    
    setContactName("");
    setCompanyName("");
    setCompanySize("");
    setContactMessage("");
  };

  const hasTrialHistory = !!sub;

  const overlayContent = (
    <div className="absolute inset-0 z-[15] flex items-start justify-center bg-slate-950/70 dark:bg-slate-950/85 backdrop-blur-xl overflow-y-auto p-4 md:p-6 lg:pl-[calc(var(--sidebar-w)+24px)] lg:pt-[84px] lg:pr-[20px] lg:pb-[28px] select-none no-scrollbar">
      <style>{`
        .no-scrollbar::-webkit-scrollbar {
          display: none !important;
        }
        .no-scrollbar {
          -ms-overflow-style: none !important;
          scrollbar-width: none !important;
        }
      `}</style>
      <div className="w-full max-w-5xl rounded-3xl border border-line bg-surface shadow-2xl p-5 md:p-6 flex flex-col items-center justify-center text-center animate-fade-in my-auto">

        {/* Brand + Lock icon header */}
        <div className="flex items-center gap-2.5 mb-3">
          <LogoMark size={32} variant="tile" className="rounded-xl shadow-md" />
          <span className="text-lg font-bold tracking-tight text-content font-heading">SANKET</span>
          <span className="inline-flex h-8 w-8 items-center justify-center rounded-xl bg-amber-500/10 text-amber-500 ml-1">
            <Lock size={16} />
          </span>
        </div>

        <h1 className="text-2xl md:text-[1.7rem] font-extrabold tracking-tight text-content font-heading leading-tight">
          Activate Your SANKET Workspace
        </h1>
        <p className="text-sm text-content-muted mt-1.5 max-w-xl leading-relaxed">
          Predictive forecasting, signal tracking, and inventory optimization require an active subscription. Choose a plan to unlock access.
        </p>

        {/* Warning alerts */}
        {verifyFailed ? (
          <div
            role="alert"
            className="mt-4 w-full max-w-2xl bg-rose-500/10 border border-rose-500/30 text-rose-500 text-xs rounded-xl p-3 text-left"
          >
            <strong>Payment received, activation pending.</strong> We could not confirm your
            payment automatically. If you were charged, do not pay again — your workspace will
            unlock once we reconcile it, usually within a few minutes. Still locked after that?
            Contact{" "}
            <a className="underline font-semibold" href="mailto:billing@sanket-supply.com">
              billing@sanket-supply.com
            </a>{" "}
            and quote your registered email.
          </div>
        ) : null}

        {isTrialExpired ? (
          <div className="mt-4 w-full max-w-2xl bg-amber-500/10 border border-amber-500/30 text-amber-500 text-xs rounded-xl p-3 text-center">
            <strong>Your 14-day free trial has expired.</strong> Please complete a monthly or yearly payment below to restore access to the software.
          </div>
        ) : sub && !hasAccess ? (
          <div className="mt-4 w-full max-w-2xl bg-rose-500/10 border border-rose-500/30 text-rose-500 text-xs rounded-xl p-3 text-center">
            <strong>Access Blocked:</strong> An active subscription is required to access the workspace. Please select a plan below to complete payment.
          </div>
        ) : null}

        {/* Billing Cycle Toggle */}
        <div className="flex justify-center items-center gap-3 mt-3 mb-2">
          <span className={`text-xs font-semibold ${billingCycle === "monthly" ? "text-content" : "text-content-muted"}`}>
            Bill Monthly
          </span>
          <button
            onClick={() => setBillingCycle(c => c === "monthly" ? "yearly" : "monthly")}
            role="switch"
            aria-checked={billingCycle === "yearly"}
            aria-label="Toggle yearly billing"
            className={`relative w-12 h-6 rounded-full transition-colors duration-200 focus:outline-none focus-visible:ring-2 focus-visible:ring-accent/40 ${
              billingCycle === "yearly" ? "bg-emerald-500" : "bg-slate-300 dark:bg-slate-600"
            }`}
          >
            <span
              className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow-md transition-transform duration-200 ${
                billingCycle === "yearly" ? "translate-x-6" : ""
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
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 w-full mt-4 text-left">
          
          {/* Option 1: 14-day Free Trial */}
          {/* `pointer-events-none` hid this card's used-trial state from
              keyboard and screen-reader users: the button stayed in the tab
              order but could not be reached or announced as unavailable.
              `aria-disabled` on the container plus the already-`disabled`
              button communicates it to everyone. */}
          <div
            aria-disabled={hasTrialHistory || undefined}
            className={`p-4 rounded-2xl border border-line bg-surface-2 flex flex-col justify-between hover:border-accent/30 hover:bg-surface-2 transition duration-200 ${hasTrialHistory ? "opacity-60" : ""}`}
          >
            <div>
              <div className="flex items-center gap-1.5 text-xs text-accent font-bold uppercase tracking-wider">
                <Clock size={12} />
                <span>Trial</span>
              </div>
              <h3 className="text-lg font-bold text-content mt-1 leading-tight">14-Day Free Trial</h3>
              <p className="text-xs text-content-subtle mt-1.5 leading-relaxed line-clamp-2 min-h-[2rem]">
                Test-drive growth forecasting tools free for 14 days. Cancel anytime.
              </p>
              <div className="mt-2.5 flex items-baseline gap-1 text-content">
                <span className="text-2xl font-extrabold">Free</span>
                <span className="text-xs text-content-muted">then ₹4,995/mo</span>
              </div>
              <ul className="mt-2.5 space-y-1.5 text-[11px] text-content-muted font-medium">
                <li className="flex items-center gap-1.5"><Check size={12} className="text-emerald-500" /> 10,000 SKUs</li>
                <li className="flex items-center gap-1.5"><Check size={12} className="text-emerald-500" /> 5 User Seats</li>
              </ul>
            </div>
            <Button
              className="w-full mt-4"
              variant={hasTrialHistory ? "secondary" : "primary"}
              disabled={hasTrialHistory}
              onClick={() => handleSelectPlan("growth_monthly", 14)}
            >
              {hasTrialHistory ? "Trial Already Used" : "Start Free Trial"}
            </Button>
          </div>

          {/* Option 2: Growth Plan */}
          <div className="p-4 rounded-2xl border border-line bg-surface-2 flex flex-col justify-between hover:border-accent/30 hover:bg-surface-2 transition duration-200">
            <div>
              <div className="flex items-center gap-1.5 text-xs text-accent font-bold uppercase tracking-wider">
                <Sparkles size={12} />
                <span>Growth</span>
              </div>
              <h3 className="text-lg font-bold text-content mt-1 leading-tight">
                {billingCycle === "monthly" ? "Growth Monthly" : "Growth Yearly"}
              </h3>
              <p className="text-xs text-content-subtle mt-1.5 leading-relaxed line-clamp-2 min-h-[2rem]">
                Unlock core predictive analytics immediately with standard billing.
              </p>
              <div className="mt-2.5">
                <div className="flex items-baseline gap-1 text-content">
                  <span className="text-2xl font-extrabold">
                    {billingCycle === "monthly" ? "₹4,995" : "₹49,950"}
                  </span>
                  <span className="text-xs text-content-muted">
                    {billingCycle === "monthly" ? "/month" : "/year"}
                  </span>
                </div>
                {billingCycle === "yearly" && (
                  <div className="text-[11px] text-emerald-600 dark:text-emerald-400 font-semibold mt-1">
                    (₹4,162/mo value)
                  </div>
                )}
              </div>
              <ul className="mt-2.5 space-y-1.5 text-[11px] text-content-muted font-medium">
                <li className="flex items-center gap-1.5"><Check size={12} className="text-emerald-500" /> 10,000 SKUs</li>
                <li className="flex items-center gap-1.5"><Check size={12} className="text-emerald-500" /> 5 User Seats</li>
              </ul>
            </div>
            <Button
              className="w-full mt-4"
              variant="secondary"
              onClick={() => handleSelectPlan(billingCycle === "monthly" ? "growth_monthly" : "growth_yearly", 0)}
            >
              Select Growth
            </Button>
          </div>

          {/* Option 3: Scale Plan */}
          <div className="p-4 rounded-2xl border-2 border-accent bg-accent/5 ring-4 ring-accent/5 flex flex-col justify-between hover:bg-accent/10 transition duration-200 relative">
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
              <p className="text-xs text-content-subtle mt-1.5 leading-relaxed line-clamp-2 min-h-[2rem]">
                Advanced models for scaling enterprise operations.
              </p>
              <div className="mt-2.5">
                <div className="flex items-baseline gap-1 text-content">
                  <span className="text-2xl font-extrabold">
                    {billingCycle === "monthly" ? "₹14,995" : "₹149,950"}
                  </span>
                  <span className="text-xs text-content-muted">
                    {billingCycle === "monthly" ? "/month" : "/year"}
                  </span>
                </div>
                {billingCycle === "yearly" && (
                  <div className="text-[11px] text-emerald-600 dark:text-emerald-400 font-semibold mt-1">
                    (₹12,495/mo value)
                  </div>
                )}
              </div>
              <ul className="mt-2.5 space-y-1.5 text-[11px] text-content-muted font-medium">
                <li className="flex items-center gap-1.5"><Check size={12} className="text-emerald-500" /> 100,000 SKUs</li>
                <li className="flex items-center gap-1.5"><Check size={12} className="text-emerald-500" /> 25 User Seats</li>
              </ul>
            </div>
            <Button
              className="w-full mt-4"
              variant="primary"
              onClick={() => handleSelectPlan(billingCycle === "monthly" ? "scale_monthly" : "scale_yearly", 0)}
            >
              Select Scale
            </Button>
          </div>

          {/* Option 4: Enterprise */}
          <div className="p-4 rounded-2xl border border-line bg-surface-2 flex flex-col justify-between hover:border-accent/30 hover:bg-surface-2 transition duration-200">
            <div>
              <div className="flex items-center gap-1.5 text-xs text-emerald-600 dark:text-emerald-400 font-bold uppercase tracking-wider">
                <Shield size={12} />
                <span>Enterprise</span>
              </div>
              <h3 className="text-lg font-bold text-content mt-1 leading-tight">Enterprise Custom</h3>
              <p className="text-xs text-content-subtle mt-1.5 leading-relaxed line-clamp-2 min-h-[2rem]">
                SLA guarantees, SSO, dedicated infrastructure, and GxP compliance.
              </p>
              <div className="mt-2.5 flex items-baseline gap-1 text-content">
                <span className="text-2xl font-extrabold">Custom</span>
                <span className="text-xs text-content-muted">pricing</span>
              </div>
              <ul className="mt-2.5 space-y-1.5 text-[11px] text-content-muted font-medium">
                <li className="flex items-center gap-1.5"><Check size={12} className="text-emerald-500" /> Unlimited SKUs</li>
                <li className="flex items-center gap-1.5"><Check size={12} className="text-emerald-500" /> GxP Compliance</li>
              </ul>
            </div>
            <button
              type="button"
              onClick={() => setShowEnterpriseModal(true)}
              className="w-full mt-4 inline-flex items-center justify-center px-4 py-2.5 rounded-xl bg-surface border border-line-strong hover:bg-surface-2 text-content text-xs font-semibold transition-colors shadow-sm text-center cursor-pointer"
            >
              Contact Sales
            </button>
          </div>

        </div>

        {/* Footer/Logout button */}
        <div className="mt-4 pt-3 border-t border-line w-full flex items-center justify-between">
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
                  loading={subscribe.isPending || openingCheckout}
                >
                  Proceed to Payment
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Enterprise Contact Modal */}
      {showEnterpriseModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 backdrop-blur-sm p-4">
          <div className="w-full max-w-md rounded-2xl border border-line bg-surface p-6 shadow-xl animate-scale-in text-left">
            <h2 className="text-lg font-bold text-content font-heading flex items-center gap-2">
              <Shield className="text-emerald-500" size={20} />
              Contact Enterprise Sales
            </h2>
            <form onSubmit={handleEnterpriseSubmit} className="mt-4 space-y-4">
              <p className="text-xs text-content-muted leading-relaxed">
                Enter your company details below. Submitting will prepare an email draft to our Enterprise team.
              </p>
              
              <Input
                label="Full Name"
                type="text"
                placeholder="John Doe"
                value={contactName}
                onChange={(e) => setContactName(e.target.value)}
                required
              />

              <Input
                label="Company Name"
                type="text"
                placeholder="Acme Corp"
                value={companyName}
                onChange={(e) => setCompanyName(e.target.value)}
                required
              />

              <div className="flex flex-col gap-1">
                <label className="label">Expected SKUs</label>
                <select
                  value={companySize}
                  onChange={(e) => setCompanySize(e.target.value)}
                  required
                  className="w-full rounded-xl px-3.5 py-2.5 text-sm outline-none transition-all duration-150 border border-line bg-surface text-content focus:border-accent focus:ring-2 focus:ring-accent-ring"
                >
                  <option value="" disabled>Select expected SKUs...</option>
                  <option value="100k-500k">100,000 - 500,000 SKUs</option>
                  <option value="500k-1m">500,000 - 1,000,000 SKUs</option>
                  <option value="1m+">Over 1,000,000 SKUs</option>
                </select>
              </div>

              <div className="flex flex-col gap-1">
                <label className="label">Message / Requirements</label>
                <textarea
                  placeholder="Tell us about your inventory and forecasting needs..."
                  value={contactMessage}
                  onChange={(e) => setContactMessage(e.target.value)}
                  className="w-full rounded-xl px-3.5 py-2.5 text-sm outline-none transition-all duration-150 border border-line bg-surface text-content focus:border-accent focus:ring-2 focus:ring-accent-ring min-h-[80px] resize-y"
                  required
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <Button
                  type="button"
                  variant="secondary"
                  onClick={() => setShowEnterpriseModal(false)}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  variant="primary"
                >
                  Contact Sales
                </Button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );

  const appShellRoot = document.getElementById("app-shell-root");
  return appShellRoot ? createPortal(overlayContent, appShellRoot) : overlayContent;
};
