import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { IndustryRoute } from "@/components/auth/IndustryRoute";
import { useAuthStore } from "@/stores/auth";

describe("IndustryRoute", () => {
  it("renders the page for the workspace's own industry", () => {
    useAuthStore.setState({ ready: true, isAuthenticated: true, industry: "pharma" });
    render(
      <IndustryRoute industry="pharma">
        <p>Batch register</p>
      </IndustryRoute>,
    );
    expect(screen.getByText("Batch register")).toBeInTheDocument();
  });

  it("denies a manually typed route belonging to another industry", () => {
    useAuthStore.setState({ ready: true, isAuthenticated: true, industry: "fashion" });
    render(
      <IndustryRoute industry="pharma">
        <p>Batch register</p>
      </IndustryRoute>,
    );
    expect(screen.queryByText("Batch register")).toBeNull();
    expect(
      screen.getByText(/not available for this workspace/i),
    ).toBeInTheDocument();
  });

  it("renders nothing while the session is still resolving", () => {
    // Guards against flashing another industry's page during bootstrap: with a
    // default industry, a Pharma tenant would see the Fashion UI for a frame.
    useAuthStore.setState({ ready: false, isAuthenticated: false, industry: null });
    const { container } = render(
      <IndustryRoute industry="pharma">
        <p>Batch register</p>
      </IndustryRoute>,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
