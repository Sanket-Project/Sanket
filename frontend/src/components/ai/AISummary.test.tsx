import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { AISummary } from "./AISummary";

const api = vi.hoisted(() => ({ summary: vi.fn() }));
vi.mock("@/api/ai", () => ({ aiApi: api }));

it("labels generated content and links evidence without interpreting HTML", async () => {
  api.summary.mockResolvedValue({ state: "success", blocks: [{ text: "Stock cover: 4.5 days. <script>unsafe</script>", kind: "fact", sources: [{ fact_id: "cover", href: "/inventory" }] }] });
  const { container } = render(<QueryClientProvider client={new QueryClient()}><AISummary feature="planning_brief" /></QueryClientProvider>);
  await userEvent.click(screen.getByRole("button", { name: /Generate AI summary/ }));
  expect(await screen.findByText("AI-generated")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /Stock cover/ })).toHaveAttribute("href", "/workspace/inventory");
  expect(container.querySelector("script")).toBeNull();
});

it("shows honest unavailable state without replacing source metrics", async () => {
  api.summary.mockResolvedValue({ state: "unavailable", blocks: [] });
  render(<QueryClientProvider client={new QueryClient()}><div>Source metric: 17 units</div><AISummary feature="planning_brief" /></QueryClientProvider>);
  await userEvent.click(screen.getByRole("button", { name: /Generate AI summary/ }));
  expect(await screen.findByText(/AI summary unavailable/)).toBeInTheDocument();
  expect(screen.getByText("Source metric: 17 units")).toBeInTheDocument();
});
