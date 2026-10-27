import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { ImportFormats } from "./ImportFormats";

const api = vi.hoisted(() => ({ importFormats: vi.fn(), manageFormat: vi.fn() }));
vi.mock("@/api/ai", () => ({ aiApi: api }));
it("disables only the selected reviewed format revision", async () => {
  api.importFormats.mockResolvedValue([{ id: "format-1", kind: "sales", fingerprint: "abcd", revision: 2, disabled: false }]);
  api.manageFormat.mockResolvedValue({ updated: true });
  render(<QueryClientProvider client={new QueryClient()}><ImportFormats /></QueryClientProvider>);
  await userEvent.click(await screen.findByRole("button", { name: "Disable format" }));
  await waitFor(() => expect(api.manageFormat).toHaveBeenCalledWith("format-1", 2, true));
});
