import { render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";
import { PageHeader } from "./PageHeader";

it("gives a working page one primary heading and a named action group", () => {
  render(<PageHeader eyebrow="Measure" title="Sales analytics" description="Recorded sales, before returns" actions={<button>Export sales</button>} />);
  expect(screen.getByRole("heading", { level: 1, name: "Sales analytics" })).toBeInTheDocument();
  expect(screen.getByText("Recorded sales, before returns")).toBeInTheDocument();
  expect(within(screen.getByRole("group", { name: "Sales analytics actions" })).getByRole("button", { name: "Export sales" })).toBeInTheDocument();
});

it("does not announce an empty action group for a read-only page", () => {
  render(<PageHeader title="Your profile" />);
  expect(screen.queryByRole("group")).not.toBeInTheDocument();
});
