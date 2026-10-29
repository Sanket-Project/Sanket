import { useFormattedCurrency } from "@/hooks/useFormattedCurrency";
import { formatCompact } from "./axis";

/**
 * Compact currency axis ticks that match how the app shows money: the amount's
 * own currency (INR in en-IN), converted only when the user set a display
 * currency and a manual rate. With no known currency the tick is a plain
 * compact number — the axis must not guess a symbol.
 */
export function useCurrencyTick(currencyCode?: string): (n: number) => string {
  const { formatPrice } = useFormattedCurrency();
  const known = /^[A-Z]{3}$/.test((currencyCode ?? "").toUpperCase());
  return (n: number) => (known ? formatPrice(n, currencyCode, { compact: true }) : formatCompact(n));
}
