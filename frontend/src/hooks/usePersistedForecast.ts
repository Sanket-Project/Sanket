import { useEffect, useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { forecastsApi, type LatestForecastResponse } from "@/api/forecasts";
import { useWorkspaceIndustry } from "@/hooks/useWorkspaceIndustry";
import { useAuthStore } from "@/stores/auth";
import { getErrorMessage } from "@/utils/errors";

const active = (status?: string) => status === "pending" || status === "running";

/** Reading a forecast never performs inference. Refresh is a separate durable job. */
export function usePersistedForecast({ horizon, view = "skus", offset = 0, limit = 6, search = "", runId }: {
  horizon: number;
  view?: "summary" | "skus";
  offset?: number;
  limit?: number;
  search?: string;
  runId?: string;
}) {
  const industry = useWorkspaceIndustry();
  const tenant = useAuthStore((state) => state.tenantId);
  const client = useQueryClient();
  const root = ["forecasts", "latest", tenant, industry] as const;
  const attempted = useRef(new Set<string>());
  const reconciledAt = useRef(new Map<string, number>());
  const deferredRequest = useRef<{ force: boolean } | null>(null);
  const query = useQuery({
    queryKey: [...root, view, offset, limit, search, runId ?? "latest"],
    queryFn: () => forecastsApi.latest({ view, offset, limit, ...(search ? { search } : {}), ...(runId ? { run_id: runId } : {}) }),
    retry: false,
    refetchInterval: (q) => active(q.state.data?.refresh?.status) ? 3000 : false,
  });
  const refresh = useMutation({
    mutationFn: (force: boolean) => forecastsApi.refresh({ horizon, force, force_zero_shot: true }),
    onSuccess: (result, force) => {
      if (result.refresh?.industry && result.refresh.industry !== industry && active(result.refresh.status)) {
        deferredRequest.current = { force: force || Boolean(deferredRequest.current?.force) };
      } else {
        deferredRequest.current = null;
      }
      client.setQueriesData<LatestForecastResponse>({ queryKey: root }, (previous) =>
        previous ? { ...previous, refresh: result.refresh } : previous);
      void client.invalidateQueries({ queryKey: root });
    },
    onError: () => { deferredRequest.current = null; },
  });
  const { mutate } = refresh;
  const saved = query.data;
  const foreignRefresh = Boolean(saved?.refresh?.industry && saved.refresh.industry !== industry);
  const waitingForOtherIndustry = foreignRefresh && active(saved?.refresh?.status);
  useEffect(() => {
    if (!saved) return;
    // Admission is tenant-wide. A competing industry's job has not fulfilled
    // this request; permit a new attempt once polling observes its slot clear.
    if (waitingForOtherIndustry) attempted.current.clear();
    if (!foreignRefresh && active(saved.refresh?.status)) deferredRequest.current = null;
    if (saved.refresh?.status === "pending") {
      const touched = Date.parse(saved.refresh.updated_at ?? saved.refresh.created_at);
      const now = Date.now();
      const last = reconciledAt.current.get(saved.refresh.id) ?? 0;
      // Repair the reservation/enqueue crash window using the same server job.
      if (now - touched >= 30000 && now - last >= 30000 && !refresh.isPending && !refresh.isError) {
        reconciledAt.current.set(saved.refresh.id, now);
        mutate(false);
      }
      return;
    }
    if (waitingForOtherIndustry) return;
    const key = `${tenant}:${industry}:${saved.forecast?.run_id ?? "none"}:${horizon}`;
    if (deferredRequest.current && !refresh.isPending) {
      const request = deferredRequest.current;
      deferredRequest.current = null;
      attempted.current.add(key);
      mutate(request.force);
      return;
    }
    if (!saved.stale && saved.forecast?.location_status !== "pending" &&
        (saved.forecast?.horizon_weeks ?? 0) >= horizon) {
      attempted.current.clear();
      return;
    }
    if (active(saved.refresh?.status) || (!foreignRefresh && saved.refresh?.status === "failed") || attempted.current.has(key)) return;
    attempted.current.add(key);
    mutate(false);
  }, [saved, query.dataUpdatedAt, tenant, industry, horizon, mutate, refresh.isPending, refresh.isError, foreignRefresh, waitingForOtherIndustry]);

  return {
    ...query,
    data: saved?.forecast ?? null,
    stale: saved?.stale ?? false,
    refreshing: active(saved?.refresh?.status) || refresh.isPending,
    generating: !foreignRefresh && active(saved?.refresh?.status),
    waitingForOtherIndustry,
    refreshStatus: saved?.refresh ?? null,
    refreshError: refresh.isError ? getErrorMessage(refresh.error, "Forecast refresh failed")
      : !foreignRefresh && saved?.refresh?.status === "failed" ? saved.refresh.error || "Forecast refresh failed" : null,
    requestRefresh: () => mutate(true),
  };
}
