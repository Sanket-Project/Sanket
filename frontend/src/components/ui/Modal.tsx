import { X } from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import clsx from "clsx";

interface Props {
  open: boolean;
  onClose: () => void;
  title?: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  size?: "sm" | "md" | "lg" | "xl";
}

const FOCUSABLE =
  'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])';

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

  useEffect(() => {
    if (!open) return;

    // Escape key closes
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { onClose(); return; }

      // Focus trap — Tab / Shift+Tab
      if (e.key === "Tab" && dialogRef.current) {
        const focusable = Array.from(
          dialogRef.current.querySelectorAll<HTMLElement>(FOCUSABLE),
        ).filter((el) => !el.hasAttribute("disabled"));
        if (focusable.length === 0) { e.preventDefault(); return; }
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey) {
          if (document.activeElement === first) { e.preventDefault(); last.focus(); }
        } else {
          if (document.activeElement === last) { e.preventDefault(); first.focus(); }
        }
      }
    };

    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);

    // Auto-focus first focusable element (or the dialog itself)
    const frame = requestAnimationFrame(() => {
      if (!dialogRef.current) return;
      const first = dialogRef.current.querySelector<HTMLElement>(FOCUSABLE);
      (first ?? dialogRef.current).focus();
    });

    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
      cancelAnimationFrame(frame);
    };
  }, [open, onClose]);

  if (!open) return null;

  const sz = {
    sm: "max-w-sm",
    md: "max-w-lg",
    lg: "max-w-2xl",
    xl: "max-w-4xl",
  }[size];

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-start justify-center p-4 pt-[10vh] overflow-y-auto bg-slate-950/40 backdrop-blur-md animate-fade-in"
      onClick={onClose}
      aria-hidden="true"
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId.current}
        tabIndex={-1}
        className={clsx(
          "w-full rounded-2xl p-7 animate-slide-up shadow-lg border border-line bg-surface outline-none",
          sz,
        )}
        onClick={(e) => e.stopPropagation()}
        aria-hidden={false}
      >
        <div className="flex items-center justify-between mb-5">
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
        <div className="text-content-muted text-sm leading-relaxed">{children}</div>
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
