import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { SignalGrid } from "@/pages/landing/sections/SignalGrid";

describe("SignalGrid", () => {
  it("names the source behind each signal", () => {
    render(<SignalGrid />);
    expect(screen.getByText("Google Trends")).toBeInTheDocument();
    expect(screen.getByText("FRED")).toBeInTheDocument();
  });

  it("expands a signal to show what it feeds", async () => {
    const user = userEvent.setup();
    render(<SignalGrid />);
    await user.click(screen.getByRole("button", { name: /weather/i }));
    expect(screen.getByText(/seasonal demand, sowing windows/i)).toBeInTheDocument();
  });
});
