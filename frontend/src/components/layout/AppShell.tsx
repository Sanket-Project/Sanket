import { Outlet } from "react-router-dom";
import { Sidebar } from "@/components/layout/Sidebar";
import { TopBar } from "@/components/layout/TopBar";
import { useWorkspaceIndustry } from "@/hooks/useWorkspaceIndustry";
import { useSidebarStore } from "@/stores/sidebar";
import { SubscriptionGate } from "@/components/auth/SubscriptionGate";
import { SetupBanner } from "@/components/onboarding/SetupBanner";
import { ScrollManager } from "@/components/layout/ScrollManager";
import { DataChat } from "@/components/ai/DataChat";

export const AppShell = () => {
  const industry = useWorkspaceIndustry();
  const { collapsed } = useSidebarStore();

  return (
    <div
      id="app-shell-root"
      className="flex h-screen w-screen overflow-hidden relative bg-canvas lg:p-2.5 lg:gap-2.5"
      data-industry={industry}
      style={{ "--sidebar-w": collapsed ? "72px" : "244px" } as React.CSSProperties}
    >
      {/* Skip-to-main for keyboard users */}
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-[100] focus:px-4 focus:py-2 focus:bg-indigo-600 focus:text-white focus:rounded-lg focus:text-sm focus:font-semibold focus:shadow-lg"
      >
        Skip to main content
      </a>

      {/* Calm canvas with a single subtle accent wash (no mesh / noise / blobs) */}
      <div className="motion-bg" />

      <Sidebar />
      <ScrollManager />

      {/* Made inert while the mobile navigation drawer is open (see Sidebar). */}
      <div id="app-main-column" className="flex-1 flex flex-col overflow-hidden h-full">
        <TopBar />
        <main
          id="main-content"
          tabIndex={-1}
          className="flex-1 overflow-y-auto pt-3 pb-5 px-1 lg:px-2 animate-fade-in relative z-10 outline-none"
        >
          <div className="mx-auto w-full max-w-[1480px]">
            <SetupBanner />
            <SubscriptionGate>
              <DataChat />
              <Outlet />
            </SubscriptionGate>
          </div>
        </main>
      </div>
    </div>
  );
};
