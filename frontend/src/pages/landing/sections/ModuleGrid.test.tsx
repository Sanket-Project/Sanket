import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ModuleGrid } from "@/pages/landing/sections/ModuleGrid";

describe("ModuleGrid", () => {
  it("lists every module", () => {
    render(<ModuleGrid />);
    expect(screen.getByRole("button", { name: /demand forecasting/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /decision engine/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /what-if scenarios/i })).toBeInTheDocument();
  });

  it("opens a module's detail when selected", async () => {
    const user = userEvent.setup();
    render(<ModuleGrid />);
    await user.click(screen.getByRole("button", { name: /what-if scenarios/i }));

    expect(screen.getByText(/simulate a promotion/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /what-if scenarios/i })).toHaveAttribute(
      "aria-expanded",
      "true",
    );
  });

  it("shows one detail at a time", async () => {
    const user = userEvent.setup();
    render(<ModuleGrid />);
    await user.click(screen.getByRole("button", { name: /what-if scenarios/i }));
    await user.click(screen.getByRole("button", { name: /data quality/i }));

    expect(screen.getByText(/flags gaps, duplicates/i)).toBeInTheDocument();
    expect(screen.queryByText(/simulate a promotion/i)).toBeNull();
  });
});
