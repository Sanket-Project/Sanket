import { apiClient } from "@/api/client";
import type { PharmaBatchExpiring } from "@/types/api";

export const pharmaApi = {
  releaseBatch: (batchId: string) =>
    apiClient.post<{
      batch_id: string;
      lot_number: string;
      gxp_status: string;
      qa_released_by: string;
      qa_released_at: string;
    }>(`/pharma/batches/${batchId}/release`).then((r) => r.data),
  expiringBatches: (days = 90) =>
    apiClient
      .get<{ threshold_days: number; count: number; batches: PharmaBatchExpiring[] }>(
        `/pharma/batches/expiring`,
        { params: { days } },
      )
      .then((r) => r.data),
};
