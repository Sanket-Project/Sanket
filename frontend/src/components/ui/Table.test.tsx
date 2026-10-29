// src/components/ui/Table.test.tsx
import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { Table, type Column } from "./Table";

type Row = { id: string; name: string; qty: number | null };
const rows: Row[] = [{ id: "a", name: "Tee", qty: 5 }, { id: "b", name: "Dress", qty: null }, { id: "c", name: "Jacket", qty: 12 }];
const cols: Column<Row>[] = [
  { key: "name", header: "Product", render: (r) => r.name, sortValue: (r) => r.name, priority: "primary" },
  { key: "qty", header: "Qty", render: (r) => r.qty ?? "—", sortValue: (r) => r.qty, align: "right" },
];
const names = () => screen.getAllByRole("row").slice(1).map((r) => within(r).getAllByRole("cell")[0].textContent);

afterEach(() => {
  // @ts-expect-error reset jsdom
  delete window.matchMedia;
});

it("sorts by a column, toggles direction, keeps nulls last, and sets aria-sort", () => {
  render(<Table data={rows} columns={cols} rowKey={(r) => r.id} />);
  const qty = screen.getByRole("button", { name: "Qty" });
  fireEvent.click(qty);
  expect(names()).toEqual(["Tee", "Jacket", "Dress"]);
  expect(screen.getByRole("columnheader", { name: /Qty/ })).toHaveAttribute("aria-sort", "ascending");
  fireEvent.click(qty);
  expect(names()).toEqual(["Jacket", "Tee", "Dress"]);
  expect(screen.getByRole("columnheader", { name: /Qty/ })).toHaveAttribute("aria-sort", "descending");
});

it("leaves non-sortable headers as plain text", () => {
  render(<Table data={rows} columns={[{ key: "n", header: "Name", render: (r) => r.name }]} rowKey={(r) => r.id} />);
  expect(screen.queryByRole("button", { name: "Name" })).not.toBeInTheDocument();
});

it("renders skeleton rows while loading instead of the empty message", () => {
  render(<Table data={[]} columns={cols} rowKey={(r) => r.id} loading loadingRows={3} empty="Nothing" />);
  expect(screen.getByRole("table")).toHaveAttribute("aria-busy", "true");
  expect(screen.getAllByRole("row")).toHaveLength(4);
  expect(screen.queryByText("Nothing")).not.toBeInTheDocument();
});

it("exposes a caption for screen readers", () => {
  render(<Table data={rows} columns={cols} rowKey={(r) => r.id} caption="Top products" />);
  expect(screen.getByRole("table", { name: "Top products" })).toBeInTheDocument();
});

it("selects rows and all rows through labelled checkboxes", () => {
  const onChange = vi.fn();
  render(<Table data={rows} columns={cols} rowKey={(r) => r.id} selection={{ selected: new Set(["a"]), onChange, label: (r) => r.name }} />);
  fireEvent.click(screen.getByRole("checkbox", { name: "Select Dress" }));
  expect([...onChange.mock.calls[0][0]].sort()).toEqual(["a", "b"]);
  fireEvent.click(screen.getByRole("checkbox", { name: "Select all rows" }));
  expect([...onChange.mock.calls[1][0]].sort()).toEqual(["a", "b", "c"]);
});

it("renders rows as cards on small screens when mobile='cards'", () => {
  window.matchMedia = vi.fn().mockImplementation((q: string) => ({ matches: q.includes("max-width"), media: q, addEventListener: vi.fn(), removeEventListener: vi.fn() })) as unknown as typeof window.matchMedia;
  render(<Table data={rows} columns={cols} rowKey={(r) => r.id} mobile="cards" caption="Top products" />);
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
  const list = screen.getByRole("list", { name: "Top products" });
  expect(within(list).getAllByRole("listitem")).toHaveLength(3);
  expect(within(list).getByText("Jacket")).toBeInTheDocument();
});
