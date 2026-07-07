import { useCurrencyStore, type CurrencyCode } from "@/stores/currency";

export function useFormattedCurrency() {
  const { currency, exchangeRate } = useCurrencyStore();

  const convertVal = (amount: number | null | undefined, fromCurrency: string = "USD"): { val: number; code: CurrencyCode } => {
    if (amount == null) return { val: 0, code: currency };

    const fromUpper = fromCurrency.toUpperCase();
    const targetUpper = currency.toUpperCase();

    // If source and target match, return original
    if (fromUpper === targetUpper) {
      return { val: amount, code: targetUpper as CurrencyCode };
    }

    // USD -> INR conversion
    if (fromUpper === "USD" && targetUpper === "INR") {
      return { val: amount * exchangeRate, code: "INR" };
    }

    // INR -> USD conversion
    if (fromUpper === "INR" && targetUpper === "USD") {
      return { val: amount / exchangeRate, code: "USD" };
    }

    return { val: amount, code: targetUpper as CurrencyCode };
  };

  const formatPrice = (
    amount: number | null | undefined,
    fromCurrency: string = "USD",
    opts: { compact?: boolean } = {},
  ) => {
    if (amount == null) return "—";

    const { val, code } = convertVal(amount, fromCurrency);
    const isINR = code === "INR";
    const locale = isINR ? "en-IN" : "en-US";

    return new Intl.NumberFormat(locale, {
      style: "currency",
      currency: code,
      notation: opts.compact ? "compact" : "standard",
      maximumFractionDigits: opts.compact ? 1 : 0,
    }).format(val);
  };

  return {
    formatPrice,
    convertVal,
    activeCurrency: currency,
  };
}
