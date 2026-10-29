import { useEffect, useRef, type RefObject } from "react";

const FOCUSABLE = 'a[href], button:not([disabled]), textarea, input, select, [tabindex]:not([tabindex="-1"])';

// Open dialogs, innermost last. Only the top one handles Escape and the Tab trap,
// so one Escape closes one surface. The body scroll lock is shared by the stack.
const openStack: symbol[] = [];
let overflowBeforeLock = "";

/** Escape, Tab trap, scroll lock, initial focus and focus restore for modal surfaces. */
export function useDialogFocus(open: boolean, onClose: () => void, ref: RefObject<HTMLElement>) {
  const onCloseRef = useRef(onClose);
  useEffect(() => { onCloseRef.current = onClose; });
  useEffect(() => {
    if (!open) return;
    const id = Symbol("dialog");
    const previous = document.activeElement as HTMLElement | null;
    const onKey = (e: KeyboardEvent) => {
      if (openStack[openStack.length - 1] !== id) return;
      if (e.key === "Escape") { onCloseRef.current(); return; }
      if (e.key !== "Tab" || !ref.current) return;
      const focusable = Array.from(ref.current.querySelectorAll<HTMLElement>(FOCUSABLE)).filter((el) => !el.hasAttribute("disabled"));
      if (focusable.length === 0) { e.preventDefault(); return; }
      const first = focusable[0], last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    if (openStack.length === 0) {
      overflowBeforeLock = document.body.style.overflow;
      document.body.style.overflow = "hidden";
    }
    openStack.push(id);
    window.addEventListener("keydown", onKey);
    const frame = requestAnimationFrame(() => {
      if (!ref.current) return;
      (ref.current.querySelector<HTMLElement>(FOCUSABLE) ?? ref.current).focus();
    });
    return () => {
      window.removeEventListener("keydown", onKey);
      const index = openStack.indexOf(id);
      if (index !== -1) openStack.splice(index, 1);
      if (openStack.length === 0) document.body.style.overflow = overflowBeforeLock;
      cancelAnimationFrame(frame);
      if (previous && document.contains(previous)) previous.focus();
    };
  }, [open, ref]);
}
