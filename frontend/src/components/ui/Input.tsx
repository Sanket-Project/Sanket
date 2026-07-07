import clsx from "clsx";
import type { InputHTMLAttributes, ReactNode } from "react";
import { forwardRef } from "react";

interface Props extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  hint?: string;
  icon?: ReactNode;
}

export const Input = forwardRef<HTMLInputElement, Props>(
  ({ label, error, hint, icon, className, id, ...rest }, ref) => {
    const inputId = id ?? rest.name;
    const errorId = inputId ? `${inputId}-error` : undefined;
    const hintId = inputId ? `${inputId}-hint` : undefined;
    const describedBy = [error && errorId, !error && hint && hintId]
      .filter(Boolean)
      .join(" ") || undefined;

    return (
      <div className="w-full">
        {label && (
          <label htmlFor={inputId} className="label">
            {label}
          </label>
        )}
        <div className="relative">
          {icon && (
            <div className="absolute inset-y-0 left-3 flex items-center text-content-subtle pointer-events-none" aria-hidden="true">
              {icon}
            </div>
          )}
          <input
            id={inputId}
            ref={ref}
            {...rest}
            aria-invalid={error ? "true" : undefined}
            aria-describedby={describedBy}
            className={clsx(
              "input",
              icon && "pl-10",
              error && "!border-rose-500",
              className,
            )}
          />
        </div>
        {error && (
          <p id={errorId} role="alert" className="text-xs text-rose-500 mt-1.5">{error}</p>
        )}
        {!error && hint && (
          <p id={hintId} className="text-xs text-content-subtle mt-1.5">{hint}</p>
        )}
      </div>
    );
  },
);
Input.displayName = "Input";
