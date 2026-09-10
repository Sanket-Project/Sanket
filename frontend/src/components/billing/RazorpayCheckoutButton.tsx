import React, { useState } from "react";
import toast from "react-hot-toast";
import { CreditCard } from "@/components/ui/icons";
import { Button } from "@/components/ui/Button";
import { billingApi } from "@/api/billing";
import { openStandardOrderCheckout } from "@/utils/razorpay";
import { getErrorMessage } from "@/utils/errors";

export interface RazorpayCheckoutButtonProps {
  /** Amount in paise (e.g. 50000 = ₹500.00). Minimum 100 paise (₹1.00). */
  amount: number;
  currency?: string;
  receipt?: string;
  name?: string;
  description?: string;
  prefill?: {
    name?: string;
    email?: string;
    contact?: string;
  };
  notes?: Record<string, string>;
  themeColor?: string;
  className?: string;
  variant?: "primary" | "secondary" | "danger" | "ghost";
  disabled?: boolean;
  children?: React.ReactNode;
  onSuccess?: (result: {
    order_id: string;
    payment_id: string;
    razorpay_signature: string;
  }) => void;
  onError?: (error: unknown) => void;
  onDismiss?: () => void;
}

export const RazorpayCheckoutButton: React.FC<RazorpayCheckoutButtonProps> = ({
  amount,
  currency = "INR",
  receipt,
  name = "SANKET",
  description = "Standard Checkout Payment",
  prefill,
  notes,
  themeColor = "#6366f1",
  className,
  variant = "primary",
  disabled = false,
  children,
  onSuccess,
  onError,
  onDismiss,
}) => {
  const [loading, setLoading] = useState(false);

  const handleCheckout = async () => {
    if (amount < 100) {
      toast.error("Minimum payment amount is ₹1.00 (100 paise)");
      return;
    }

    setLoading(true);
    try {
      // 1. Get Razorpay key ID from config or environment
      let keyId = import.meta.env.VITE_RAZORPAY_KEY_ID as string | undefined;
      if (!keyId) {
        const config = await billingApi.getConfig();
        if (config.configured && config.key_id) {
          keyId = config.key_id;
        }
      }

      if (!keyId) {
        throw new Error(
          "Razorpay is not configured. Please set VITE_RAZORPAY_KEY_ID or backend keys."
        );
      }

      // 2. Create order on backend (POST /api/create-order or /billing/create-order)
      const order = await billingApi.createOrder({
        amount,
        currency,
        receipt: receipt || `rcpt_${Date.now()}`,
        notes,
      });

      // 3. Open Razorpay Standard Checkout popup modal
      const opened = await openStandardOrderCheckout({
        keyId,
        orderId: order.order_id,
        amount: order.amount,
        currency: order.currency,
        name,
        description,
        prefill,
        notes,
        themeColor,
        onSuccess: async (response) => {
          try {
            // 4. Verify payment signature on backend (POST /api/verify-payment or /billing/verify-payment)
            const verification = await billingApi.verifyPayment({
              razorpay_order_id: response.razorpay_order_id,
              razorpay_payment_id: response.razorpay_payment_id,
              razorpay_signature: response.razorpay_signature,
            });

            toast.success("Payment verified successfully!");
            if (onSuccess) {
              onSuccess({
                order_id: verification.order_id,
                payment_id: verification.payment_id,
                razorpay_signature: response.razorpay_signature,
              });
            }
          } catch (err: unknown) {
            const errMsg = getErrorMessage(err, "Payment signature verification failed");
            toast.error(errMsg);
            if (onError) onError(err);
          }
        },
        onDismiss: () => {
          toast("Payment cancelled — modal closed.", { icon: "ℹ️" });
          if (onDismiss) onDismiss();
        },
        onFailure: (err) => {
          const errMsg = err?.description || "Payment failed. Please try again.";
          toast.error(errMsg);
          if (onError) onError(err);
        },
      });

      if (!opened) {
        throw new Error("Failed to load Razorpay Checkout script. Check your internet connection.");
      }
    } catch (err: unknown) {
      const errMsg = getErrorMessage(err, "Could not initialize checkout");
      toast.error(errMsg);
      if (onError) onError(err);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Button
      variant={variant}
      className={className}
      loading={loading}
      disabled={disabled || loading}
      icon={<CreditCard size={14} />}
      onClick={handleCheckout}
    >
      {children || `Pay ${(amount / 100).toLocaleString("en-IN", { style: "currency", currency })}`}
    </Button>
  );
};
export default RazorpayCheckoutButton;
