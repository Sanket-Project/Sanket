import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

export type CurrencyCode = "USD" | "INR";

interface CurrencyState {
  currency: CurrencyCode;
  exchangeRate: number; // $1 USD = X INR
  setCurrency: (c: CurrencyCode) => void;
}

// Automatically detect if user timezone offset matches Indian Standard Time (IST, GMT+5:30)
// GMT+5:30 timezone offset in JS is -330 minutes.
const isIndianTimezone = new Date().getTimezoneOffset() === -330;

export const useCurrencyStore = create<CurrencyState>()(
  persist(
    (set) => ({
      currency: isIndianTimezone ? "INR" : "USD",
      exchangeRate: 83,
      setCurrency: (c) => set({ currency: c }),
    }),
    {
      name: "sanket.currency",
      storage: createJSONStorage(() => localStorage),
    },
  ),
);
