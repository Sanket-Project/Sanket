import { act, renderHook } from "@testing-library/react";
import { beforeEach, expect, it } from "vitest";

import { useCurrencyStore } from "@/stores/currency";
import { useCurrencyTick } from "./useCurrencyTick";

beforeEach(() => act(() => useCurrencyStore.setState({ display: "source", manualRate: null })));

it("formats ticks compactly in the app's locale for the currency", () => {
  const inr = renderHook(() => useCurrencyTick("INR")).result.current;
  expect(inr(1_200_000)).toBe("₹12L");
  expect(inr(0)).toBe("₹0");
  const usd = renderHook(() => useCurrencyTick("USD")).result.current;
  expect(usd(1_200_000)).toBe("$1.2M");
  expect(usd(950)).toBe("$950");
});

it("converts with the user's manual rate, like the rest of the app", () => {
  act(() => {
    useCurrencyStore.getState().setDisplay("INR");
    useCurrencyStore.getState().setManualRate(80, "2026-10-01");
  });
  const tick = renderHook(() => useCurrencyTick("USD")).result.current;
  expect(tick(1_000)).toBe("₹80K");
});

it("shows a plain compact number when the currency is unknown, never a guessed symbol", () => {
  const tick = renderHook(() => useCurrencyTick(undefined)).result.current;
  expect(tick(1_200_000)).toBe("1.2M");
});
