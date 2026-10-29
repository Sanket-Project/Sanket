import clsx from "clsx";
import { useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { X } from "@/components/ui/icons";
import { useDialogFocus } from "./useDialogFocus";

interface Props { open: boolean; onClose: () => void; title: ReactNode; description?: ReactNode; children: ReactNode; footer?: ReactNode; width?: "md" | "lg" }

export const Drawer = ({ open, onClose, title, description, children, footer, width = "md" }: Props) => {
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const descId = useId();
  useDialogFocus(open, onClose, ref);
  if (!open) return null;
  return createPortal(
    <div className="fixed inset-0 z-50 flex justify-end bg-black/30 animate-fade-in" onClick={onClose}>
      <div ref={ref} role="dialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={description ? descId : undefined} tabIndex={-1}
        onClick={(e) => e.stopPropagation()}
        className={clsx("drawer-panel flex h-full w-full flex-col border-l border-line bg-surface shadow-lg sm:w-auto", width === "lg" ? "sm:max-w-3xl sm:min-w-[40rem]" : "sm:max-w-xl sm:min-w-[28rem]")}>
        <header className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
          <div className="min-w-0">
            <h2 id={titleId} className="t-section">{title}</h2>
            {description && <p id={descId} className="t-body mt-1">{description}</p>}
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="focus-ring grid h-9 w-9 shrink-0 place-items-center rounded-lg text-content-muted hover:bg-surface-2 hover:text-content">
            <X size={18} aria-hidden="true" />
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
        {footer && <footer className="flex flex-wrap justify-end gap-2 border-t border-line px-5 py-3">{footer}</footer>}
      </div>
    </div>,
    document.body,
  );
};
