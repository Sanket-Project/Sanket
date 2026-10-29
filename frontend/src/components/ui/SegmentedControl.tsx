import clsx from "clsx";
import { useRef, type KeyboardEvent, type ReactNode } from "react";

interface Props<V extends string> {
  label: string;
  value: V;
  onChange: (value: V) => void;
  options: { value: V; label: ReactNode }[];
  size?: "sm" | "md";
}

export function SegmentedControl<V extends string>({ label, value, onChange, options, size = "md" }: Props<V>) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const activeIndex = Math.max(0, options.findIndex((o) => o.value === value));
  const move = (from: number, delta: number) => {
    const next = (from + delta + options.length) % options.length;
    onChange(options[next].value);
    refs.current[next]?.focus();
  };
  const onKeyDown = (e: KeyboardEvent, i: number) => {
    if (e.key === "ArrowRight" || e.key === "ArrowDown") { e.preventDefault(); move(i, 1); }
    if (e.key === "ArrowLeft" || e.key === "ArrowUp") { e.preventDefault(); move(i, -1); }
  };
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex max-w-full overflow-x-auto rounded-lg border border-line bg-surface-2 p-0.5">
      {options.map((o, i) => {
        const checked = o.value === value;
        return (
          <button key={o.value} ref={(el) => { refs.current[i] = el; }} type="button" role="radio" aria-checked={checked} tabIndex={i === activeIndex ? 0 : -1}
            onClick={() => onChange(o.value)} onKeyDown={(e) => onKeyDown(e, i)}
            className={clsx("focus-ring focus-visible:outline-offset-[-2px] whitespace-nowrap rounded-md font-medium transition-colors duration-fast ease-standard",
              size === "sm" ? "px-2.5 py-1 text-xs" : "px-3 py-1.5 text-sm",
              checked ? "bg-surface text-content shadow-sm" : "text-content-muted hover:text-content")}>
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
