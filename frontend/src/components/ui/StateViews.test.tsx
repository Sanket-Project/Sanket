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
