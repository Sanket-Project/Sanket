import { PageHeader } from "@/components/ui/PageHeader";
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CreditCard, Check } from "@/components/ui/icons";
import toast from "react-hot-toast";
import { billingApi, type Plan } from "@/api/billing";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { PageLoader } from "@/components/ui/Spinner";
import { fmtNumber } from "@/utils/format";
import { getErrorMessage, isServerError } from "@/utils/errors";
import { openRazorpayCheckout } from "@/utils/razorpay";
import { RazorpayCheckoutButton } from "@/components/billing/RazorpayCheckoutButton";

/** Validate that a redirect URL comes from a trusted payment provider domain. */
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

// Billing is always shown in INR — Razorpay charges the fixed INR plan amount
// configured in the dashboard, independent of the app's USD/INR display toggle.
const inrFmt = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  maximumFractionDigits: 0,
});

export const BillingPage = () => {
  const cents = (n: number) => inrFmt.format(n / 100);
  const qc = useQueryClient();
  const [pickPlan, setPickPlan] = useState<Plan | null>(null);
  const [email, setEmail] = useState("");
  const [showCancelConfirm, setShowCancelConfirm] = useState(false);
  // Payment taken but activation failed — needs a persistent recovery path.
  const [verifyFailed, setVerifyFailed] = useState(false);
  // Covers the Razorpay SDK script fetch, not just the API call, so the button
  // doesn't go idle during the dead air before the modal appears.
  const [openingCheckout, setOpeningCheckout] = useState(false);

  const { data: plans, isLoading: l1 } = useQuery({
    queryKey: ["billing", "plans"],
    queryFn: billingApi.listPlans,
  });
  const { data: sub, isLoading: l2 } = useQuery({
    queryKey: ["billing", "subscription"],
    queryFn: billingApi.getSubscription,
  });
  const { data: usage } = useQuery({
    queryKey: ["billing", "usage"],
    queryFn: billingApi.usage,
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
      // See SubscriptionGate: the customer may have been charged already, so
      // this needs a persistent recovery path, not a transient toast.
      setVerifyFailed(true);
      toast.error(getErrorMessage(e, "Payment verification failed"));
    },
  });
  // Stable across renders, so the return-from-checkout effect runs once.
  const verifyPayment = verify.mutate;

  // Handle redirect back from Razorpay hosted page
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const paymentId = params.get("razorpay_payment_id");
    const subId = params.get("razorpay_subscription_id");
    const sig = params.get("razorpay_signature");

    if (paymentId && subId && sig) {
      // Clear the signature from the URL immediately — before the mutation,
      // not after it succeeds. See SubscriptionGate for the full rationale.
      window.history.replaceState({}, document.title, window.location.pathname);

      verifyPayment({
        razorpay_payment_id: paymentId,
        razorpay_subscription_id: subId,
        razorpay_signature: sig,
      });
    }
  }, [verifyPayment]);

  const subscribe = useMutation({
    mutationFn: (body: { plan_id: string; billing_email: string }) =>
      billingApi.startSubscription(body),
    onSuccess: async (r) => {
      qc.invalidateQueries({ queryKey: ["billing"] });
      setPickPlan(null);

      // A trial needs no payment — the server has already granted it.
      if (r.status === "trialing") {
        toast.success("Your free trial is active. Welcome aboard!");
        return;
      }

      // Try opening Razorpay JS SDK Checkout Popup if key is configured
      if (config?.configured && config.key_id && r.razorpay_subscription_id) {
        setOpeningCheckout(true);
        try {
          const opened = await openRazorpayCheckout({
            keyId: config.key_id,
            subscriptionId: r.razorpay_subscription_id,
            planName: pickPlan?.display_name || "Subscription",
            billingEmail: email,
            onSuccess: (res) => {
              verify.mutate(res);
            },
            onDismiss: () => {
              toast("Payment cancelled — no charge was made.", { icon: "🔒" });
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
        toast.success("Redirecting to Razorpay to confirm payment…");
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
      if (!isServerError(e)) {
        toast.error(getErrorMessage(e, "Failed to start subscription"));
      }
    },
  });

  const cancel = useMutation({
    mutationFn: () => billingApi.cancel(true),
    onSuccess: () => {
      toast.success("Cancellation scheduled for period end");
      qc.invalidateQueries({ queryKey: ["billing"] });
      setShowCancelConfirm(false);
    },
  });

  const portal = useMutation({
    mutationFn: () => billingApi.portalSession(window.location.href),
    onSuccess: (r) => {
      // Validate the redirect URL is a known Razorpay domain before navigating
      if (!isSafeRedirectUrl(r.url)) {
        toast.error("Portal redirect URL failed validation — contact support");
        console.warn("Blocked unsafe portal redirect:", r.url);
        return;
      }
      window.location.href = r.url;
    },
  });

  if (l1 || l2) return <PageLoader />;

  const activePlanId = sub?.plan_id;

  return (
    <div className="space-y-6">
      <div className="animate-fade-in stagger-1">
        <PageHeader title="Billing" description={<> Manage your subscription, usage, and payment method. </>} />
      </div>

      {/* Payment went through at Razorpay but we could not activate. Sticky,
          because "you were charged and nothing happened" needs a route to a
          human, not a toast that vanishes. */}
      {verifyFailed && (
        <div
          role="alert"
          className="animate-fade-in rounded-xl border border-rose-500/30 bg-rose-500/10 p-4 text-sm text-rose-600 dark:text-rose-400"
        >
          <strong className="block mb-1">Payment received, activation pending.</strong>
          We couldn't confirm your payment automatically. If you were charged, please don't pay
          again — this usually reconciles within a few minutes. If your plan still shows as
          inactive after that, contact{" "}
          <a className="underline font-semibold" href="mailto:billing@sanket-supply.com">
            billing@sanket-supply.com
          </a>
          .
        </div>
      )}

      {/* Current subscription */}
      <Card title="Current subscription" className="animate-fade-in stagger-2">
        {sub ? (
          <div className="flex items-center justify-between flex-wrap gap-4">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xl font-semibold text-content">
                  {plans?.find((p) => p.id === sub.plan_id)?.display_name ?? sub.plan_id}
                </span>
                <Badge
                  variant={
                    sub.status === "active" || sub.status === "trialing"
                      ? "success"
                      : sub.status === "past_due"
                      ? "warning"
                      : "danger"
                  }
                >
                  {sub.status}
                </Badge>
                {sub.cancel_at_period_end && (
                  <Badge variant="warning">Ends {new Date(sub.current_period_end).toLocaleDateString()}</Badge>
                )}
              </div>
              <div className="text-sm text-content-muted font-medium">
                Current period: {new Date(sub.current_period_start).toLocaleDateString()} →{" "}
                {new Date(sub.current_period_end).toLocaleDateString()}
              </div>
            </div>
            <div className="flex gap-2">
              <Button
                variant="secondary"
                icon={<CreditCard size={14} />}
                loading={portal.isPending}
                onClick={() => portal.mutate()}
              >
                Manage payment
              </Button>
              {!sub.cancel_at_period_end && sub.status !== "cancelled" && (
                <Button variant="danger" onClick={() => setShowCancelConfirm(true)}>
                  Cancel at period end
                </Button>
              )}
            </div>
          </div>
        ) : (
          <div className="text-sm text-content-muted font-medium">
            No active subscription. Pick a plan below to start.
          </div>
        )}
      </Card>

      {/* Usage */}
      {usage && (
        <Card title="Current period usage" className="animate-fade-in stagger-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {Object.entries(usage.meters).map(([meter, m]) => (
              <div key={meter} className="p-4 rounded-xl bg-surface/70 border border-line/60 shadow-sm transition-all duration-200 hover:-translate-y-px hover:shadow-md">
                <div className="text-xs uppercase tracking-wider text-content-subtle font-bold">
                  {meter.replace(/_/g, " ")}
                </div>
                <div className="flex items-baseline justify-between mt-1">
                  <span className="text-2xl font-bold text-content">
                    {fmtNumber(m.used)}
                  </span>
                  <span className="text-xs text-content-subtle font-medium">
                    {m.limit != null ? `/ ${fmtNumber(m.limit)}` : "unlimited"}
                  </span>
                </div>
                {m.limit != null && (
                  <div className="mt-2 h-1.5 w-full bg-surface-3/60 rounded-full overflow-hidden">
                    <div
                      className={
                        m.pct >= 1 ? "bg-rose-500 h-full" : m.pct >= 0.8 ? "bg-amber-500 h-full" : "bg-emerald-500 h-full"
                      }
                      style={{ width: `${Math.min(100, m.pct * 100)}%` }}
                    />
                  </div>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Plans */}
      <Card title={sub ? "Switch plan" : "Available plans"} className="animate-fade-in stagger-4">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {plans?.map((p) => {
            const isCurrent = p.id === activePlanId;
            return (
              <div
                key={p.id}
                className={`relative p-6 rounded-2xl border transition-all duration-300 hover:scale-[1.01] hover:shadow-lg ${
                  isCurrent
                    ? "border-accent/20 bg-accent-soft/5 ring-4 ring-accent/10 shadow-sm"
                    : "border-line/90 bg-surface/70 hover:border-slate-350"
                }`}
              >
                {isCurrent && (
                  <Badge variant="primary" className="absolute top-4 right-4 text-[10px] font-bold uppercase tracking-wider">
                    Current Plan
                  </Badge>
                )}
                <div className="text-lg font-bold text-content leading-tight">{p.display_name}</div>
                <div className="text-3xl font-semibold text-content mt-2 tracking-tight">
                  {p.base_price_cents > 0 ? cents(p.base_price_cents) : "Custom"}
                  {p.base_price_cents > 0 && (
                    <span className="text-xs font-normal text-content-subtle tracking-normal font-sans ml-1">/{p.billing_interval}</span>
                  )}
                </div>
                <ul className="mt-5 space-y-2 text-xs font-medium text-content-muted">
                  {Object.entries(p.included_quotas).slice(0, 5).map(([k, v]) => (
                    <li key={k} className="flex items-center gap-2">
                      <Check size={14} className="text-emerald-500 shrink-0" />
                      <span className="capitalize">
                        {fmtNumber(v as number)} {k.replace(/_/g, " ")}
                      </span>
                    </li>
                  ))}
                </ul>
                {!isCurrent && (
                  <Button
                    className="w-full mt-6"
                    variant={p.tier === "scale" ? "primary" : "secondary"}
                    // Switching plans isn't implemented server-side — starting a
                    // second subscription now returns 409 rather than silently
                    // stacking one. Say so instead of offering a dead action.
                    disabled={!!sub}
                    title={
                      sub
                        ? "Cancel your current subscription before switching plans"
                        : undefined
                    }
                    onClick={() => setPickPlan(p)}
                  >
                    {sub ? "Cancel current plan to switch" : "Subscribe"}
                  </Button>
                )}
              </div>
            );
          })}
        </div>
      </Card>

      {/* Enterprise CTA */}
      <Card className="animate-fade-in stagger-5 border-line/80 bg-gradient-to-br from-slate-50/80 to-white/80 dark:from-slate-900/60 dark:to-slate-800/60">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-5">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-lg font-bold text-content dark:text-content">Enterprise</span>
              <Badge variant="primary" className="text-[10px] font-bold uppercase tracking-wider">Custom</Badge>
            </div>
            <p className="text-sm text-content-muted dark:text-content-subtle max-w-lg">
              Need custom SLAs, SSO, dedicated infrastructure, GxP compliance workflows, or volume pricing?
              Our enterprise team will scope a contract around your requirements.
            </p>
            <ul className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-xs text-content-muted dark:text-content-subtle">
              {[
                "Unlimited SKUs",
                "SSO / SAML",
                "Dedicated infra",
                "GxP audit trails",
                "SLA guarantees",
                "Priority support",
              ].map((f) => (
                <li key={f} className="flex items-center gap-1.5">
                  <Check size={12} className="text-emerald-500 shrink-0" />
                  {f}
                </li>
              ))}
            </ul>
          </div>
          <a
            href="mailto:enterprise@sanket-supply.com?subject=Enterprise%20Enquiry"
            className="shrink-0 inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-surface-2 hover:bg-surface-2 dark:bg-surface dark:hover:bg-surface-2 text-white dark:text-content text-sm font-semibold transition-colors shadow-sm"
          >
            Contact sales
          </a>
        </div>
      </Card>

      {/* Standard Web Checkout (One-Time / Custom Orders) */}
      <Card title="Standard Web Checkout" className="animate-fade-in stagger-6 border-line/80 bg-surface/70 dark:bg-surface/40">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <div className="text-sm font-bold text-content dark:text-content">
              Direct Order Checkout
            </div>
            <p className="text-xs text-content-muted dark:text-content-subtle mt-1 max-w-xl">
              Test or execute Razorpay Standard Checkout order creation and instant cryptographic signature verification directly from this workspace.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <RazorpayCheckoutButton
              amount={50000}
              currency="INR"
              description="SANKET Supply Chain Optimization Order"
              prefill={{ email }}
              onSuccess={(res) => {
                console.log("Standard checkout verified successfully:", res);
                qc.invalidateQueries({ queryKey: ["billing"] });
              }}
            >
              Test Standard Checkout (₹500)
            </RazorpayCheckoutButton>
          </div>
        </div>
      </Card>

      {/* Subscribe Modal */}
      <Modal
        open={!!pickPlan}
        title={`Subscribe to ${pickPlan?.display_name ?? ""}`}
        onClose={() => setPickPlan(null)}
      >
        <div className="space-y-4">
          <p className="text-sm text-content-muted dark:text-content-subtle">
            You'll be redirected to Razorpay to complete payment.
            {pickPlan && pickPlan.base_price_cents > 0 && (
              <> Amount: <strong className="text-content dark:text-content">{inrFmt.format(pickPlan.base_price_cents / 100)}/{pickPlan.billing_interval}</strong>.</>
            )}
          </p>
          <Input
            label="Billing email"
            type="email"
            placeholder="you@company.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <div className="flex justify-end gap-2 pt-2">
            <Button variant="secondary" onClick={() => setPickPlan(null)}>Cancel</Button>
            <Button
              variant="primary"
              loading={subscribe.isPending || openingCheckout}
              disabled={!/^\S+@\S+\.\S+$/.test(email)}
              onClick={() => {
                if (pickPlan) {
                  subscribe.mutate({
                    plan_id: pickPlan.id,
                    billing_email: email,
                  });
                }
              }}
            >
              Proceed to payment
            </Button>
          </div>
        </div>
      </Modal>

      {/* Cancel confirmation */}
      <ConfirmDialog
        open={showCancelConfirm}
        title="Cancel subscription?"
        message={
          <p className="text-sm text-content-muted dark:text-content-subtle">
            Your subscription will remain active until the end of the current billing period, then cancel automatically. You can resubscribe at any time.
          </p>
        }
        confirmLabel="Cancel at period end"
        tone="danger"
        loading={cancel.isPending}
        onConfirm={() => cancel.mutate()}
        onClose={() => setShowCancelConfirm(false)}
      />
    </div>
  );
};
