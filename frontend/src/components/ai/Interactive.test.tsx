import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useAuthStore } from "@/stores/auth";

const api = vi.hoisted(() => ({ interpret: vi.fn(), question: vi.fn() }));
vi.mock("@/hooks/useCommunicationPreferences", () => ({ useCommunicationPreferences: () => ({ data: { preferences: { language: "te" } } }) }));
vi.mock("@/api/aiInteractive", () => ({ aiInteractiveApi: api }));
import { ScenarioAssistant } from "./ScenarioAssistant";
import { DataChat } from "./DataChat";

describe("interactive AI review boundaries", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({ tenantId: "workspace-a", userId: "user-a", isAuthenticated: true });
  });

  it("requires reviewing and applying assumptions; interpretation never applies or simulates", async () => {
    api.interpret.mockResolvedValue({ state: "success", assumptions: { demand_shock_pct: 20 }, evidence: [{ field: "demand_shock_pct", span: "Demand increases by 20%", value: 20 }], unresolved: [] });
    const onApply = vi.fn();
    render(<ScenarioAssistant onApply={onApply} />);
    await userEvent.type(screen.getByRole("textbox", { name: "Describe a scenario" }), "Demand increases by 20%");
    await userEvent.click(screen.getByRole("button", { name: "Interpret assumptions" }));
    await screen.findByRole("spinbutton", { name: "Demand change (%)" });
    expect(onApply).not.toHaveBeenCalled();
    expect(api.interpret.mock.calls[0][2]).toBe("te");
    await userEvent.clear(screen.getByRole("spinbutton", { name: "Demand change (%)" }));
    await userEvent.type(screen.getByRole("spinbutton", { name: "Demand change (%)" }), "15");
    await userEvent.click(screen.getByRole("button", { name: "Apply reviewed assumptions" }));
    expect(onApply).toHaveBeenCalledWith({ demand_shock_pct: 15 });
  });

  it("clears scenario interpretation when workspace changes", async () => {
    let resolve!: (value: unknown) => void;
    api.interpret.mockReturnValue(new Promise((r) => { resolve = r; }));
    render(<ScenarioAssistant onApply={vi.fn()} />);
    await userEvent.type(screen.getByRole("textbox", { name: "Describe a scenario" }), "Demand increases by 20%");
    await userEvent.click(screen.getByRole("button", { name: "Interpret assumptions" }));
    act(() => useAuthStore.setState({ tenantId: "workspace-b" }));
    resolve({ state: "success", assumptions: { demand_shock_pct: 20 }, evidence: [{ field: "demand_shock_pct", span: "Old workspace secret", value: 20 }], unresolved: [] });
    await waitFor(() => expect(screen.queryByText("Old workspace secret")).not.toBeInTheDocument());
  });

  it("keeps chat only in the current identity and renders every safe citation", async () => {
    api.question.mockResolvedValue({ state: "success", blocks: [{ text: "Available units: 17.", kind: "fact", sources: [{ fact_id: "stock", href: "/inventory" }, { fact_id: "forecast", href: "/forecasts" }] }] });
    render(<DataChat />);
    await userEvent.click(screen.getByText("Sanket AI"));
    await userEvent.type(screen.getByRole("textbox", { name: "Question about your data" }), "How much stock?");
    await userEvent.click(screen.getByRole("button", { name: "Ask question" }));
    await screen.findByText("Available units: 17.");
    expect(screen.getByRole("link", { name: "Source: inventory" })).toHaveAttribute("href", "/workspace/inventory");
    expect(screen.getByRole("link", { name: "Source: forecasts" })).toHaveAttribute("href", "/workspace/forecasts");
    act(() => useAuthStore.setState({ tenantId: "workspace-b" }));
    await waitFor(() => expect(screen.queryByText("Available units: 17.")).not.toBeInTheDocument());
  });

  it("allows cancellation and never exposes an unsafe source URL", async () => {
    let resolve!: (value: unknown) => void;
    api.question.mockReturnValue(new Promise((r) => { resolve = r; }));
    render(<DataChat />);
    await userEvent.click(screen.getByText("Sanket AI"));
    await userEvent.type(screen.getByRole("textbox", { name: "Question about your data" }), "Inventory?");
    await userEvent.click(screen.getByRole("button", { name: "Ask question" }));
    await userEvent.click(screen.getByRole("button", { name: "Cancel question" }));
    resolve({ state: "success", blocks: [{ text: "Late answer", sources: [{ href: "https://evil.test" }] }] });
    await waitFor(() => expect(screen.queryByText("Late answer")).not.toBeInTheDocument());
  });

  it.each([
    ["disabled", "feature_disabled", "Sanket AI is turned off for this workspace. An owner or admin can enable data questions in Settings > AI assistance."],
    ["policy_blocked", "sharing_disabled", "Data questions require aggregate data sharing. An owner or admin can enable it in Settings > AI assistance."],
  ])("explains %s instead of hiding the cause", async (state, reason, message) => {
    api.question.mockResolvedValue({ state, reason, blocks: [] });
    render(<DataChat />);
    await userEvent.click(screen.getByText("Sanket AI"));
    await userEvent.type(screen.getByRole("textbox", { name: "Question about your data" }), "How much stock?");
    await userEvent.click(screen.getByRole("button", { name: "Ask question" }));
    await screen.findByText(message);
  });
});
