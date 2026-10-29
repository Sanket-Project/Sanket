import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, it, vi } from "vitest";
import { PlanningHero } from "./PlanningHero";

it("connects the reference hero's primary action to the real forecasting workflow", () => {
  const generate = vi.fn();
  render(<MemoryRouter><PlanningHero onGenerate={generate} generating={false} /></MemoryRouter>);
  expect(screen.getByRole("heading", { level: 1, name: "Turn demand signals into confident decisions." })).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Generate forecast" }));
  expect(generate).toHaveBeenCalledOnce();
  expect(screen.getByRole("link", { name: /View latest insights/ })).toHaveAttribute("href", "/workspace/trends");
});

it("keeps generation unavailable while the current forecast is running", () => {
  render(<MemoryRouter><PlanningHero onGenerate={vi.fn()} generating /></MemoryRouter>);
  expect(screen.getByRole("button", { name: "Generate forecast" })).toBeDisabled();
});

it("keeps planning status and refresh available inside the compact hero", () => {
  const refresh = vi.fn();
  render(<MemoryRouter><PlanningHero onGenerate={vi.fn()} generating={false} brief={<p>Recorded inputs unavailable</p>} actions={<button onClick={refresh}>Refresh brief</button>} /></MemoryRouter>);
  expect(screen.getByText("Recorded inputs unavailable")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Refresh brief" }));
  expect(refresh).toHaveBeenCalledOnce();
});
