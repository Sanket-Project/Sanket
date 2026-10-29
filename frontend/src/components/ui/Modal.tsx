import { X } from "@/components/ui/icons";
import { useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import clsx from "clsx";
import { useDialogFocus } from "./useDialogFocus";

interface Props {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  size?: "sm" | "md" | "lg" | "xl" | "wide";
}

export const Modal = ({
  open,
  onClose,
  title,
  children,
  footer,
  size = "md",
}: Props) => {
  const dialogRef = useRef<HTMLDivElement>(null);
  const titleId = useRef(`modal-title-${Math.random().toString(36).slice(2)}`);

  useDialogFocus(open, onClose, dialogRef);

  if (!open) return null;

  const sz = {
    sm: "max-w-sm",
    md: "max-w-lg",
    lg: "max-w-2xl",
    xl: "max-w-4xl",
    wide: "max-w-[1600px] max-h-[92dvh] flex flex-col",
  }[size];

  return createPortal(
    <div
      className={clsx("fixed inset-0 z-50 flex items-start justify-center p-4 overflow-y-auto bg-black/30 backdrop-blur-sm animate-fade-in",
        size === "wide" ? "pt-[4dvh]" : "pt-[10vh]")}
      onClick={onClose}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId.current}
        tabIndex={-1}
        className={clsx(
          "min-w-0 w-full rounded-[16px] p-5 sm:p-6 animate-slide-up shadow-lg border border-line bg-surface outline-none",
          sz,
        )}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex shrink-0 items-center justify-between mb-5">
          <h2
            id={titleId.current}
            className="font-heading text-xl font-semibold text-content tracking-tight"
          >
            {title}
          </h2>
          <button
            onClick={onClose}
            aria-label="Close dialog"
            className="p-1.5 rounded-lg text-content-subtle hover:text-content hover:bg-surface-3 transition"
          >
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        <div className={clsx("text-content-muted text-sm leading-relaxed", size === "wide" && "min-h-0 overflow-y-auto pr-1")}>{children}</div>
        {footer && (
          <div className="mt-6 pt-5 border-t border-line flex justify-end gap-3">
            {footer}
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
};
