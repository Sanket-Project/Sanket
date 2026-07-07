import clsx from "clsx";
import type { ReactNode } from "react";

interface Props {
  icon?: ReactNode;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  /** subtle = inline within a card; default = standalone block */
  variant?: "default" | "subtle";
  className?: string;
}

/**
 * Honest empty state — used when there is genuinely nothing to show yet (no
 * connected sources, no forecast run). Never a placeholder for fabricated data.
 */
export const EmptyState = ({
  icon,
  title,
  description,
  action,
  variant = "default",
  className,
}: Props) => (
  <div
    className={clsx(
      "flex flex-col items-center justify-center text-center",
      variant === "default" ? "px-6 py-14" : "px-4 py-8",
      className,
    )}
  >
    {icon && (
      <div className="mb-4 grid h-12 w-12 place-items-center rounded-2xl bg-surface-3 text-content-subtle">
        {icon}
      </div>
    )}
    <h3 className="font-heading text-[15px] font-semibold tracking-tight text-content">{title}</h3>
    {description && (
      <p className="mt-1.5 max-w-sm text-sm leading-relaxed text-content-subtle">{description}</p>
    )}
    {action && <div className="mt-5">{action}</div>}
  </div>
);
