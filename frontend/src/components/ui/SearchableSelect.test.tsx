import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { SearchableSelect } from "./SearchableSelect";

const options = [
  { value: "", label: "All districts" },
  { value: "Hyderabad", label: "Hyderabad" },
  { value: "Adilabad", label: "Adilabad" },
];

function Picker() {
  const [value, setValue] = useState("");
  return <SearchableSelect label="District" value={value} options={options} onChange={setValue} />;
}

describe("SearchableSelect", () => {
  it("uses viewport space when main is content-sized rather than a scroll container", async () => {
    const user = userEvent.setup();
    render(<main><SearchableSelect label="District" value="" options={options} onChange={vi.fn()} /></main>);
    const bounds = (top: number, bottom: number) => ({top, bottom, height:bottom-top, left:20,right:300,width:280,x:20,y:top,toJSON:()=>({})});
    const height = vi.spyOn(window, "innerHeight", "get").mockReturnValue(700);
    const main = vi.spyOn(screen.getByRole("main"), "getBoundingClientRect").mockReturnValue(bounds(50,300));
    const trigger = vi.spyOn(screen.getByRole("combobox"), "getBoundingClientRect").mockReturnValue(bounds(200,244));
    await user.click(screen.getByRole("combobox"));
    expect(screen.getByRole("listbox").parentElement).toHaveAttribute("data-side", "bottom");
    height.mockRestore(); main.mockRestore(); trigger.mockRestore();
  });
  it("has a labelled combobox and filters options without changing selection", async () => {
    const user = userEvent.setup();
    render(<Picker />);
    await user.click(screen.getByRole("combobox", { name: "District" }));
    await user.type(screen.getByRole("searchbox", { name: "Search District" }), "hyd");
    expect(screen.getByRole("option", { name: "Hyderabad" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Adilabad" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("option", { name: "Hyderabad" }));
    expect(screen.getByRole("combobox", { name: "District" })).toHaveTextContent("Hyderabad");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("supports keyboard selection, Escape and returns focus to the control", async () => {
    const user = userEvent.setup();
    render(<Picker />);
    await user.click(screen.getByRole("combobox", { name: "District" }));
    await user.keyboard("{ArrowDown}{Enter}");
    expect(screen.getByRole("combobox", { name: "District" })).toHaveTextContent("Hyderabad");
    await user.click(screen.getByRole("combobox", { name: "District" }));
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "District" })).toHaveFocus();
  });

  it("dismisses on outside click and reports remote search and missing options", async () => {
    const user = userEvent.setup();
    const search = vi.fn();
    render(<><SearchableSelect label="Product" value="" options={[]} onChange={vi.fn()} onSearch={search} /><button>Outside</button></>);
    await user.click(screen.getByRole("combobox", { name: "Product" }));
    await user.type(screen.getByRole("searchbox"), "kurta");
    expect(search).toHaveBeenLastCalledWith("kurta");
    expect(screen.getByText("No matches found")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Outside" }));
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
  });

  it("opens above a low control without scrolling page ancestors and scrolls only its option list", async () => {
    const user = userEvent.setup();
    const scroll = vi.fn();
    const priorScroll = HTMLElement.prototype.scrollIntoView;
    HTMLElement.prototype.scrollIntoView = scroll;
    render(<SearchableSelect label="District" value="" options={options} onChange={vi.fn()} />);
    const control = screen.getByRole("combobox", { name: "District" });
    const position = vi.spyOn(control, "getBoundingClientRect").mockReturnValue({ top: 574, bottom: 644, height: 70, left: 20, right: 300, width: 280, x: 20, y: 574, toJSON: () => ({}) });
    await user.click(control);
    expect(screen.getByRole("listbox").parentElement).toHaveAttribute("data-side", "top");
    expect(screen.getByRole("listbox")).toHaveStyle({ maxHeight: "240px" });
    expect(scroll).not.toHaveBeenCalled();
    const listbox = screen.getByRole("listbox");
    Object.defineProperty(listbox, "clientHeight", { configurable: true, value: 80 });
    const last = screen.getByRole("option", { name: "Adilabad" });
    Object.defineProperties(last, { offsetTop: { configurable: true, value: 160 }, offsetHeight: { configurable: true, value: 40 } });
    await user.keyboard("{End}");
    expect(listbox.scrollTop).toBe(120);
    const first = screen.getByRole("option", { name: "All districts" });
    Object.defineProperties(first, { offsetTop: { configurable: true, value: 0 }, offsetHeight: { configurable: true, value: 40 } });
    await user.keyboard("{Home}");
    expect(listbox.scrollTop).toBe(0);
    await user.keyboard("{ArrowDown}");
    expect(scroll).not.toHaveBeenCalled();
    position.mockRestore();
    HTMLElement.prototype.scrollIntoView = priorScroll;
  });

  it("anchors to the trigger independently of its label and hint in a short viewport", async () => {
    const user = userEvent.setup();
    render(<SearchableSelect label="District" value="" options={options} onChange={vi.fn()} hint="All districts" />);
    const control = screen.getByRole("combobox", { name: "District" });
    const bounds = (top: number, bottom: number) => ({ top, bottom, height: bottom - top, left: 20, right: 300, width: 280, x: 20, y: top, toJSON: () => ({}) });
    const height = vi.spyOn(window, "innerHeight", "get").mockReturnValue(260);
    const controlRect = vi.spyOn(control, "getBoundingClientRect").mockReturnValue(bounds(150, 194));
    const rootRect = vi.spyOn(control.parentElement!, "getBoundingClientRect").mockReturnValue(bounds(124, 218));
    await user.click(control);
    expect(screen.getByRole("listbox")).toHaveStyle({ maxHeight: "86px" });
    height.mockRestore(); controlRect.mockRestore(); rootRect.mockRestore();
  });

  it("keeps an upward menu inside its scroll surface below the fixed header", async () => {
    const user = userEvent.setup();
    render(<main aria-label="Workspace" style={{ overflowY: "auto" }}><SearchableSelect label="District" value="" options={options} onChange={vi.fn()} /></main>);
    const bounds = (top: number, bottom: number) => ({ top, bottom, height: bottom - top, left: 20, right: 300, width: 280, x: 20, y: top, toJSON: () => ({}) });
    const height = vi.spyOn(window, "innerHeight", "get").mockReturnValue(500);
    const surface = vi.spyOn(screen.getByRole("main"), "getBoundingClientRect").mockReturnValue(bounds(70, 500));
    const field = vi.spyOn(screen.getByRole("combobox"), "getBoundingClientRect").mockReturnValue(bounds(300, 390));
    await user.click(screen.getByRole("combobox"));
    expect(screen.getByRole("listbox").parentElement).toHaveAttribute("data-side", "top");
    expect(screen.getByRole("listbox")).toHaveStyle({ maxHeight: "166px" });
    height.mockRestore(); surface.mockRestore(); field.mockRestore();
  });
});

