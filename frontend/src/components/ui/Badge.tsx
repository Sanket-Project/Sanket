import clsx from "clsx";
import type { ReactNode } from "react";

interface Props {
  children: ReactNode;
  variant?: "default" | "success" | "warning" | "danger" | "info" | "primary";
  dot?: boolean;
  className?: string;
}

export const Badge = ({ children, variant = "default", dot, className }: Props) => {
  const cls = {
    default: "bg-surface-2 text-content-muted border-line",
    success: "bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-500/15 dark:text-emerald-300 dark:border-emerald-500/30",
    warning: "bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-500/15 dark:text-amber-300 dark:border-amber-500/30",
    danger: "bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-500/15 dark:text-rose-300 dark:border-rose-500/30",
    info: "bg-cyan-50 text-cyan-700 border-cyan-200 dark:bg-cyan-500/15 dark:text-cyan-300 dark:border-cyan-500/30",
    primary: "border-transparent",
  }[variant];

  const dotColor = {
    default: "bg-content-subtle",
    success: "bg-emerald-500",
    info: "bg-cyan-500",
    primary: "bg-[var(--accent)]",
    warning: "bg-amber-500",
    danger: "bg-rose-500",
  }[variant];

  const isPrimary = variant === "primary";

  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-semibold tracking-wide uppercase border leading-none",
        cls,
        className,
      )}
      style={
        isPrimary
          ? { background: "var(--accent-soft)", color: "var(--accent)" }
          : undefined
      }
    >
      {dot && <span className={clsx("h-1.5 w-1.5 rounded-full shrink-0", dotColor)} />}
      {children}
    </span>
  );
};
