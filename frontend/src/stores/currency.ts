import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

export type CurrencyCode = "USD" | "INR";

/** "source" shows every amount in the currency it was recorded in. */
export type DisplayCurrency = "source" | CurrencyCode;

/**
 * A conversion rate the user typed in themselves, with the date they did.
 * There is deliberately no built-in rate: an old constant (83) once turned an
 * INR total into a figure 83x too large. Without a rate, nothing is converted.
 */
export interface ManualRate {
  usdToInr: number;
  setAt: string; // ISO date the user entered the rate
}

interface CurrencyState {
  display: DisplayCurrency;
  manualRate: ManualRate | null;
  setDisplay: (d: DisplayCurrency) => void;
  setManualRate: (usdToInr: number, setAt?: string) => void;
  clearManualRate: () => void;
}

type PersistedCurrency = Pick<CurrencyState, "display" | "manualRate">;

/**
 * Version 0 stored `{ currency, exchangeRate: 83 }`. The 83 was a default, not
 * a rate anyone entered, so it is discarded; the display preference survives.
 */
export function migrateCurrencyState(persisted: unknown, version: number): PersistedCurrency {
  const old = (persisted ?? {}) as Record<string, unknown>;
  if (version < 2) {
    const display = old.currency === "INR" || old.currency === "USD" ? old.currency : "source";
    return { display, manualRate: null };
  }
  return {
    display: (old.display as DisplayCurrency) ?? "source",
    manualRate: (old.manualRate as ManualRate | null) ?? null,
  };
}

export const useCurrencyStore = create<CurrencyState>()(
  persist(
    (set) => ({
      display: "source",
      manualRate: null,
      setDisplay: (display) => set({ display }),
      setManualRate: (usdToInr, setAt) =>
        set({
          manualRate:
            Number.isFinite(usdToInr) && usdToInr > 0
              ? { usdToInr, setAt: setAt ?? new Date().toISOString().slice(0, 10) }
              : null,
        }),
      clearManualRate: () => set({ manualRate: null }),
    }),
    {
      name: "sanket.currency",
      version: 2,
      storage: createJSONStorage(() => localStorage),
      migrate: migrateCurrencyState,
      partialize: (s) => ({ display: s.display, manualRate: s.manualRate }),
    },
  ),
);
