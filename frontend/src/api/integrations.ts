import { apiClient } from "@/api/client";

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
  /** Sales replay accounting: new rows, rows already present, corrected rows. */
  rows_inserted: number;
  rows_unchanged: number;
  rows_updated: number;
  identity_mode: "transaction" | "period" | null;
  warnings: string[];
  errors: string[];
}

export interface UploadOptions {
  /**
   * How a re-uploaded sales row is recognised: "transaction" lines (order and
   * line id, else the row itself) or "period" totals — one row per SKU,
   * location, channel and day, so a corrected export replaces the value.
   */
  identity?: "transaction" | "period";
  /** ISO code of the prices in the file, for SKUs it creates. */
  currency?: string;
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
  /**
   * Rows land in the workspace's own industry — the server reads it from the
   * verified session. No target_industry is sent: supplying a different one is
   * refused, and supplying the same one is just a chance to get it wrong.
   */
  upload: (
    file: File,
    kind: string,
    columnMapping?: Record<string, string>,
    options: UploadOptions = {},
  ) => {
    const form = new FormData();
    form.append("file", file);
    form.append("kind", kind);
    if (columnMapping) {
      form.append("column_mapping", JSON.stringify(columnMapping));
    }
    if (kind === "sales" && options.identity) form.append("identity", options.identity);
    if (options.currency) form.append("currency", options.currency);
    return apiClient
      .post<UploadResult>("/integrations/upload", form, {
        headers: { "Content-Type": "multipart/form-data" },
      })
      .then((r) => r.data);
  },
  analyze: (file: File, kind: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("kind", kind);
    return apiClient
      .post<{
        headers: string[];
        suggested_mapping: Record<string, string>;
        sample_rows: Record<string, any>[];
      }>("/integrations/upload/analyze", form, {
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
