import clsx from "clsx";
import type { ButtonHTMLAttributes, ReactNode } from "react";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md" | "lg";
  loading?: boolean;
  icon?: ReactNode;
}

export const Button = ({
  variant = "primary",
  size = "md",
  loading,
  icon,
  children,
  className,
  disabled,
  ...rest
}: Props) => {
  const variantCls = {
    primary: "btn-primary",
    secondary: "btn-secondary",
    ghost: "btn-ghost",
    danger:
      "btn bg-rose-600 text-white hover:bg-rose-700 focus-visible:ring-2 focus-visible:ring-rose-400/50",
  }[variant];
  const sizeCls = {
    sm: "px-3 py-1.5 text-xs",
    md: "px-4 py-2.5 text-sm",
    lg: "px-6 py-3 text-base",
  }[size];

  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={clsx(variantCls, sizeCls, className)}
    >
      {loading ? (
        <span
          className="h-4 w-4 rounded-full border-2 border-current/30 border-t-current animate-spin"
          aria-hidden="true"
        />
      ) : (
        icon && <span aria-hidden="true" className="contents">{icon}</span>
      )}
      {children}
    </button>
  );
};
