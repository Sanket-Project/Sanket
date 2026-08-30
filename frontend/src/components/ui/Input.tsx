import clsx from "clsx";
import type { InputHTMLAttributes, ReactNode } from "react";
import { forwardRef, useState } from "react";
import { Eye, EyeOff } from "@/components/ui/icons";

interface Props extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  hint?: string;
  icon?: ReactNode;
  showPasswordToggle?: boolean;
}

export const Input = forwardRef<HTMLInputElement, Props>(
  ({ label, error, hint, icon, className, id, type, showPasswordToggle = true, ...rest }, ref) => {
    const [showPassword, setShowPassword] = useState(false);

    const inputId = id ?? rest.name;
    const errorId = inputId ? `${inputId}-error` : undefined;
    const hintId = inputId ? `${inputId}-hint` : undefined;
    const describedBy = [error && errorId, !error && hint && hintId]
      .filter(Boolean)
      .join(" ") || undefined;

    const isPassword = type === "password";
    const actualType = isPassword ? (showPassword ? "text" : "password") : type;
    const displayToggle = isPassword && showPasswordToggle;

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
            type={actualType}
            aria-invalid={error ? "true" : undefined}
            aria-describedby={describedBy}
            className={clsx(
              "input",
              icon && "pl-10",
              displayToggle && "pr-10",
              error && "!border-rose-500",
              className,
            )}
            {...rest}
          />
          {displayToggle && (
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              className="absolute inset-y-0 right-3 flex items-center text-content-subtle transition hover:text-content"
              aria-label={showPassword ? "Hide password" : "Show password"}
            >
              {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
            </button>
          )}
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
