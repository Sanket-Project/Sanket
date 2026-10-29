import clsx from "clsx";
import { useId, type ReactNode } from "react";

/** Groups content by heading and hairline instead of another card. */
export const Section = ({ title, description, actions, divider = true, id, className, children }: {
  title: ReactNode; description?: ReactNode; actions?: ReactNode; divider?: boolean; id?: string; className?: string; children: ReactNode;
}) => {
  const headingId = useId();
  return (
    <section id={id} aria-labelledby={headingId} className={clsx("min-w-0", divider && "border-t border-line pt-6", className)}>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
        <div className="min-w-0">
          <h2 id={headingId} className="t-section">{title}</h2>
          {description && <p className="t-body mt-1">{description}</p>}
        </div>
        {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {children}
    </section>
  );
};
