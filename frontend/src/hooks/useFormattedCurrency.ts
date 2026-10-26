import { useCurrencyStore } from "@/stores/currency";

const ISO = /^[A-Z]{3}$/;

const fmtDate = (iso: string) =>
  new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric" }).format(
    new Date(`${iso}T00:00:00Z`),
  );

/**
 * Money formatting that never guesses a currency.
 *
 * Every amount must say what currency it is in (`sourceCurrency`, from the
 * API). It is shown in that currency unless the user chose another display
 * currency *and* entered a USD↔INR rate themselves; then it is converted and
 * `conversionNote` says at what rate, entered when.
 */
export function useFormattedCurrency() {
  const { display, manualRate } = useCurrencyStore();

  const convertVal = (
    amount: number | null | undefined,
    sourceCurrency: string | null | undefined,
  ): { val: number; code: string | null; converted: boolean } => {
    const src = (sourceCurrency ?? "").toUpperCase();
    const code = ISO.test(src) ? src : null;
    const val = amount ?? 0;
    if (!code || display === "source" || display === code || !manualRate) {
      return { val, code, converted: false };
    }
    if (code === "USD" && display === "INR") {
      return { val: val * manualRate.usdToInr, code: "INR", converted: true };
    }
    if (code === "INR" && display === "USD") {
      return { val: val / manualRate.usdToInr, code: "USD", converted: true };
    }
    return { val, code, converted: false };
  };

  const formatPrice = (
    amount: number | null | undefined,
    sourceCurrency: string | null | undefined,
    opts: { compact?: boolean } = {},
  ) => {
    if (amount == null) return "—";
    const { val, code } = convertVal(amount, sourceCurrency);
    const numberOpts = {
      notation: opts.compact ? ("compact" as const) : ("standard" as const),
      maximumFractionDigits: opts.compact ? 1 : 0,
    };
    if (!code) {
      return `${new Intl.NumberFormat("en-US", numberOpts).format(val)} (currency unknown)`;
    }
    return new Intl.NumberFormat(code === "INR" ? "en-IN" : "en-US", {
      style: "currency",
      currency: code,
      ...numberOpts,
    }).format(val);
  };

  /** Why an amount in `sourceCurrency` is shown as it is, or null if obvious. */
  const conversionNote = (sourceCurrency: string | null | undefined): string | null => {
    const src = (sourceCurrency ?? "").toUpperCase();
    if (display === "source" || display === src || !ISO.test(src)) return null;
    const { converted } = convertVal(1, src);
    if (converted && manualRate) {
      return `Converted at your manual rate: 1 USD = ${manualRate.usdToInr} INR (set ${fmtDate(manualRate.setAt)})`;
    }
    return `Shown in ${src} — no conversion rate set`;
  };

  return { formatPrice, convertVal, conversionNote, display };
}
