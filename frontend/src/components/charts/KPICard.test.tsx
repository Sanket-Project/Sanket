import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { KPICard } from "./KPICard";

it("defaults to Recorded provenance", () => {
  render(<KPICard label="Orders" value={4} />);
  expect(screen.getByText("Recorded")).toBeInTheDocument();
});

it("passes provenance through", () => {
  render(<KPICard label="Orders" value={4} provenance="estimated" />);
  expect(screen.getByText("Estimated")).toBeInTheDocument();
});

it("treats the Unavailable sentinel as missing and never shows the subtitle as the reason", () => {
  render(<KPICard label="Capital" value="Unavailable" subtitle="From the current source report" />);
  expect(screen.getByText("—")).toBeInTheDocument();
  expect(screen.getByText("Not available from current data")).toBeInTheDocument();
  expect(screen.queryByText("From the current source report")).not.toBeInTheDocument();
  expect(screen.queryByText("Unavailable")).not.toBeInTheDocument();
});

it("shows an explicit unavailableReason for a missing value", () => {
  render(<KPICard label="Capital" value="Unavailable" subtitle="From the current source report" unavailableReason="Needs unit cost" />);
  expect(screen.getByText("—")).toBeInTheDocument();
  expect(screen.getByText("Needs unit cost")).toBeInTheDocument();
});

it("treats the dash sentinel as missing with the default reason", () => {
  render(<KPICard label="Capital" value="—" />);
  expect(screen.getByText("Not available from current data")).toBeInTheDocument();
});
