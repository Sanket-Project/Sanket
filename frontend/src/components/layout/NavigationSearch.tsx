import { Search } from "@/components/ui/icons";
import { useSidebarStore } from "@/stores/sidebar";

export function NavigationSearch() {
  const open = () => {
    useSidebarStore.getState().setCollapsed(false);
    if (!window.matchMedia("(min-width: 1024px)").matches) useSidebarStore.getState().setMobileOpen(true);
    requestAnimationFrame(() => document.querySelector<HTMLInputElement>('input[aria-label="Search navigation"]')?.focus());
  };
  return <button type="button" onClick={open} aria-label="Find a page" className="inline-flex h-10 min-w-10 items-center gap-3 rounded-xl border border-line bg-surface-2/50 px-3 text-sm text-content-muted hover:border-line-strong lg:w-72 xl:w-80">
    <Search size={16} aria-hidden="true" /><span className="hidden lg:inline">Find a page…</span><kbd className="ml-auto hidden rounded border border-line bg-surface px-1.5 py-0.5 font-mono text-[10px] lg:inline">Ctrl K</kbd>
  </button>;
}
