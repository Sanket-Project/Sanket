import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { Modal } from "./Modal";

it("exposes an open dialog and its controls to assistive technology", () => {
  render(<Modal open onClose={vi.fn()} title="Import sales">
    <label><input type="radio" />Weekly totals</label>
    <button>Import</button>
  </Modal>);
  expect(screen.getByRole("dialog", { name: "Import sales" })).toBeInTheDocument();
  expect(screen.getByRole("radio", { name: "Weekly totals" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Import" })).toBeInTheDocument();
});
