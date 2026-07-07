import clsx from "clsx";
import type { HTMLAttributes, ReactNode } from "react";

interface Props extends Omit<HTMLAttributes<HTMLDivElement>, "title"> {
  title?: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  padding?: "none" | "sm" | "md" | "lg";
  children: ReactNode;
}

export const Card = ({
  title,
  description,
  action,
  padding = "md",
  className,
  children,
  ...rest
}: Props) => {
  const padCls = { none: "p-0", sm: "p-4", md: "p-6", lg: "p-8" }[padding];

  return (
    <div
      {...rest}
      className={clsx(
        "rounded-[20px] bg-surface border border-line shadow-sm hover:shadow-md hover:border-line-strong transition-all duration-200 ease-out",
        padCls,
        className,
      )}
    >
      {(title || description || action) && (
        <div
          className={clsx(
            "flex items-start justify-between gap-4",
            padding === "none" ? "px-5 pt-5 mb-4" : "mb-5",
          )}
        >
          <div className="min-w-0">
            {title && (
              <h3 className="font-heading text-[15px] font-semibold text-content tracking-tight">
                {title}
              </h3>
            )}
            {description && (
              <p className="text-xs text-content-subtle mt-1 leading-relaxed">{description}</p>
            )}
          </div>
          {action && <div className="shrink-0">{action}</div>}
        </div>
      )}
      {children}
    </div>
  );
};
