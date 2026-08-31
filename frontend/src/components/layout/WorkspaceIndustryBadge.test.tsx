import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { WorkspaceIndustryBadge } from "@/components/layout/WorkspaceIndustryBadge";
import { useAuthStore } from "@/stores/auth";

/**
 * The header used to carry an industry switcher whose dropdown listed all five
 * industries by name. Two problems: it let an authenticated user change
 * industry, and it named industries their workspace has nothing to do with.
 */
describe("WorkspaceIndustryBadge", () => {
  const signIn = (industry: "fashion" | "pharma") =>
    useAuthStore.setState({
      ready: true,
      isAuthenticated: true,
      industry,
      role: "owner",
      email: "owner@example.com",
      fullName: "Owner",
      userId: "u",
      tenantId: "t",
    });

  beforeEach(() => {
    useAuthStore.setState({ industry: null, isAuthenticated: false });
  });

  it("names the workspace's own industry", () => {
    signIn("pharma");
    render(<WorkspaceIndustryBadge />);
    expect(screen.getByText("Pharmaceuticals")).toBeInTheDocument();
  });

  it("does not name any other industry", () => {
    signIn("fashion");
    render(<WorkspaceIndustryBadge />);
    expect(screen.getByText("Fashion & Apparel")).toBeInTheDocument();
    for (const other of [
      "Pharmaceuticals",
      "Consumer Electronics",
      "Agrocenter",
      "Tools & Hardware",
    ]) {
      expect(screen.queryByText(other)).toBeNull();
    }
  });

  it("offers no control that could change the industry", () => {
    signIn("fashion");
    render(<WorkspaceIndustryBadge />);
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.queryByText(/switch/i)).toBeNull();
  });
});
