/** Helper for loading and launching Razorpay JS Checkout SDK modal. */

/** The subset of the Checkout SDK this helper uses. */
interface RazorpayInstance {
  open: () => void;
  on: (event: "payment.failed", handler: (response: RazorpayFailure) => void) => void;
}
type RazorpayConstructor = new (options: Record<string, unknown>) => RazorpayInstance;
interface RazorpayFailure {
  error: { code?: string; description?: string; reason?: string; [key: string]: unknown };
}

declare global {
  interface Window {
    Razorpay?: RazorpayConstructor;
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

export interface RazorpayStandardOrderOptions {
  keyId: string;
  orderId: string;
  amount: number; // in paise
  currency?: string;
  name?: string;
  description?: string;
  image?: string;
  prefill?: {
    name?: string;
    email?: string;
    contact?: string;
  };
  notes?: Record<string, string>;
  themeColor?: string;
  onSuccess: (response: {
    razorpay_payment_id: string;
    razorpay_order_id: string;
    razorpay_signature: string;
  }) => void;
  onDismiss?: () => void;
  onFailure?: (error: RazorpayFailure["error"]) => void;
}

export async function openStandardOrderCheckout({
  keyId,
  orderId,
  amount,
  currency = "INR",
  name = "SANKET",
  description = "Payment",
  image,
  prefill,
  notes,
  themeColor = "#6366f1",
  onSuccess,
  onDismiss,
  onFailure,
}: RazorpayStandardOrderOptions): Promise<boolean> {
  const loaded = await loadRazorpayScript();
  if (!loaded || !window.Razorpay) {
    return false;
  }

  const options: Record<string, unknown> = {
    key: keyId,
    amount,
    currency,
    name,
    description,
    order_id: orderId,
    prefill: {
      name: prefill?.name || "",
      email: prefill?.email || "",
      contact: prefill?.contact || "",
    },
    notes: notes || {},
    theme: {
      color: themeColor,
    },
    handler: (response: {
      razorpay_payment_id: string;
      razorpay_order_id: string;
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

  if (image) {
    options.image = image;
  }

  const rzp = new window.Razorpay(options);

  if (onFailure) {
    rzp.on("payment.failed", (response: RazorpayFailure) => {
      onFailure(response.error);
    });
  }

  rzp.open();
  return true;
}
