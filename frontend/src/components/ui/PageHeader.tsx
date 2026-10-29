import type { ReactNode } from "react";

interface Props {
  title: string;
  eyebrow?: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}

/** One consistent heading rhythm; actions wrap beside or below the page title. */
export const PageHeader = ({ title, eyebrow, description, actions }: Props) => (
  <header className="flex min-w-0 flex-wrap items-end justify-between gap-x-6 gap-y-4 pb-1">
    <div className="min-w-0 max-w-3xl">
      {eyebrow && <p className="mb-2 flex items-center gap-2 text-xs font-medium text-accent">{eyebrow}</p>}
      <h1 className="font-heading text-[28px] font-semibold leading-tight tracking-tight text-content">{title}</h1>
      {description && <p className="mt-2 text-sm leading-relaxed text-content-muted">{description}</p>}
    </div>
    {actions && <div role="group" aria-label={`${title} actions`} className="flex max-w-full flex-wrap items-center gap-2">{actions}</div>}
  </header>
);
