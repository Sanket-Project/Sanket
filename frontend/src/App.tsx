import { lazy, Suspense, useEffect } from "react";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { Toaster } from "react-hot-toast";

import { useAuthStore } from "@/stores/auth";
import { ProtectedRoute } from "@/components/auth/ProtectedRoute";
import { OnboardingGate } from "@/components/auth/OnboardingGate";
import { AppShell } from "@/components/layout/AppShell";
import { ErrorBoundary } from "@/components/ErrorBoundary";
import { SkeletonCard } from "@/components/ui/Skeleton";

// Heavy pages — code split to keep the initial bundle lean
const LandingPage = lazy(() =>
  import("@/pages/LandingPage").then((m) => ({ default: m.LandingPage }))
);
const LoginPage = lazy(() =>
  import("@/pages/Login").then((m) => ({ default: m.LoginPage }))
);
const TermsPage = lazy(() =>
  import("@/pages/Legal").then((m) => ({ default: m.TermsPage }))
);
const PrivacyPolicyPage = lazy(() =>
  import("@/pages/Legal").then((m) => ({ default: m.PrivacyPolicyPage }))
);
const Dashboard = lazy(() =>
  import("@/pages/Dashboard").then((m) => ({ default: m.Dashboard }))
);
const ProductsPage = lazy(() =>
  import("@/pages/Products").then((m) => ({ default: m.ProductsPage }))
);
const SkusPage = lazy(() =>
  import("@/pages/Skus").then((m) => ({ default: m.SkusPage }))
);
const SignalsPage = lazy(() =>
  import("@/pages/Signals").then((m) => ({ default: m.SignalsPage }))
);
const ForecastsPage = lazy(() =>
  import("@/pages/Forecasts").then((m) => ({ default: m.ForecastsPage }))
);
const SettingsPage = lazy(() =>
  import("@/pages/Settings").then((m) => ({ default: m.SettingsPage }))
);
const IntegrationsPage = lazy(() =>
  import("@/pages/Integrations").then((m) => ({ default: m.IntegrationsPage }))
);
const LiveSalesPage = lazy(() =>
  import("@/pages/LiveSales").then((m) => ({ default: m.LiveSalesPage }))
);
const PharmaBatchesPage = lazy(() =>
  import("@/pages/PharmaBatches").then((m) => ({ default: m.PharmaBatchesPage }))
);
const ProductDetailPage = lazy(() =>
  import("@/pages/detail/ProductDetail").then((m) => ({ default: m.ProductDetailPage }))
);
const SkuDetailPage = lazy(() =>
  import("@/pages/detail/SkuDetail").then((m) => ({ default: m.SkuDetailPage }))
);
const BillingPage = lazy(() =>
  import("@/pages/Billing").then((m) => ({ default: m.BillingPage }))
);
const WebhooksPage = lazy(() =>
  import("@/pages/Webhooks").then((m) => ({ default: m.WebhooksPage }))
);
const TrendAnalysisPage = lazy(() =>
  import("@/pages/TrendAnalysis").then((m) => ({ default: m.TrendAnalysisPage }))
);
const HybridForecastsPage = lazy(() =>
  import("@/pages/HybridForecasts").then((m) => ({ default: m.HybridForecastsPage }))
);
const ShortageAlertsPage = lazy(() =>
  import("@/pages/ShortageAlerts").then((m) => ({ default: m.ShortageAlertsPage }))
);
const FinancialImpactPage = lazy(() =>
  import("@/pages/FinancialImpact").then((m) => ({ default: m.FinancialImpactPage }))
);
const SalesAnalyticsPage = lazy(() =>
  import("@/pages/SalesAnalytics").then((m) => ({ default: m.SalesAnalyticsPage }))
);
const ForecastAccuracyPage = lazy(() =>
  import("@/pages/ForecastAccuracy").then((m) => ({ default: m.ForecastAccuracyPage }))
);
const InventoryPage = lazy(() =>
  import("@/pages/Inventory").then((m) => ({ default: m.InventoryPage }))
);
const ForgotPasswordPage = lazy(() =>
  import("@/pages/ForgotPassword").then((m) => ({ default: m.ForgotPasswordPage }))
);
const ResetPasswordPage = lazy(() =>
  import("@/pages/ResetPassword").then((m) => ({ default: m.ResetPasswordPage }))
);
const ProfilePage = lazy(() =>
  import("@/pages/Profile").then((m) => ({ default: m.ProfilePage }))
);
const NotFoundPage = lazy(() =>
  import("@/pages/NotFound").then((m) => ({ default: m.NotFoundPage }))
);
const OnboardingPage = lazy(() =>
  import("@/pages/onboarding/OnboardingPage").then((m) => ({ default: m.OnboardingPage }))
);

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (count, err) => {
        const status = (err as { response?: { status?: number } })?.response?.status;
        if (status && status < 500 && status !== 408) return false;
        return count < 2;
      },
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
});

/** Consistent loading fallback for all lazy-loaded pages */
const PageFallback = () => (
  <div className="space-y-4 p-8">
    <SkeletonCard />
    <SkeletonCard />
    <SkeletonCard />
  </div>
);

export default function App() {
  // Kick off the one-time auth bootstrap (Firebase listener / dev-session
  // restore) as early as possible so route guards resolve without flicker.
  useEffect(() => {
    useAuthStore.getState().bootstrap();
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter basename={import.meta.env.BASE_URL}>
        <Routes>
          <Route
            path="/"
            element={
              <ErrorBoundary>
                <Suspense fallback={<PageFallback />}>
                  <LandingPage />
                </Suspense>
              </ErrorBoundary>
            }
          />
          <Route
            path="/login"
            element={
              <ErrorBoundary>
                <Suspense fallback={<PageFallback />}>
                  <LoginPage />
                </Suspense>
              </ErrorBoundary>
            }
          />
          <Route
            path="/terms"
            element={
              <ErrorBoundary>
                <Suspense fallback={<PageFallback />}>
                  <TermsPage />
                </Suspense>
              </ErrorBoundary>
            }
          />
          <Route
            path="/privacy"
            element={
              <ErrorBoundary>
                <Suspense fallback={<PageFallback />}>
                  <PrivacyPolicyPage />
                </Suspense>
              </ErrorBoundary>
            }
          />
          <Route
            path="/forgot-password"
            element={
              <ErrorBoundary>
                <Suspense fallback={<PageFallback />}>
                  <ForgotPasswordPage />
                </Suspense>
              </ErrorBoundary>
            }
          />
          <Route
            path="/reset-password"
            element={
              <ErrorBoundary>
                <Suspense fallback={<PageFallback />}>
                  <ResetPasswordPage />
                </Suspense>
              </ErrorBoundary>
            }
          />
          <Route
            path="/onboarding"
            element={
              <ProtectedRoute>
                <ErrorBoundary>
                  <Suspense fallback={<PageFallback />}>
                    <OnboardingPage />
                  </Suspense>
                </ErrorBoundary>
              </ProtectedRoute>
            }
          />
          <Route
            path="/workspace"
            element={
              <ProtectedRoute>
                <OnboardingGate>
                  <AppShell />
                </OnboardingGate>
              </ProtectedRoute>
            }
          >
            <Route index element={<ErrorBoundary><Suspense fallback={<PageFallback />}><Dashboard /></Suspense></ErrorBoundary>} />
            <Route path="products" element={<ErrorBoundary><Suspense fallback={<PageFallback />}><ProductsPage /></Suspense></ErrorBoundary>} />
            <Route path="products/:id" element={<ErrorBoundary><Suspense fallback={<PageFallback />}><ProductDetailPage /></Suspense></ErrorBoundary>} />
            <Route path="skus" element={<ErrorBoundary><Suspense fallback={<PageFallback />}><SkusPage /></Suspense></ErrorBoundary>} />
            <Route path="skus/:id" element={<ErrorBoundary><Suspense fallback={<PageFallback />}><SkuDetailPage /></Suspense></ErrorBoundary>} />
            <Route path="inventory" element={<ErrorBoundary><Suspense fallback={<PageFallback />}><InventoryPage /></Suspense></ErrorBoundary>} />
            <Route path="signals" element={<ErrorBoundary><Suspense fallback={<PageFallback />}><SignalsPage /></Suspense></ErrorBoundary>} />
            <Route path="trends" element={<ErrorBoundary><Suspense fallback={<PageFallback />}><TrendAnalysisPage /></Suspense></ErrorBoundary>} />
            <Route path="forecasts" element={<ErrorBoundary><Suspense fallback={<PageFallback />}><ForecastsPage /></Suspense></ErrorBoundary>} />
            <Route path="forecasts/hybrid" element={<ErrorBoundary><Suspense fallback={<PageFallback />}><HybridForecastsPage /></Suspense></ErrorBoundary>} />
            <Route path="alerts" element={<ErrorBoundary><Suspense fallback={<PageFallback />}><ShortageAlertsPage /></Suspense></ErrorBoundary>} />
            <Route path="sales-analytics" element={<ErrorBoundary><Suspense fallback={<PageFallback />}><SalesAnalyticsPage /></Suspense></ErrorBoundary>} />
            <Route path="live-sales" element={<ErrorBoundary><Suspense fallback={<PageFallback />}><LiveSalesPage /></Suspense></ErrorBoundary>} />
            <Route path="financial" element={<ErrorBoundary><Suspense fallback={<PageFallback />}><FinancialImpactPage /></Suspense></ErrorBoundary>} />
            <Route path="forecast-accuracy" element={<ErrorBoundary><Suspense fallback={<PageFallback />}><ForecastAccuracyPage /></Suspense></ErrorBoundary>} />
            <Route path="pharma/batches" element={<ErrorBoundary><Suspense fallback={<PageFallback />}><PharmaBatchesPage /></Suspense></ErrorBoundary>} />
            <Route path="billing" element={<ErrorBoundary><Suspense fallback={<PageFallback />}><BillingPage /></Suspense></ErrorBoundary>} />
            <Route path="webhooks" element={<ErrorBoundary><Suspense fallback={<PageFallback />}><WebhooksPage /></Suspense></ErrorBoundary>} />
            <Route path="integrations" element={<ErrorBoundary><Suspense fallback={<PageFallback />}><IntegrationsPage /></Suspense></ErrorBoundary>} />
            <Route path="settings" element={<ErrorBoundary><Suspense fallback={<PageFallback />}><SettingsPage /></Suspense></ErrorBoundary>} />
            <Route path="profile" element={<ErrorBoundary><Suspense fallback={<PageFallback />}><ProfilePage /></Suspense></ErrorBoundary>} />
          </Route>
          {/* 404 — show a proper page instead of silently redirecting */}
          <Route
            path="*"
            element={
              <Suspense fallback={null}>
                <NotFoundPage />
              </Suspense>
            }
          />
        </Routes>
      </BrowserRouter>

      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            background: "#11141C",
            color: "#fff",
            border: "1px solid rgba(255,255,255,0.08)",
            fontSize: 13,
          },
        }}
      />
      {/* Only include devtools in development — not in the production bundle */}
      {import.meta.env.DEV && (
        <ReactQueryDevtools initialIsOpen={false} buttonPosition="bottom-left" />
      )}
    </QueryClientProvider>
  );
}
