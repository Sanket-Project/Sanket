import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { CurrencyMenu } from "@/components/layout/CurrencyMenu";
import { useCurrencyStore } from "@/stores/currency";

describe("CurrencyMenu", () => {
  beforeEach(() => act(() => useCurrencyStore.setState({ display: "source", manualRate: null })));

  it("defaults to showing amounts in the currency they were recorded in", () => {
    render(<CurrencyMenu />);
    expect(screen.getByRole("button", { name: /amounts: as recorded/i })).toBeInTheDocument();
  });

  it("says nothing is converted until the user enters a rate", async () => {
    const user = userEvent.setup();
    render(<CurrencyMenu />);
    await user.click(screen.getByRole("button", { name: /amounts/i }));
    await user.selectOptions(screen.getByLabelText(/show amounts in/i), "USD");

    expect(useCurrencyStore.getState().display).toBe("USD");
    expect(screen.getByText(/no rate set/i)).toBeInTheDocument();
  });

  it("stores the rate the user typed with today's date", async () => {
    const user = userEvent.setup();
    render(<CurrencyMenu />);
    await user.click(screen.getByRole("button", { name: /amounts/i }));
    await user.type(screen.getByLabelText(/1 usd =/i), "84.5");
    await user.click(screen.getByRole("button", { name: /save rate/i }));

    const rate = useCurrencyStore.getState().manualRate;
    expect(rate?.usdToInr).toBe(84.5);
    expect(rate?.setAt).toBe(new Date().toISOString().slice(0, 10));
  });
});
