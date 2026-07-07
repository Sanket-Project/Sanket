import { apiClient } from "@/api/client";

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export const exportApi = {
  forecastXlsx: async (industry: string) => {
    const resp = await apiClient.get("/export/forecast.xlsx", { responseType: "blob" });
    triggerDownload(resp.data as Blob, `sanket_forecast_${industry}.xlsx`);
  },

  signalsCsv: async (industry: string, days = 30) => {
    const resp = await apiClient.get("/export/signals.csv", {
      params: { days },
      responseType: "blob",
    });
    triggerDownload(resp.data as Blob, `sanket_signals_${industry}_${days}d.csv`);
  },

  productsCsv: async () => {
    const resp = await apiClient.get("/export/products.csv", { responseType: "blob" });
    triggerDownload(resp.data as Blob, `sanket_products_${Date.now()}.csv`);
  },

  skusCsv: async () => {
    const resp = await apiClient.get("/export/skus.csv", { responseType: "blob" });
    triggerDownload(resp.data as Blob, `sanket_skus_${Date.now()}.csv`);
  },

  inventoryCsv: async () => {
    const resp = await apiClient.get("/export/inventory.csv", { responseType: "blob" });
    triggerDownload(resp.data as Blob, `sanket_inventory_${Date.now()}.csv`);
  },

  alertsCsv: async (industry: string) => {
    const resp = await apiClient.get("/export/alerts.csv", { responseType: "blob" });
    triggerDownload(resp.data as Blob, `sanket_alerts_${industry}_${Date.now()}.csv`);
  },
};
