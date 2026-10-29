import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { ErrorState, LoadingState, QueryBoundary, UnavailableState } from "./StateViews";

it("announces loading politely", () => {
  render(<LoadingState label="Loading sales" />);
  expect(screen.getByRole("status")).toHaveTextContent("Loading sales");
});

it("offers a retry that calls back", () => {
  const onRetry = vi.fn();
  render(<ErrorState message="Server said no" onRetry={onRetry} />);
  expect(screen.getByRole("alert")).toHaveTextContent("Server said no");
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(onRetry).toHaveBeenCalledOnce();
});

it("states why data is unavailable", () => {
  render(<UnavailableState title="No branch breakdown" reason="Sales were imported without branch identifiers." />);
  expect(screen.getByText("No branch breakdown")).toBeInTheDocument();
  expect(screen.getByText(/without branch identifiers/)).toBeInTheDocument();
});

it("QueryBoundary renders loading, error, empty and data in turn", () => {
  const base = { data: undefined as number[] | undefined, isLoading: true, isError: false, refetch: vi.fn() };
  const view = (q: typeof base) => (
    <QueryBoundary query={q} isEmpty={(d) => d.length === 0} empty={<p>Nothing yet</p>}>
      {(d) => <p>{d.length} rows</p>}
    </QueryBoundary>
  );
  const { rerender } = render(view(base));
  expect(screen.getByRole("status")).toBeInTheDocument();
  rerender(view({ ...base, isLoading: false, isError: true }));
  expect(screen.getByRole("alert")).toBeInTheDocument();
  rerender(view({ ...base, isLoading: false, data: [] }));
  expect(screen.getByText("Nothing yet")).toBeInTheDocument();
  rerender(view({ ...base, isLoading: false, data: [0, 0] }));
  expect(screen.getByText("2 rows")).toBeInTheDocument();
});

it("QueryBoundary keeps cached data on a failed refresh and says so", () => {
  const refetch = vi.fn();
  render(
    <QueryBoundary query={{ data: [1, 2, 3], isLoading: false, isError: true, refetch }}>
      {(d) => <p>{d.length} rows</p>}
    </QueryBoundary>,
  );
  expect(screen.getByText("3 rows")).toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("Showing the last loaded data — refresh failed.");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(refetch).toHaveBeenCalledOnce();
});

it("QueryBoundary renders the idle slot for a disabled query, not an error", () => {
  render(
    <QueryBoundary query={{ data: undefined, isLoading: false, isError: false, status: "pending", fetchStatus: "idle" }} idle={<p>Pick a product first</p>}>
      {() => <p>data</p>}
    </QueryBoundary>,
  );
  expect(screen.getByText("Pick a product first")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

it("QueryBoundary error state retries through refetch", () => {
  const refetch = vi.fn();
  render(
    <QueryBoundary query={{ data: undefined, isLoading: false, isError: true, error: new Error("boom"), refetch }}>
      {() => <p>data</p>}
    </QueryBoundary>,
  );
  expect(screen.getByRole("alert")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(refetch).toHaveBeenCalledOnce();
});
