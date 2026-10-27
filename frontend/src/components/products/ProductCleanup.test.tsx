import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { ProductCleanup } from "./ProductCleanup";

const api = vi.hoisted(() => ({ cleanup: vi.fn(), applyCleanup: vi.fn() }));
vi.mock("@/api/ai", () => ({ aiApi: api }));

it("requires preview and explicit confirmation before changing a product", async () => {
  const suggestion = { product_id: "s1", field: "size", value: "XL", confidence: "high", evidence: "XL" };
  api.cleanup.mockResolvedValue({ state: "success", suggestions: [suggestion], duplicate_pairs: [],
    products: [{ id: "s1", name: "Blue Shirt XL", category: "Shirts", attributes: {}, revision: "v1" }] });
  api.applyCleanup.mockImplementation((changes, confirm) => Promise.resolve({ applied: confirm, changes: changes.map((c: object) => ({ ...c, before: null })) }));
  render(<QueryClientProvider client={new QueryClient()}><ProductCleanup skus={[{ id: "s1", sku_code: "SHIRT-A" }]} /></QueryClientProvider>);
  await userEvent.click(screen.getByText("Review product cleanup"));
  await userEvent.click(screen.getByLabelText("SHIRT-A"));
  await userEvent.click(screen.getByRole("button", { name: "Suggest cleanup" }));
  expect(await screen.findByText("AI-generated suggestions")).toBeInTheDocument();
  expect(api.applyCleanup).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "Preview selected changes" }));
  await userEvent.click(await screen.findByRole("button", { name: "Apply reviewed changes" }));
  await waitFor(() => expect(api.applyCleanup).toHaveBeenLastCalledWith([{ sku_id: "s1", field: "size", value: "XL", revision: "v1" }], true));
});
