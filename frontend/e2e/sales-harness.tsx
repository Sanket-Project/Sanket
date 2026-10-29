import React from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { SalesAnalyticsPage } from "../src/pages/SalesAnalytics";
import { useAuthStore } from "../src/stores/auth";
import "../src/styles/index.css";

useAuthStore.setState({ industry: "fashion" });
createRoot(document.getElementById("root")!).render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter><SalesAnalyticsPage /></MemoryRouter></QueryClientProvider>);
