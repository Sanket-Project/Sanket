import clsx from "clsx";
import { useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";

interface Tab<V extends string> { value: V; label: ReactNode; content: ReactNode; badge?: ReactNode }
interface Props<V extends string> { label: string; tabs: Tab<V>[]; value?: V; defaultValue?: V; onChange?: (value: V) => void }

export function Tabs<V extends string>({ label, tabs, value, defaultValue, onChange }: Props<V>) {
  const base = useId();
  const [inner, setInner] = useState<V>(defaultValue ?? tabs[0].value);
  const current = value ?? inner;
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const select = (v: V) => { if (value === undefined) setInner(v); onChange?.(v); };
  const focusAt = (i: number) => refs.current[(i + tabs.length) % tabs.length]?.focus();
  const onKeyDown = (e: KeyboardEvent, i: number) => {
    const keys: Record<string, () => void> = {
      ArrowRight: () => focusAt(i + 1), ArrowLeft: () => focusAt(i - 1),
      Home: () => focusAt(0), End: () => focusAt(tabs.length - 1),
      Enter: () => select(tabs[i].value), " ": () => select(tabs[i].value),
    };
    if (keys[e.key]) { e.preventDefault(); keys[e.key](); }
  };
  const active = tabs.find((t) => t.value === current) ?? tabs[0];
  return (
    <div className="min-w-0">
      <div role="tablist" aria-label={label} className="flex max-w-full gap-1 overflow-x-auto border-b border-line">
        {tabs.map((t, i) => {
          const selected = t.value === active.value;
          return (
            <button key={t.value} ref={(el) => { refs.current[i] = el; }} type="button" role="tab" id={`${base}-tab-${t.value}`}
              aria-selected={selected} aria-controls={selected ? `${base}-panel-${t.value}` : undefined} tabIndex={selected ? 0 : -1}
              onClick={() => select(t.value)} onKeyDown={(e) => onKeyDown(e, i)}
              className={clsx("focus-ring focus-visible:outline-offset-[-2px] -mb-px inline-flex items-center gap-2 whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium transition-colors duration-fast ease-standard",
                selected ? "border-accent text-content" : "border-transparent text-content-muted hover:text-content")}>
              {t.label}{t.badge}
            </button>
          );
        })}
      </div>
      <div role="tabpanel" id={`${base}-panel-${active.value}`} aria-labelledby={`${base}-tab-${active.value}`} tabIndex={0} className="focus-ring pt-4">
        {active.content}
      </div>
    </div>
  );
}
