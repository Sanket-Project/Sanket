import { apiClient } from "@/api/client";
import type { IndustryCode } from "@/types/api";

export interface IntegrationStatus {
  provider: string;
  connected: boolean;
  status: "connected" | "syncing" | "error" | "disconnected" | string;
  shop_domain?: string | null;
  target_industry?: string | null;
  last_sync_at?: string | null;
  last_sync_status?: string | null;
  last_sync_stats: Record<string, number | string | null>;
  error_message?: string | null;
  shop_name?: string | null;
}

export interface ShopifyConnectRequest {
  shop_domain: string;
  access_token: string;
  target_industry: IndustryCode;
  sync_products: boolean;
  sync_inventory: boolean;
  sync_orders: boolean;
}

export interface SyncScope {
  sync_products: boolean;
  sync_inventory: boolean;
  sync_orders: boolean;
}

export interface LiveSaleRow {
  sale_time: string;
  sku_code?: string | null;
  description?: string | null;
  units: number;
  revenue?: number | null;
  order_id?: string | null;
}

export interface LiveSalesSummary {
  connected: boolean;
  today_units: number;
  today_revenue: number;
  today_orders: number;
  last_sale_at?: string | null;
  sparkline_hourly: number[];
  recent: LiveSaleRow[];
}

// ── Connector Hub (catalog of all providers) ────────────────────────────────
export interface AuthField {
  key: string;
  label: string;
  type: string;
  required: boolean;
  placeholder?: string | null;
  help?: string | null;
  options?: string[] | null;
  secret: boolean;
}

export interface Connector {
  key: string;
  name: string;
  category: string;
  availability: "live" | "beta" | "planned";
  summary: string;
  feeds: string[];
  auth_fields: AuthField[];
  docs_url?: string | null;
  icon: string;
  accent: string;
  status: "connected" | "syncing" | "error" | "requested" | "disconnected" | string;
  connected: boolean;
  last_sync_at?: string | null;
  last_sync_status?: string | null;
  error_message?: string | null;
  // Returned once, right after connecting a push provider (rest_api / webhooks).
  push_token?: string | null;
  supports_sync?: boolean;
}

export interface CategoryGroup {
  category: string;
  label: string;
  connectors: Connector[];
}

export interface Catalog {
  groups: CategoryGroup[];
  total: number;
  live: number;
  connected: number;
}

export interface GenericConnectRequest {
  target_industry: IndustryCode;
  credentials: Record<string, string>;
}

export interface UploadResult {
  provider: string;
  kind: string;
  rows_total: number;
  rows_imported: number;
  rows_skipped: number;
  products_created: number;
  skus_created: number;
  inventory_rows: number;
  sales_rows: number;
  errors: string[];
}

export const integrationsApi = {
  // Hub catalog
  catalog: () => apiClient.get<Catalog>("/integrations/catalog").then((r) => r.data),
  connect: (provider: string, body: GenericConnectRequest) =>
    apiClient.post<Connector>(`/integrations/${provider}/connect`, body).then((r) => r.data),
  disconnect: (provider: string) =>
    apiClient.delete<Connector>(`/integrations/${provider}`).then((r) => r.data),
  sync: (provider: string) =>
    apiClient.post<{ status: string; detail: string }>(`/integrations/${provider}/sync`, {}).then((r) => r.data),
  upload: (file: File, kind: string, targetIndustry: IndustryCode) => {
    const form = new FormData();
    form.append("file", file);
    form.append("kind", kind);
    form.append("target_industry", targetIndustry);
    return apiClient
      .post<UploadResult>("/integrations/upload", form, {
        headers: { "Content-Type": "multipart/form-data" },
      })
      .then((r) => r.data);
  },

  // Shopify (dedicated flow)
  shopifyStatus: () =>
    apiClient.get<IntegrationStatus>("/integrations/shopify").then((r) => r.data),
  shopifyConnect: (body: ShopifyConnectRequest) =>
    apiClient
      .post<IntegrationStatus>("/integrations/shopify/connect", body)
      .then((r) => r.data),
  shopifySync: (body: SyncScope) =>
    apiClient
      .post<{ status: string; detail: string }>("/integrations/shopify/sync", body)
      .then((r) => r.data),
  shopifyDisconnect: () =>
    apiClient.delete<IntegrationStatus>("/integrations/shopify").then((r) => r.data),
  shopifyLive: () =>
    apiClient.get<LiveSalesSummary>("/integrations/shopify/live").then((r) => r.data),
};
