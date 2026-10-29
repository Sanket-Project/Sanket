import clsx from "clsx";
import { forwardRef, useId, type ReactNode, type SelectHTMLAttributes } from "react";
import { ChevronDown } from "@/components/ui/icons";

interface Props extends Omit<SelectHTMLAttributes<HTMLSelectElement>, "size"> {
  label?: ReactNode;
  hint?: ReactNode;
  error?: ReactNode;
  options?: { value: string; label: string; disabled?: boolean }[];
  size?: "sm" | "md";
}

/** Native select for real keyboard and screen-reader behaviour, styled to the kit. */
export const Select = forwardRef<HTMLSelectElement, Props>(function Select({ label, hint, error, options, size = "md", className, id, children, ...rest }, ref) {
  const auto = useId();
  const selectId = id ?? auto;
  const hintId = hint ? `${selectId}-hint` : undefined;
  const errorId = error ? `${selectId}-error` : undefined;
  return (
    <div className={clsx("min-w-0", className)}>
      {label && <label htmlFor={selectId} className="t-label mb-1.5 block">{label}</label>}
      <div className="relative">
        <select ref={ref} id={selectId} aria-invalid={error ? true : undefined}
          aria-describedby={[hintId, errorId].filter(Boolean).join(" ") || undefined}
          className={clsx("focus-ring w-full appearance-none rounded-lg border bg-surface pl-3 pr-9 text-sm text-content transition-colors duration-fast ease-standard hover:border-line-strong disabled:opacity-60",
            size === "sm" ? "h-8" : "h-10", error ? "border-rose-500" : "border-line")}
          {...rest}>
          {options ? options.map((o) => <option key={o.value} value={o.value} disabled={o.disabled}>{o.label}</option>) : children}
        </select>
        <ChevronDown size={14} aria-hidden="true" className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-content-subtle" />
      </div>
      {hint && <p id={hintId} className="mt-1 text-xs text-content-subtle">{hint}</p>}
      {error && <p id={errorId} className="mt-1 text-xs text-rose-600 dark:text-rose-400">{error}</p>}
    </div>
  );
});
