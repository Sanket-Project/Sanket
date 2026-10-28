import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { ManagementReport } from "./ManagementReport";
import { SupplierDraft } from "./SupplierDraft";
import { useAuthStore } from "@/stores/auth";

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock("@/api/client", () => ({ apiClient: api }));
vi.mock("@/hooks/useCommunicationPreferences", () => ({ useCommunicationPreferences: () => ({ data: { preferences: { language: "en" } } }) }));
const renderInScope = (element: React.ReactNode) => render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{element}</QueryClientProvider>);

beforeEach(() => { vi.clearAllMocks(); useAuthStore.setState({ role: "admin" }); });

it("requires preview and explicit report-email confirmation", async () => {
  api.post.mockResolvedValueOnce({ data: { report: { snapshot: "s1", as_of: "2026-10-27", label: "Factual report" },
    subject: "ROI report", body: "No observed savings", preview_token: "bound-token", language: "en" } }).mockResolvedValueOnce({ data: { state: "unavailable" } });
  renderInScope(<ManagementReport windowDays={90} />);
  expect(screen.queryByRole("button", { name: "Confirm and send email" })).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Review report email" }));
  await userEvent.type(await screen.findByLabelText("Verified recipient email"), "synthetic@example.test");
  expect(api.post).toHaveBeenCalledTimes(1);
  await userEvent.click(screen.getByLabelText(/I reviewed/));
  await userEvent.click(screen.getByRole("button", { name: "Confirm and send email" }));
  await waitFor(() => expect(api.post).toHaveBeenCalledWith("/management/roi/email", expect.objectContaining({ confirm: true, preview_token: "bound-token", recipient: "synthetic@example.test", window_days: 90 }), expect.objectContaining({ signal: expect.any(AbortSignal) })));
  expect(await screen.findByRole("status")).toHaveTextContent("Email delivery unavailable");
});

it("does not send a supplier email when a draft is generated or edited", async () => {
  api.post.mockResolvedValue({ data: { subject: "Order TEST", body: "37 units", whatsapp_text: "37 units", quantity: 37,
    currency: "INR", revision: "r1", preview_token: "p1", label: "Factual template", language: "en", source: "/workspace/decisions" } });
  renderInScope(<SupplierDraft decisionId="d1" />);
  await userEvent.click(screen.getByRole("button", { name: "Prepare supplier draft" }));
  const body = await screen.findByLabelText("Message body");
  await userEvent.type(body, " - reviewed");
  expect(api.post).toHaveBeenCalledTimes(1);
  expect(screen.getByText(/User-edited draft/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Confirm and send email" })).toBeDisabled();
});

it("clears a reviewed report when the selected reporting period changes", async () => {
  api.post.mockResolvedValue({ data: { report: { snapshot: "s1", as_of: "2026-10-27", label: "Factual report" }, subject: "Report", body: "Body", preview_token: "token", language: "en" } });
  const view = renderInScope(<ManagementReport windowDays={90} />);
  await userEvent.click(screen.getByRole("button", { name: "Review report email" }));
  await screen.findByLabelText("Message body");
  view.rerender(<QueryClientProvider client={new QueryClient()}><ManagementReport windowDays={30} /></QueryClientProvider>);
  expect(screen.queryByLabelText("Message body")).not.toBeInTheDocument();
});

it("discards a PDF download that finishes after switching the report context", async () => {
  let finish!: (value: { data: Blob }) => void;
  api.get.mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
  const previous = Object.getOwnPropertyDescriptor(URL, "createObjectURL");
  const createObjectURL = vi.fn(() => "blob:synthetic");
  Object.defineProperty(URL, "createObjectURL", { configurable: true, value: createObjectURL });
  const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  try {
    const view = renderInScope(<ManagementReport windowDays={90} />);
    await userEvent.click(screen.getByRole("button", { name: "Download ROI PDF" }));
    view.rerender(<QueryClientProvider client={new QueryClient()}><ManagementReport windowDays={30} /></QueryClientProvider>);
    await act(async () => { finish({ data: new Blob(["synthetic PDF"]) }); });
    expect(createObjectURL).not.toHaveBeenCalled();
    expect(click).not.toHaveBeenCalled();
  } finally {
    click.mockRestore();
    if (previous) Object.defineProperty(URL, "createObjectURL", previous);
    else Reflect.deleteProperty(URL, "createObjectURL");
  }
});
