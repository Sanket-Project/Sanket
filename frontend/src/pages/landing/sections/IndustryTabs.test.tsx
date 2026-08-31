import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { IndustryTabs } from "@/pages/landing/sections/IndustryTabs";

describe("IndustryTabs", () => {
  it("shows the first industry's real horizon on load", () => {
    render(<IndustryTabs />);
    expect(screen.getByRole("tab", { name: /apparel & fashion/i })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByText(/26-week/i)).toBeInTheDocument();
  });

  it("switches the panel when another industry is chosen", async () => {
    const user = userEvent.setup();
    render(<IndustryTabs />);
    await user.click(screen.getByRole("tab", { name: /pharmaceuticals/i }));

    // Pharma is the commercially distinctive one: 52 weeks at GxP audit level.
    expect(screen.getByText(/52-week/i)).toBeInTheDocument();
    expect(screen.getByText(/gxp/i)).toBeInTheDocument();
    expect(screen.queryByText(/26-week/i)).toBeNull();
  });

  it("is operable by keyboard", async () => {
    const user = userEvent.setup();
    render(<IndustryTabs />);
    await user.tab();
    expect(screen.getByRole("tab", { name: /apparel & fashion/i })).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("tabpanel")).toBeInTheDocument();
  });
});
