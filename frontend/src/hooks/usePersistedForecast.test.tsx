import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, expect, it, vi } from "vitest";

const api = vi.hoisted(() => ({ latest: vi.fn(), refresh: vi.fn() }));
vi.mock("@/api/forecasts", () => ({ forecastsApi: api }));
vi.mock("@/hooks/useWorkspaceIndustry", () => ({ useWorkspaceIndustry: () => "fashion" }));
import { usePersistedForecast } from "@/hooks/usePersistedForecast";

const saved = { run_id: "saved", rows: [{ sku_id: "a", forecast_date: "2026-10-26", p10: 1, p50: 2, p90: 3 }],
  completed_at: "2026-10-26T00:00:00Z", horizon_weeks: 12, age_seconds: 7200, total_skus: 25000 };
const queued = { id: "job", status: "pending", industry: "fashion", horizon_weeks: 12 };
const wrapper = ({ children }: { children: ReactNode }) => <QueryClientProvider client={new QueryClient({
  defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
})}>{children}</QueryClientProvider>;

beforeEach(() => { vi.resetAllMocks(); });

it("reads saved results before requesting background refresh, without waiting for inference", async () => {
  api.latest.mockResolvedValue({ forecast: saved, refresh: null, stale: true });
  api.refresh.mockReturnValue(new Promise(() => {}));
  const { result } = renderHook(() => usePersistedForecast({ horizon: 12, view: "summary" }), { wrapper });
  await waitFor(() => expect(result.current.data?.run_id).toBe("saved"));
  expect(api.latest).toHaveBeenCalledWith({ view: "summary", offset: 0, limit: 6 });
  await waitFor(() => expect(api.refresh).toHaveBeenCalledWith({ horizon: 12, force: false, force_zero_shot: true }));
  expect(result.current.refreshing).toBe(true);
});

it("does not enqueue on every read of a fresh run", async () => {
  api.latest.mockResolvedValue({ forecast: saved, refresh: null, stale: false });
  const { result } = renderHook(() => usePersistedForecast({ horizon: 12 }), { wrapper });
  await waitFor(() => expect(result.current.data).toBe(saved));
  expect(api.refresh).not.toHaveBeenCalled();
});

it("keeps saved forecast when refresh fails and allows an explicit retry", async () => {
  api.latest.mockResolvedValue({ forecast: saved, refresh: null, stale: true });
  api.refresh.mockRejectedValue(new Error("Queue unavailable"));
  const { result } = renderHook(() => usePersistedForecast({ horizon: 12 }), { wrapper });
  await waitFor(() => expect(result.current.refreshError).toContain("Queue unavailable"));
  expect(result.current.data?.run_id).toBe("saved");
  expect(api.refresh).toHaveBeenCalledTimes(1);
  api.refresh.mockResolvedValue({ refresh: queued, stale: true });
  await act(async () => result.current.requestRefresh());
  expect(api.refresh).toHaveBeenLastCalledWith({ horizon: 12, force: true, force_zero_shot: true });
});

it("does not claim first generation started before enqueue succeeds", async () => {
  api.latest.mockResolvedValue({ forecast: null, refresh: null, stale: true });
  api.refresh.mockRejectedValue(new Error("Worker queue offline"));
  const { result } = renderHook(() => usePersistedForecast({ horizon: 12 }), { wrapper });
  await waitFor(() => expect(result.current.refreshError).toContain("Worker queue offline"));
  expect(result.current.refreshing).toBe(false);
  expect(result.current.data).toBeNull();
});

it("requests server pages without downloading the entire catalog", async () => {
  api.latest.mockResolvedValue({ forecast: saved, refresh: null, stale: false });
  const { result } = renderHook(() => usePersistedForecast({ horizon: 12, offset: 24996, runId: "saved" }), { wrapper });
  await waitFor(() => expect(result.current.data?.total_skus).toBe(25000));
  expect(api.latest).toHaveBeenCalledWith({ view: "skus", offset: 24996, limit: 6, run_id: "saved" });
});

it("requests a missing location split without discarding a fresh saved forecast", async () => {
  api.latest.mockResolvedValue({ forecast: { ...saved, location_status: "pending" }, refresh: null, stale: false });
  api.refresh.mockResolvedValue({ refresh: queued, stale: false });
  const { result } = renderHook(() => usePersistedForecast({ horizon: 12 }), { wrapper });
  await waitFor(() => expect(api.refresh).toHaveBeenCalledOnce());
  expect(result.current.data?.run_id).toBe("saved");
});

it("polls the accepted job until the newly persisted result replaces the old run", async () => {
  api.latest.mockResolvedValueOnce({ forecast: saved, refresh: null, stale: true })
    .mockResolvedValueOnce({ forecast: saved, refresh: queued, stale: true })
    .mockResolvedValue({ forecast: { ...saved, run_id: "new-run" }, refresh: { ...queued, status: "completed" }, stale: false });
  api.refresh.mockResolvedValue({ refresh: queued, stale: true });
  const { result } = renderHook(() => usePersistedForecast({ horizon: 12 }), { wrapper });
  await waitFor(() => expect(result.current.data?.run_id).toBe("new-run"), { timeout: 5000 });
  expect(result.current.refreshing).toBe(false);
  expect(api.refresh).toHaveBeenCalledOnce();
});

it("requests a longer horizon while retaining the saved run's actual horizon", async () => {
  api.latest.mockResolvedValue({ forecast: saved, refresh: null, stale: false });
  api.refresh.mockResolvedValue({ refresh: queued, stale: true });
  const { result, rerender } = renderHook(({ horizon }) => usePersistedForecast({ horizon }), { wrapper, initialProps: { horizon: 12 } });
  await waitFor(() => expect(result.current.data?.horizon_weeks).toBe(12));
  expect(api.refresh).not.toHaveBeenCalled();
  rerender({ horizon: 26 });
  await waitFor(() => expect(api.refresh).toHaveBeenCalledWith({ horizon: 26, force: false, force_zero_shot: true }));
  expect(result.current.data?.horizon_weeks).toBe(12);
});

it.each(["fashion", "electronics"])("reconciles an old %s reservation without starting a different job", async (industry) => {
  const pending = { ...queued, industry, updated_at: new Date(Date.now() - 60000).toISOString() };
  api.latest.mockResolvedValue({ forecast: saved, refresh: pending, stale: true });
  api.refresh.mockResolvedValue({ refresh: pending, stale: true });
  const { result } = renderHook(() => usePersistedForecast({ horizon: 12 }), { wrapper });
  await waitFor(() => expect(api.refresh).toHaveBeenCalledOnce());
  expect(api.refresh).toHaveBeenCalledWith({ horizon: 12, force: false, force_zero_shot: true });
  expect(result.current.data?.run_id).toBe("saved");
});

it("reevaluates an unchanged pending payload as its reservation ages", async () => {
  const now = Date.now();
  const pending = { ...queued, updated_at: new Date(now).toISOString() };
  api.latest.mockResolvedValue({ forecast: null, refresh: pending, stale: true });
  api.refresh.mockResolvedValue({ refresh: pending, stale: true });
  const { result } = renderHook(() => usePersistedForecast({ horizon: 12 }), { wrapper });
  await waitFor(() => expect(result.current.refreshStatus?.id).toBe("job"));
  expect(api.refresh).not.toHaveBeenCalled();
  const clock = vi.spyOn(Date, "now").mockReturnValue(now + 35000);
  try {
    await act(async () => { await result.current.refetch(); });
    await waitFor(() => expect(api.refresh).toHaveBeenCalledOnce());
  } finally {
    clock.mockRestore();
  }
});

it("queues the desired industry after a competing tenant-wide run releases its slot", async () => {
  let phase: "initial" | "foreign" | "released" | "own" = "initial";
  const foreign = { ...queued, id: "electronics-job", industry: "electronics", status: "running" };
  api.latest.mockImplementation(async () => ({ forecast: null, stale: true,
    refresh: phase === "foreign" ? foreign : phase === "own" ? queued
      : phase === "released" ? { ...queued, id: "old-failed", status: "failed", error: "Earlier failure" } : null }));
  api.refresh.mockImplementation(async () => {
    if (phase === "initial") {
      phase = "foreign";
      return { refresh: foreign, stale: true };
    }
    phase = "own";
    return { refresh: queued, stale: true };
  });
  const { result } = renderHook(() => usePersistedForecast({ horizon: 12 }), { wrapper });
  await waitFor(() => expect(result.current.refreshStatus?.id).toBe("electronics-job"));
  expect(api.refresh).toHaveBeenCalledOnce();
  phase = "released";
  await act(async () => { await result.current.refetch(); });
  await waitFor(() => expect(api.refresh).toHaveBeenCalledTimes(2));
  expect(api.refresh).toHaveBeenLastCalledWith({ horizon: 12, force: false, force_zero_shot: true });
  expect(result.current.refreshStatus?.id).toBe("job");
});

it("does not describe another industry's active run as this industry's generation", async () => {
  api.latest.mockResolvedValue({ forecast: null, stale: true,
    refresh: { ...queued, industry: "electronics", status: "running" } });
  const { result } = renderHook(() => usePersistedForecast({ horizon: 12 }), { wrapper });
  await waitFor(() => expect(result.current.refreshStatus?.industry).toBe("electronics"));
  expect(result.current.generating).toBe(false);
  expect(result.current.waitingForOtherIndustry).toBe(true);
  expect(api.refresh).not.toHaveBeenCalled();
});

it("preserves a manual force-refresh of fresh data while another industry holds the slot", async () => {
  let phase: "initial" | "foreign" | "released" | "own" = "initial";
  const foreign = { ...queued, id: "electronics-job", industry: "electronics", status: "running" };
  api.latest.mockImplementation(async () => ({ forecast: saved, stale: false,
    refresh: phase === "foreign" ? foreign : phase === "own" ? queued : null }));
  api.refresh.mockImplementation(async () => {
    if (phase === "initial") {
      phase = "foreign";
      return { refresh: foreign, stale: true };
    }
    phase = "own";
    return { refresh: queued, stale: false };
  });
  const { result } = renderHook(() => usePersistedForecast({ horizon: 12 }), { wrapper });
  await waitFor(() => expect(result.current.data?.run_id).toBe("saved"));
  await act(async () => result.current.requestRefresh());
  await waitFor(() => expect(result.current.refreshStatus?.id).toBe("electronics-job"));
  phase = "released";
  await act(async () => { await result.current.refetch(); });
  await waitFor(() => expect(api.refresh).toHaveBeenCalledTimes(2));
  expect(api.refresh).toHaveBeenLastCalledWith({ horizon: 12, force: true, force_zero_shot: true });
});

it("upgrades a deferred automatic request when the user explicitly forces refresh", async () => {
  let busy = true;
  const foreign = { ...queued, id: "electronics-job", industry: "electronics", status: "running" };
  api.latest.mockResolvedValue({ forecast: null, refresh: null, stale: true });
  api.refresh.mockImplementation(async () => {
    api.latest.mockResolvedValue({ forecast: null, refresh: busy ? foreign : queued, stale: true });
    return { refresh: busy ? foreign : queued, stale: true };
  });
  const { result } = renderHook(() => usePersistedForecast({ horizon: 12 }), { wrapper });
  await waitFor(() => expect(result.current.waitingForOtherIndustry).toBe(true));
  expect(api.refresh).toHaveBeenLastCalledWith({ horizon: 12, force: false, force_zero_shot: true });
  await act(async () => result.current.requestRefresh());
  await waitFor(() => expect(api.refresh).toHaveBeenCalledTimes(2));
  busy = false;
  api.latest.mockResolvedValue({ forecast: null, refresh: null, stale: true });
  await act(async () => { await result.current.refetch(); });
  await waitFor(() => expect(api.refresh).toHaveBeenCalledTimes(3));
  expect(api.refresh).toHaveBeenLastCalledWith({ horizon: 12, force: true, force_zero_shot: true });
});
