import { Outlet } from "react-router-dom";
import { Sidebar } from "@/components/layout/Sidebar";
import { TopBar } from "@/components/layout/TopBar";
import { useIndustryStore } from "@/stores/industry";
import { useSidebarStore } from "@/stores/sidebar";
import { SubscriptionGate } from "@/components/auth/SubscriptionGate";
import { SetupBanner } from "@/components/onboarding/SetupBanner";

export const AppShell = () => {
  const industry = useIndustryStore((s) => s.activeIndustry);
  const { collapsed } = useSidebarStore();

  return (
    <div
      id="app-shell-root"
      className="flex h-screen w-screen overflow-hidden relative bg-canvas lg:p-3 lg:gap-3"
      data-industry={industry}
      style={{ "--sidebar-w": collapsed ? "76px" : "260px" } as React.CSSProperties}
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

      <div className="flex-1 flex flex-col overflow-hidden h-full">
        <TopBar />
        <main
          id="main-content"
          tabIndex={-1}
          className="flex-1 overflow-y-auto pt-3 lg:pt-4 pb-4 px-1 lg:px-2 animate-fade-in relative z-10 outline-none"
        >
          <div className="mx-auto w-full max-w-[1440px]">
            <SetupBanner />
            <SubscriptionGate>
              <Outlet />
            </SubscriptionGate>
          </div>
        </main>
      </div>
    </div>
  );
};
