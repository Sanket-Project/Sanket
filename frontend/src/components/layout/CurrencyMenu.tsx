import { useState } from "react";

import { useCurrencyStore, type DisplayCurrency } from "@/stores/currency";

const LABEL: Record<DisplayCurrency, string> = {
  source: "As recorded",
  USD: "USD",
  INR: "INR",
};

/**
 * Display-currency control. Amounts stay in the currency they were recorded
 * in unless the user picks another one *and* enters a USD↔INR rate; the rate
 * is the user's own, stamped with the day it was entered — never a built-in.
 */
export const CurrencyMenu = () => {
  const { display, manualRate, setDisplay, setManualRate, clearManualRate } = useCurrencyStore();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(manualRate ? String(manualRate.usdToInr) : "");

  return (
    <div className="relative shrink-0">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="h-9 px-3 flex items-center gap-1.5 rounded-xl border border-line bg-surface text-content-muted hover:text-content hover:bg-surface-2 transition-all duration-150 tactile-press"
        aria-expanded={open}
        aria-label={`Amounts: ${LABEL[display]}`}
        title="Display currency"
      >
        <span className="text-xs font-semibold tracking-wide">{LABEL[display]}</span>
      </button>

      {open && (
        <div className="absolute right-0 z-50 mt-2 w-72 rounded-xl border border-line bg-surface p-3 shadow-lg">
          <label className="block text-xs font-semibold text-content" htmlFor="display-currency">
            Show amounts in
          </label>
          <select
            id="display-currency"
            value={display}
            onChange={(e) => setDisplay(e.target.value as DisplayCurrency)}
            className="mt-1 w-full rounded-lg border border-line bg-surface-2 px-2 py-1.5 text-sm"
          >
            <option value="source">The currency they were recorded in</option>
            <option value="INR">INR</option>
            <option value="USD">USD</option>
          </select>

          <label className="mt-3 block text-xs font-semibold text-content" htmlFor="usd-inr-rate">
            1 USD = … INR (your rate)
          </label>
          <div className="mt-1 flex gap-2">
            <input
              id="usd-inr-rate"
              inputMode="decimal"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="e.g. 84.2"
              className="w-full rounded-lg border border-line bg-surface-2 px-2 py-1.5 text-sm"
            />
            <button
              type="button"
              onClick={() => setManualRate(Number(draft))}
              className="rounded-lg border border-line px-2 text-xs font-semibold"
            >
              Save rate
            </button>
          </div>
          <p className="mt-2 text-xs text-content-muted">
            {manualRate ? (
              <>
                Using your rate 1 USD = {manualRate.usdToInr} INR, entered {manualRate.setAt}.{" "}
                <button type="button" className="underline" onClick={clearManualRate}>
                  Remove
                </button>
              </>
            ) : (
              "No rate set — amounts stay in their own currency. Sanket has no live exchange rate."
            )}
          </p>
        </div>
      )}
    </div>
  );
};
