import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { FilterBar } from "./FilterBar";

it("groups filters and offers clear only when filters are active", () => {
  const onClear = vi.fn();
  const { rerender } = render(<FilterBar label="Inventory filters" filters={<input aria-label="Search" />} actions={<button>Export</button>} activeCount={0} onClear={onClear} />);
  expect(screen.getByRole("group", { name: "Inventory filters" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Clear filters/ })).not.toBeInTheDocument();
  rerender(<FilterBar label="Inventory filters" filters={<input aria-label="Search" />} activeCount={2} onClear={onClear} />);
  fireEvent.click(screen.getByRole("button", { name: "Clear filters (2)" }));
  expect(onClear).toHaveBeenCalledOnce();
});
