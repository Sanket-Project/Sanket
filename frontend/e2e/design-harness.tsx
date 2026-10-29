// Isolated browser-test entry. Vite resolves shared React/Router modules once.
import React from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { AppShell } from "../src/components/layout/AppShell";
import { Button } from "../src/components/ui/Button";
import { Input } from "../src/components/ui/Input";
import { Card } from "../src/components/ui/Card";
import { ForecastChart } from "../src/components/charts/ForecastChart";
import { useAuthStore } from "../src/stores/auth";
import "../src/styles/index.css";

useAuthStore.setState({ industry: "fashion", role: "owner", isAuthenticated: true, ready: true, fullName: "Design reviewer", onboarding: null });
localStorage.setItem("sanket.theme", document.documentElement.classList.contains("dark") ? "dark" : "light");
const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
client.setQueryData(["billing", "subscription"], { status: "active" });
const screenName = new URLSearchParams(location.search).get("screen");
const fixture = new URLSearchParams(location.search).get("fixture");
if (fixture === "planning") {
  const { installPlanningFixture } = await import("./planning-fixture");
  installPlanningFixture();
} else {
  const { installUnavailableFixture } = await import("./unavailable-fixture");
  installUnavailableFixture();
}
const pageModules = import.meta.glob(["../src/pages/**/*.tsx", "!../src/pages/**/*.test.tsx"]);
const screens: Record<string, [string, string]> = {
  Dashboard: ["Dashboard", "Dashboard"], Products: ["Products", "ProductsPage"], Skus: ["Skus", "SkusPage"],
  Inventory: ["Inventory", "InventoryPage"], Forecasts: ["Forecasts", "ForecastsPage"], Decisions: ["Decisions", "DecisionsPage"],
  SalesAnalytics: ["SalesAnalytics", "SalesAnalyticsPage"], TrendAnalysis: ["TrendAnalysis", "TrendAnalysisPage"],
  ROIDashboard: ["ROIDashboard", "ROIDashboardPage"], FinancialImpact: ["FinancialImpact", "FinancialImpactPage"],
  DataQuality: ["DataQuality", "DataQualityPage"], ShortageAlerts: ["ShortageAlerts", "ShortageAlertsPage"],
  Integrations: ["Integrations", "IntegrationsPage"], Notifications: ["Notifications", "NotificationsPage"],
  Settings: ["Settings", "SettingsPage"], Profile: ["Profile", "ProfilePage"], Billing: ["Billing", "BillingPage"],
  Webhooks: ["Webhooks", "WebhooksPage"], LiveSales: ["LiveSales", "LiveSalesPage"], PharmaBatches: ["PharmaBatches", "PharmaBatchesPage"],
  ProductDetail: ["detail/ProductDetail", "ProductDetailPage"], SkuDetail: ["detail/SkuDetail", "SkuDetailPage"],
  Login: ["Login", "LoginPage"], ForgotPassword: ["ForgotPassword", "ForgotPasswordPage"], ResetPassword: ["ResetPassword", "ResetPasswordPage"],
  AcceptInvite: ["AcceptInvite", "AcceptInvitePage"], Terms: ["Legal", "TermsPage"], Privacy: ["Legal", "PrivacyPolicyPage"], NotFound: ["NotFound", "NotFoundPage"],
  ForecastAccuracy: ["ForecastAccuracy", "ForecastAccuracyPage"], HybridForecasts: ["HybridForecasts", "HybridForecastsPage"],
  WhatIfScenario: ["WhatIfScenario", "WhatIfScenarioPage"], Signals: ["Signals", "SignalsPage"],
  Landing: ["LandingPage", "LandingPage"],
  OnboardingIndustry: ["onboarding/OnboardingPage", "OnboardingPage"], OnboardingData: ["onboarding/OnboardingPage", "OnboardingPage"],
  OnboardingCalendar: ["onboarding/OnboardingPage", "OnboardingPage"], OnboardingTeam: ["onboarding/OnboardingPage", "OnboardingPage"], OnboardingBaseline: ["onboarding/OnboardingPage", "OnboardingPage"],
  Fashion: ["industries/FashionDashboard", "FashionDashboard"], Electronics: ["industries/ElectronicsDashboard", "ElectronicsDashboard"],
  Pharma: ["industries/PharmaDashboard", "PharmaDashboard"], Agriculture: ["industries/AgrocenterdDashboard", "AgrocenterdDashboard"], Hardware: ["industries/HardwareDashboard", "HardwareDashboard"],
};
const publicScreens = new Set(["Login", "ForgotPassword", "ResetPassword", "AcceptInvite", "Terms", "Privacy", "NotFound", "Landing", "OnboardingIndustry", "OnboardingData", "OnboardingCalendar", "OnboardingTeam", "OnboardingBaseline"]);
let content = <section><h1>Planning workspace</h1><p>Sources are unavailable in this isolated design test.</p><Card title="Business overview" aria-label="Business overview"><Input label="Find a product" hint="Search your product catalog" /><Button>Review plan</Button></Card></section>;
if (screenName && screens[screenName]) {
  const [file, exportName] = screens[screenName];
  const module = await pageModules[`../src/pages/${file}.tsx`]();
  const Screen = (module as Record<string, React.ComponentType>)[exportName];
  content = <Screen />;
  if (screenName === "Login" || screenName === "AcceptInvite" || screenName === "Landing") useAuthStore.setState({ isAuthenticated: false });
  if (screenName.startsWith("Onboarding")) useAuthStore.setState({ onboarding: { status: "in_progress", current_step: screenName.slice(10).toLowerCase() as "industry" | "data" | "calendar" | "team" | "baseline", steps: {}, completed_at: null } });
  if (screenName === "PharmaBatches" || screenName === "Pharma") useAuthStore.setState({ industry: "pharma" });
}
if (screenName === "ChartReview") content = <Card title="Synthetic chart acceptance fixture"><ForecastChart rows={[{ sku_id: "fixture", forecast_date: "2026-11-02", p10: 8, p50: 10, p90: 12 }]} history={[{ date: "2026-10-26", actual: 9 }]} unitLabel="units / week" /></Card>;
if (screenName === "ImportReview") {
  const { UploadPanel } = await import("../src/pages/Integrations");
  content = <Card title="Import data"><UploadPanel onDone={() => {}} /></Card>;
}
if (screenName === "ImportDialog") {
  const { ImportModal } = await import("../src/components/ui/ImportModal");
  content = <ImportModal open onClose={() => {}} title="Synthetic import review" description="No workspace data" requiredColumns={[]} onParse={async () => { throw new Error("Disabled in design review"); }} onImport={async () => { throw new Error("Disabled in design review"); }} onDownloadTemplate={() => {}} manualEntry={{ label: "Single item", content: <p>Isolated review</p>, onSubmit: () => {}, submitLabel: "Create item" }} defaultTab="manual" />;
}
const publicScreen = publicScreens.has(screenName ?? "");

createRoot(document.getElementById("root")!).render(
  <QueryClientProvider client={client}>
    <MemoryRouter initialEntries={["/workspace"]}>
      {publicScreen ? content : <Routes><Route path="/workspace" element={<AppShell />}><Route index element={content} /></Route></Routes>}
      {fixture && <p className="fixed bottom-1 left-1 z-[100] rounded bg-surface px-2 py-1 text-[10px] text-content-muted">Synthetic design review · no workspace data</p>}
    </MemoryRouter>
  </QueryClientProvider>,
);
