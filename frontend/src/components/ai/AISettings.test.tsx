import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { AISettings } from "./AISettings";

const api = vi.hoisted(() => ({ settings: vi.fn(), saveSettings: vi.fn() }));
vi.mock("@/api/ai", () => ({ aiApi: api }));

it("requires explicit permissions and sends only the reviewed settings", async () => {
  const settings = { enabled: false, sharing: "headers_only", tasks: { import_mapping: false }, aggregate_context: false, product_names: false, can_manage: true };
  api.settings.mockResolvedValue(settings);
  api.saveSettings.mockResolvedValue({ ...settings, enabled: true });
  render(<QueryClientProvider client={new QueryClient()}><AISettings /></QueryClientProvider>);
  const enabled = await screen.findByLabelText("Enable AI in this workspace");
  expect(enabled).not.toBeChecked();
  expect(screen.getByLabelText(/Share aggregate/)).not.toBeChecked();
  await userEvent.click(enabled);
  await userEvent.click(screen.getByRole("button", { name: "Save AI settings" }));
  await waitFor(() => expect(api.saveSettings).toHaveBeenCalledWith({ enabled: true, sharing: "headers_only", tasks: { import_mapping: false }, aggregate_context: false, product_names: false }));
});

it("does not expose controls for features that are not built yet", async () => {
  api.settings.mockResolvedValue({ enabled: false, sharing: "headers_only", tasks: { import_mapping: false, data_qa_plan: false },
    aggregate_context: false, product_names: false, can_manage: true });
  render(<QueryClientProvider client={new QueryClient()}><AISettings /></QueryClientProvider>);
  await screen.findByLabelText("Enable AI in this workspace");
  expect(screen.queryByLabelText("data qa plan")).not.toBeInTheDocument();
});

it("exposes the implemented explanation controls with readable labels", async () => {
  api.settings.mockResolvedValue({ enabled: false, sharing: "headers_only", tasks: { decision_explanation: false, alert_explanation: false, planning_brief: false, industry_advice: false }, aggregate_context: false, product_names: false, can_manage: true });
  render(<QueryClientProvider client={new QueryClient()}><AISettings /></QueryClientProvider>);
  expect(await screen.findByLabelText("Decision explanations")).not.toBeChecked();
  expect(screen.getByLabelText("Alert and anomaly explanations")).not.toBeChecked();
});

it("exposes regional report and interactive task controls by their product names", async () => {
  api.settings.mockResolvedValue({ enabled: false, sharing: "headers_only", tasks: { weekly_summary: false,
    roi_report: false, supplier_draft: false, scenario_interpretation: false, scenario_explanation: false,
    data_qa_plan: false, data_qa_answer: false }, aggregate_context: false, product_names: false, can_manage: true });
  render(<QueryClientProvider client={new QueryClient()}><AISettings /></QueryClientProvider>);
  expect(await screen.findByLabelText("Weekly email summaries")).not.toBeChecked();
  expect(screen.getByLabelText("ROI report summaries")).not.toBeChecked();
  expect(screen.getByLabelText("Supplier draft summaries")).not.toBeChecked();
  expect(screen.getByLabelText("Natural-language scenarios")).not.toBeChecked();
  expect(screen.getByLabelText("Read-only data questions")).not.toBeChecked();
});
