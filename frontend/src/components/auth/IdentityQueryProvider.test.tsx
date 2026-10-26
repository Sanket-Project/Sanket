import { act, render, screen, waitFor } from "@testing-library/react";
import { useQuery } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { IdentityQueryProvider } from "@/components/auth/IdentityQueryProvider";
import { useAuthStore } from "@/stores/auth";

// Deep audit F1: one module-level QueryClient served account A's cached rows to
// account B whenever the query key matched (e.g. ['decisions', 'fashion', 'open']).

function signIn(tenantId: string, userId: string) {
  useAuthStore.setState({ isAuthenticated: true, tenantId, userId, industry: "fashion" });
}

function OpenDecisions({ fetcher }: { fetcher: () => Promise<string[]> }) {
  const { data } = useQuery({
    queryKey: ["decisions", "fashion", "open"],
    queryFn: fetcher,
    staleTime: 30_000,
  });
  return <ul>{(data ?? []).map((row) => <li key={row}>{row}</li>)}</ul>;
}

describe("IdentityQueryProvider", () => {
  beforeEach(() => {
    useAuthStore.setState({ isAuthenticated: false, tenantId: null, userId: null, industry: null });
  });

  it("does not serve account A's cached data to account B in the same industry", async () => {
    signIn("tenant-a", "user-a");
    const fetcher = vi.fn()
      .mockResolvedValueOnce(["A-private-row"])
      .mockResolvedValueOnce(["B-row"]);
    render(<IdentityQueryProvider><OpenDecisions fetcher={fetcher} /></IdentityQueryProvider>);
    expect(await screen.findByText("A-private-row")).toBeInTheDocument();

    act(() => signIn("tenant-b", "user-b"));

    expect(await screen.findByText("B-row")).toBeInTheDocument();
    expect(screen.queryByText("A-private-row")).not.toBeInTheDocument();
    expect(fetcher).toHaveBeenCalledTimes(2);
  });

  it("drops an in-flight response that belongs to the previous identity", async () => {
    signIn("tenant-a", "user-a");
    let resolveA: (rows: string[]) => void = () => {};
    const fetcher = vi.fn()
      .mockImplementationOnce(() => new Promise<string[]>((resolve) => { resolveA = resolve; }))
      .mockResolvedValueOnce(["B-row"]);
    render(<IdentityQueryProvider><OpenDecisions fetcher={fetcher} /></IdentityQueryProvider>);
    await waitFor(() => expect(fetcher).toHaveBeenCalledTimes(1));

    act(() => signIn("tenant-b", "user-b"));
    await act(async () => resolveA(["A-late-row"]));

    expect(await screen.findByText("B-row")).toBeInTheDocument();
    expect(screen.queryByText("A-late-row")).not.toBeInTheDocument();
  });

  it("clears previous-session data on sign-out", async () => {
    signIn("tenant-a", "user-a");
    const fetcher = vi.fn().mockResolvedValueOnce(["A-private-row"]).mockResolvedValue([]);
    render(<IdentityQueryProvider><OpenDecisions fetcher={fetcher} /></IdentityQueryProvider>);
    expect(await screen.findByText("A-private-row")).toBeInTheDocument();

    act(() => useAuthStore.setState({ isAuthenticated: false, tenantId: null, userId: null }));

    await waitFor(() => expect(screen.queryByText("A-private-row")).not.toBeInTheDocument());
  });

  it("keeps the cache for the same identity across unrelated store updates", async () => {
    signIn("tenant-a", "user-a");
    const fetcher = vi.fn().mockResolvedValue(["A-row"]);
    render(<IdentityQueryProvider><OpenDecisions fetcher={fetcher} /></IdentityQueryProvider>);
    expect(await screen.findByText("A-row")).toBeInTheDocument();

    act(() => useAuthStore.setState({ fullName: "Renamed" }));

    expect(screen.getByText("A-row")).toBeInTheDocument();
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
