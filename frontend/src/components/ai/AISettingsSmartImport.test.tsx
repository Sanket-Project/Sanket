import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { AISettings } from "./AISettings";

const api = vi.hoisted(() => ({ settings: vi.fn(), saveSettings: vi.fn() }));
vi.mock("@/api/ai", () => ({ aiApi: api }));

it("offers a switch for smart import planning", async () => {
  api.settings.mockResolvedValue({ enabled: true, sharing: "headers_only", tasks: { import_mapping: true, import_plan: false },
    aggregate_context: false, product_names: false, can_manage: true });
  render(<QueryClientProvider client={new QueryClient()}><AISettings /></QueryClientProvider>);
  expect(await screen.findByLabelText("Smart import planning (multiple files)")).not.toBeChecked();
});
