import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { Button } from "./Button";
import { Input } from "./Input";
import { Table } from "./Table";

it("announces a pending action and prevents duplicate submissions", () => {
  const submit = vi.fn();
  render(<Button loading onClick={submit}>Save changes</Button>);
  const button = screen.getByRole("button", { name: "Save changes" });
  expect(button).toHaveAttribute("aria-busy", "true");
  fireEvent.click(button);
  expect(submit).not.toHaveBeenCalled();
});

it("associates independently rendered field labels and help without caller IDs", () => {
  render(<><Input label="Workspace name" hint="Visible to your team" /><Input label="Display name" /></>);
  const field = screen.getByRole("textbox", { name: "Workspace name" });
  expect(field).toHaveAccessibleDescription("Visible to your team");
  expect(field.id).not.toBe(screen.getByRole("textbox", { name: "Display name" }).id);
});

it("keeps field validation and caller-provided descriptions available together", () => {
  render(<><p id="currency-help">Use the recorded currency</p><Input label="Currency" error="Choose a currency" aria-describedby="currency-help" /></>);
  expect(screen.getByRole("textbox", { name: "Currency" })).toHaveAccessibleDescription("Use the recorded currency Choose a currency");
});

it("lets keyboard users open a data row without also triggering it from nested actions", () => {
  const open = vi.fn();
  const edit = vi.fn();
  render(<Table data={[{ id: "sku-a" }]} rowKey={row => row.id} onRowClick={open}
    columns={[{ key: "sku", header: "SKU", render: row => row.id }, { key: "edit", header: "Actions", render: () => <button onClick={edit}>Edit SKU</button> }]} />);
  const row = screen.getByRole("row", { name: /sku-a/ });
  expect(row).toHaveAttribute("tabindex", "0");
  fireEvent.keyDown(row, { key: "Enter" });
  expect(open).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole("button", { name: "Edit SKU" }));
  expect(edit).toHaveBeenCalledTimes(1);
  expect(open).toHaveBeenCalledTimes(1);
});
