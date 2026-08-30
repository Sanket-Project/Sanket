/** Helper for loading and launching Razorpay JS Checkout SDK modal. */

declare global {
  interface Window {
    Razorpay?: any;
  }
}

export function loadRazorpayScript(): Promise<boolean> {
  return new Promise((resolve) => {
    if (window.Razorpay) {
      resolve(true);
      return;
    }
    const script = document.createElement("script");
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.onload = () => resolve(true);
    script.onerror = () => resolve(false);
    document.body.appendChild(script);
  });
}

export interface RazorpayCheckoutOptions {
  keyId: string;
  subscriptionId: string;
  planName: string;
  billingEmail: string;
  onSuccess: (response: {
    razorpay_payment_id: string;
    razorpay_subscription_id: string;
    razorpay_signature: string;
  }) => void;
  onDismiss?: () => void;
}

export async function openRazorpayCheckout({
  keyId,
  subscriptionId,
  planName,
  billingEmail,
  onSuccess,
  onDismiss,
}: RazorpayCheckoutOptions): Promise<boolean> {
  const loaded = await loadRazorpayScript();
  if (!loaded || !window.Razorpay) {
    return false;
  }

  const options = {
    key: keyId,
    subscription_id: subscriptionId,
    name: "SANKET Workspace",
    description: `${planName} Subscription`,
    prefill: {
      email: billingEmail,
    },
    theme: {
      color: "#6366f1",
    },
    handler: (response: {
      razorpay_payment_id: string;
      razorpay_subscription_id: string;
      razorpay_signature: string;
    }) => {
      onSuccess(response);
    },
    modal: {
      ondismiss: () => {
        if (onDismiss) onDismiss();
      },
    },
  };

  const rzp = new window.Razorpay(options);
  rzp.open();
  return true;
}
