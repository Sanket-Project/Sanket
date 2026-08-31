import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ConnectorGrid } from "@/pages/landing/sections/ConnectorGrid";

describe("ConnectorGrid", () => {
  it("filters by free-text search", async () => {
    const user = userEvent.setup();
    render(<ConnectorGrid />);
    await user.type(screen.getByRole("searchbox", { name: /search connectors/i }), "shop");

    expect(screen.getByText("Shopify")).toBeInTheDocument();
    expect(screen.queryByText("Snowflake")).toBeNull();
  });

  it("filters by category", async () => {
    const user = userEvent.setup();
    render(<ConnectorGrid />);
    await user.click(screen.getByRole("button", { name: /^databases$/i }));

    expect(screen.getByText("PostgreSQL")).toBeInTheDocument();
    expect(screen.queryByText("Shopify")).toBeNull();
  });

  it("says plainly how many connectors actually work today", () => {
    // The page used to advertise "29+ CONNECTORS", counting ones with no sync
    // adapter built. Six work.
    render(<ConnectorGrid />);
    expect(screen.getByText(/6 live today/i)).toBeInTheDocument();
  });

  it("marks a planned connector as not yet available", () => {
    render(<ConnectorGrid />);
    const card = screen.getByText("Snowflake").closest("li");
    expect(card).not.toBeNull();
    expect(within(card as HTMLElement).getByText(/coming soon/i)).toBeInTheDocument();
  });

  it("reports when a search matches nothing", async () => {
    const user = userEvent.setup();
    render(<ConnectorGrid />);
    await user.type(screen.getByRole("searchbox", { name: /search connectors/i }), "zzzz");
    expect(screen.getByText(/no connectors match/i)).toBeInTheDocument();
  });
});
