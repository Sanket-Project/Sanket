import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { DataQualityPage } from "./DataQuality";

const api = vi.hoisted(() => ({ report: vi.fn(), fix: vi.fn() }));
vi.mock("@/api/dataQuality", () => ({ dataQualityApi: api }));
vi.mock("@/hooks/useWorkspaceIndustry", () => ({ useWorkspaceIndustry: () => "fashion" }));
vi.mock("react-hot-toast", () => ({ default: { success: vi.fn(), error: vi.fn() } }));

it("binds confirmed fixes to the reviewed preview token", async () => {
  api.report.mockResolvedValue({ health_score: 80, grade: "Review", checks_run: 12, issues_found: 1, critical: 0, warnings: 1,
    fixable_automatically: ["dedupe_sales"], findings: [{ key: "duplicates", label: "Duplicated sales", severity: "warning", count: 2,
      why_it_matters: "Double-counts sales", how_to_fix: "Remove identical copies", sample: [], autofix: "dedupe_sales" }] });
  api.fix.mockResolvedValue({ action: "dedupe_sales", rows_affected: 1, applied: false, preview_token: "bound-preview" });
  render(<QueryClientProvider client={new QueryClient()}><MemoryRouter><DataQualityPage /></MemoryRouter></QueryClientProvider>);
  await userEvent.click(await screen.findByRole("button", { name: /Review auto-fix/i }));
  await userEvent.click(await screen.findByRole("button", { name: "Delete rows" }));
  await waitFor(() => expect(api.fix).toHaveBeenLastCalledWith("dedupe_sales", true, "bound-preview"));
});
