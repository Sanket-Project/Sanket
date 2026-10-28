import { useEffect, useId, useRef, useState } from "react";
import { Check, ChevronDown, Search } from "@/components/ui/icons";
import clsx from "clsx";

export interface SelectOption { value: string; label: string; description?: string }

interface Props {
  label: string;
  value: string;
  options: SelectOption[];
  onChange: (value: string) => void;
  onSearch?: (query: string) => void;
  selectedLabel?: string;
  disabled?: boolean;
  loading?: boolean;
  hint?: string;
}

/** Searchable, labelled single selection with an optional remote search source. */
export function SearchableSelect({ label, value, options, onChange, onSearch, selectedLabel, disabled, loading, hint }: Props) {
  const id = useId();
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const search = useRef<HTMLInputElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [placement, setPlacement] = useState({ above: false, maxHeight: 240 });
  const visible = onSearch ? options : options.filter((option) => option.label.toLowerCase().includes(query.toLowerCase()));
  const selected = options.find((option) => option.value === value)?.label ?? selectedLabel ?? "Choose an option";
  const close = (restoreFocus = false) => {
    setOpen(false);
    if (restoreFocus) trigger.current?.focus({ preventScroll: true });
  };
  const choose = (option: SelectOption) => { onChange(option.value); close(true); };

  useEffect(() => {
    if (!open) return;
    const place = () => {
      // Labels and helper text must not displace the trigger's popup anchor.
      const rect = trigger.current?.getBoundingClientRect();
      if (!rect) return;
      // The workspace scroll surface starts below the persistent top bar.
      const main = root.current?.closest("main");
      const surface = main && /auto|scroll|hidden|clip/.test(getComputedStyle(main).overflowY)
        ? main.getBoundingClientRect() : undefined;
      const top = Math.max(0, surface?.top ?? 0);
      const bottom = Math.min(window.innerHeight, surface?.bottom ?? window.innerHeight);
      const below = bottom - rect.bottom - 8;
      const above = rect.top - top - 8;
      const flip = below < 300 && above > below;
      setPlacement({ above: flip, maxHeight: Math.max(0, Math.min(240, (flip ? above : below) - 56)) });
    };
    place();
    search.current?.focus({ preventScroll: true });
    const outside = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", outside);
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => { document.removeEventListener("mousedown", outside); window.removeEventListener("resize", place); window.removeEventListener("scroll", place, true); };
  }, [open]);

  useEffect(() => {
    const viewport = list.current;
    const option = viewport?.children[active] as HTMLElement | undefined;
    if (!open || !viewport || !option) return;
    // scrollIntoView also moves the page/main surface and can hide the menu's
    // search field under the header. Keep keyboard scrolling local to the list.
    const top = option.offsetTop, bottom = top + option.offsetHeight;
    if (top < viewport.scrollTop) viewport.scrollTop = top;
    else if (bottom > viewport.scrollTop + viewport.clientHeight) viewport.scrollTop = bottom - viewport.clientHeight;
  }, [open, active, query, options, placement.maxHeight]);

  return <div className="relative min-w-0" ref={root} onBlur={(event) => {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOpen(false);
  }}>
    <label id={`${id}-label`} htmlFor={`${id}-trigger`} className="mb-2 block text-xs font-semibold text-content-muted">{label}</label>
    <div className="relative">
    <button id={`${id}-trigger`} ref={trigger} type="button" role="combobox" aria-labelledby={`${id}-label`} aria-expanded={open}
      aria-controls={`${id}-list`} aria-haspopup="listbox" disabled={disabled}
      className="flex min-h-11 w-full items-center justify-between gap-3 rounded-xl border border-line bg-surface px-3 py-2.5 text-left text-sm text-content shadow-sm transition hover:border-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-50"
      onClick={() => { if (open) close(); else { setQuery(""); onSearch?.(""); setActive(Math.max(0, options.findIndex((option) => option.value === value))); setOpen(true); } }}
      onKeyDown={(event) => { if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); setOpen(true); setActive(0); } }}>
      <span className="min-w-0 truncate">{selected}</span><ChevronDown size={16} aria-hidden="true" className={clsx("shrink-0 text-content-muted transition-transform", open && "rotate-180")} />
    </button>
    {open && <div data-side={placement.above ? "top" : "bottom"} className={clsx("absolute inset-x-0 z-40 min-w-0 overflow-hidden rounded-xl border border-line bg-surface shadow-xl", placement.above ? "bottom-full mb-2" : "top-full mt-2")}>
      <div className="flex items-center gap-2 border-b border-line px-3 py-2">
        <Search size={15} className="shrink-0 text-content-muted" />
        <input ref={search} type="search" aria-label={`Search ${label}`} aria-controls={`${id}-list`}
          aria-activedescendant={visible[active] ? `${id}-option-${active}` : undefined} value={query}
          className="min-w-0 w-full bg-transparent py-1 text-sm text-content outline-none" placeholder={`Search ${label.toLowerCase()}…`}
          onChange={(event) => { setQuery(event.target.value); setActive(0); onSearch?.(event.target.value); }}
          onKeyDown={(event) => {
            if (event.key === "Escape") { event.preventDefault(); close(true); }
            if (event.key === "ArrowDown" || event.key === "ArrowUp") {
              event.preventDefault();
              setActive((current) => Math.max(0, Math.min(visible.length - 1, current + (event.key === "ArrowDown" ? 1 : -1))));
            }
            if (event.key === "Enter") { event.preventDefault(); if (visible[active]) choose(visible[active]); }
            if (event.key === "Home" || event.key === "End") { event.preventDefault(); setActive(event.key === "Home" ? 0 : Math.max(0, visible.length - 1)); }
          }} />
      </div>
      <ul ref={list} id={`${id}-list`} role="listbox" aria-label={label} aria-busy={loading} style={{ maxHeight: placement.maxHeight }} className="relative overflow-y-auto overscroll-contain p-1.5">
        {visible.map((option, index) => <li id={`${id}-option-${index}`} key={option.value} role="option" aria-selected={option.value === value}
          className={clsx("flex cursor-pointer items-center justify-between gap-2 rounded-lg px-3 py-2.5 text-sm text-content", active === index && "bg-surface-3")}
          onMouseDown={(event) => event.preventDefault()} onMouseEnter={() => setActive(index)} onClick={() => choose(option)}>
          <span className="min-w-0 break-words">{option.label}{option.description && <span className="mt-0.5 block text-xs text-content-subtle">{option.description}</span>}</span>
          {option.value === value && <Check size={15} className="shrink-0 text-accent" />}
        </li>)}
        {visible.length === 0 && <li className="px-3 py-3 text-sm text-content-muted">{loading ? "Searching…" : "No matches found"}</li>}
      </ul>
    </div>}
    </div>
    {hint && <p className="mt-1.5 text-xs text-content-subtle">{hint}</p>}
  </div>;
}
