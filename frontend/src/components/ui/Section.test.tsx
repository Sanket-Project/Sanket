import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { Section } from "./Section";

it("is a labelled region with a level-2 heading and its actions", () => {
  render(<Section title="Stock movement" description="Last 30 days" actions={<button>Export</button>}><p>body</p></Section>);
  const region = screen.getByRole("region", { name: "Stock movement" });
  expect(region).toContainElement(screen.getByRole("heading", { level: 2, name: "Stock movement" }));
  expect(screen.getByRole("button", { name: "Export" })).toBeInTheDocument();
  expect(screen.getByText("Last 30 days")).toBeInTheDocument();
});
