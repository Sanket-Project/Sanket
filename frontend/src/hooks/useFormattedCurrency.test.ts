import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { useFormattedCurrency } from "@/hooks/useFormattedCurrency";
import { migrateCurrencyState, useCurrencyStore } from "@/stores/currency";

/**
 * Audit F03: an INR sales total of 13,091,162 was displayed as 1,086,566,446 —
 * the hook assumed the amount was USD and multiplied by a hard-coded 83.
 * Amounts are now formatted in the currency they are in, and converted only
 * with a rate the user entered (and dated) themselves.
 */
const reset = () =>
  act(() => useCurrencyStore.setState({ display: "source", manualRate: null }));

describe("useFormattedCurrency", () => {
  beforeEach(reset);

  it("formats INR as INR with no conversion", () => {
    const { result } = renderHook(() => useFormattedCurrency());
    expect(result.current.formatPrice(13091162, "INR")).toBe("₹1,30,91,162");
    expect(result.current.convertVal(13091162, "INR")).toEqual({
      val: 13091162,
      code: "INR",
      converted: false,
    });
  });

  it("does not convert when asked for USD but no rate has been entered", () => {
    act(() => useCurrencyStore.getState().setDisplay("USD"));
    const { result } = renderHook(() => useFormattedCurrency());

    expect(result.current.convertVal(8400, "INR")).toEqual({ val: 8400, code: "INR", converted: false });
    expect(result.current.conversionNote("INR")).toMatch(/no conversion rate set/i);
  });

  it("converts with the user's dated manual rate and says so", () => {
    act(() => {
      useCurrencyStore.getState().setDisplay("USD");
      useCurrencyStore.getState().setManualRate(84, "2026-10-01");
    });
    const { result } = renderHook(() => useFormattedCurrency());

    expect(result.current.convertVal(8400, "INR")).toEqual({ val: 100, code: "USD", converted: true });
    expect(result.current.formatPrice(8400, "INR")).toBe("$100");
    expect(result.current.conversionNote("INR")).toBe("Converted at your manual rate: 1 USD = 84 INR (set 1 Oct 2026)");
  });

  it("never converts a currency the rate does not cover", () => {
    act(() => {
      useCurrencyStore.getState().setDisplay("INR");
      useCurrencyStore.getState().setManualRate(84, "2026-10-01");
    });
    const { result } = renderHook(() => useFormattedCurrency());
    expect(result.current.convertVal(10, "EUR")).toEqual({ val: 10, code: "EUR", converted: false });
  });

  it("shows an amount of unknown currency as a plain number, not as dollars", () => {
    const { result } = renderHook(() => useFormattedCurrency());
    expect(result.current.formatPrice(1500, null)).toBe("1,500 (currency unknown)");
  });
});

describe("persisted currency settings", () => {
  it("drops the old hard-coded 83 instead of treating it as a user rate", () => {
    expect(migrateCurrencyState({ currency: "INR", exchangeRate: 83 }, 0)).toEqual({
      display: "INR",
      manualRate: null,
    });
  });
});
