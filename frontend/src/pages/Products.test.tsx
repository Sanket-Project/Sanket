import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ list: vi.fn(), listAll: vi.fn() }));
vi.mock("@/api/products", () => ({ productsApi: api }));
vi.mock("@/api/skus", () => ({ skusApi: { list: async () => [], listAll: async () => [] } }));
vi.mock("@/components/products/ProductCleanup", () => ({ ProductCleanup: () => null }));
vi.mock("@/hooks/useWorkspaceIndustry", () => ({ useWorkspaceIndustry: () => "fashion" }));
import { ProductsPage } from "@/pages/Products";

const rows = Array.from({ length: 160 }, (_, i) => ({ id: String(i), name: `Product ${i}`,
  status: "active", category: "Shirts", industry: "fashion", attributes: {},
  updated_at: "2026-10-28T00:00:00Z", created_at: "2026-10-28T00:00:00Z" }));
const show = () => render(<QueryClientProvider client={new QueryClient({ defaultOptions: {
  queries: { retry: false, retryDelay: 0 },
} })}><MemoryRouter><ProductsPage /></MemoryRouter></QueryClientProvider>);
beforeEach(() => { vi.clearAllMocks(); api.list.mockResolvedValue(rows.slice(0, 100)); api.listAll.mockResolvedValue(rows); });

it("counts every product and lets users page and search the entire catalogue", async () => {
  show();
  expect((await screen.findAllByText("160", {}, { timeout: 2000 })).length).toBeGreaterThan(0);
  expect(screen.getByText("Product 0")).toBeInTheDocument();
  expect(screen.queryByText("Product 159")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Next page" }));
  expect(screen.queryByText("Product 0")).not.toBeInTheDocument();
  fireEvent.change(screen.getByPlaceholderText("Search name, brand, category…"), { target: { value: "Product 159" } });
  expect(await screen.findByText("Product 159")).toBeInTheDocument();
});

it("reports catalogue errors instead of claiming the catalogue is empty", async () => {
  api.list.mockRejectedValue(new Error("Unavailable"));
  api.listAll.mockRejectedValue(new Error("Unavailable"));
  show();
  const alert = await screen.findByRole("alert");
  expect(within(alert).getByText(/catalogue could not be loaded/i)).toBeInTheDocument();
  expect(screen.queryByText("Your Product Catalogue is Empty")).not.toBeInTheDocument();
});
