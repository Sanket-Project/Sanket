import axios, { AxiosError, type InternalAxiosRequestConfig } from "axios";
import toast from "react-hot-toast";
import { useAuthStore } from "@/stores/auth";
import { useIndustryStore } from "@/stores/industry";
import { getErrorMessage } from "@/utils/errors";

const baseURL = import.meta.env.VITE_API_BASE_URL ?? "/api/v1";

// Deduplicate toasts: prevent the same error firing multiple times within 3s
// (e.g. 3 parallel queries all failing = only 1 toast shown)
const _toastShownAt: Record<string, number> = {};
function dedupeToast(key: string, message: string) {
  const now = Date.now();
  if (_toastShownAt[key] && now - _toastShownAt[key] < 3000) return;
  _toastShownAt[key] = now;
  toast.error(message);
}

export const apiClient = axios.create({
  baseURL,
  headers: { "Content-Type": "application/json" },
  timeout: 60000,
});

// NOTE: there is intentionally no direct ML-service client. All forecast
// requests go through the SANKET backend (`/forecasts/*`), which authenticates
// the user, derives tenant_id server-side, and proxies to the internal ML
// service with a service token. The browser must never reach the ML service.

apiClient.interceptors.request.use(async (config: InternalAxiosRequestConfig) => {
  // getToken() returns a freshly auto-refreshed Firebase ID token (or the dev
  // token in fallback mode). Don't overwrite an Authorization header a caller
  // set explicitly (e.g. the /auth/session bootstrap call).
  if (!config.headers.Authorization) {
    const token = await useAuthStore.getState().getToken();
    if (token) config.headers.Authorization = `Bearer ${token}`;
  }
  const industry = useIndustryStore.getState().activeIndustry;
  if (industry) config.headers["X-Industry-Code"] = industry;
  return config;
});

let isRefreshing = false;
let pending: Array<(t: string | null) => void> = [];

apiClient.interceptors.response.use(
  (r) => r,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig & {
      _retry?: boolean;
    };
    if (!error.response) {
      // No response can mean a true network failure OR a client-side timeout
      // (axios aborts long requests). Distinguish them so a slow forecast isn't
      // mislabelled as the backend being down.
      if (error.code === "ECONNABORTED" || /timeout/i.test(error.message)) {
        dedupeToast(
          "timeout",
          "Request timed out — the server is taking longer than expected",
        );
      } else {
        dedupeToast("network", "Network error — backend unreachable");
      }
      return Promise.reject(error);
    }
    const status = error.response.status;
    const isAuthEndpoint = (original.url ?? "").startsWith("/auth/");

    if (status === 401 && !original._retry && !isAuthEndpoint) {
      original._retry = true;
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          pending.push((token) => {
            if (token) {
              original.headers!.Authorization = `Bearer ${token}`;
              resolve(apiClient(original));
            } else {
              reject(error);
            }
          });
        });
      }
      isRefreshing = true;
      try {
        // Firebase mode: force a token refresh and retry once. Dev mode:
        // refresh() returns null → fall through to sign-out.
        const refreshed = await useAuthStore.getState().refresh();
        pending.forEach((cb) => cb(refreshed));
        pending = [];
        if (refreshed) {
          original.headers!.Authorization = `Bearer ${refreshed}`;
          return apiClient(original);
        }
        await useAuthStore.getState().logout();
        toast.error("Session expired — please sign in again");
      } catch {
        pending.forEach((cb) => cb(null));
        pending = [];
        await useAuthStore.getState().logout();
        toast.error("Session expired — please sign in again");
      } finally {
        isRefreshing = false;
      }
    }

    if (status >= 500) {
      dedupeToast("server_error", "Server error — try again shortly");
    } else if (status === 403) {
      dedupeToast("forbidden", "You do not have permission for that action");
    } else if (status === 404) {
      // surfaces inline in components, not as global toast
    } else if (status === 409) {
      toast.error(getErrorMessage(error, "Conflict"));
    }
    // 422 (validation) errors surface inline in the component that made the
    // call (see getErrorMessage usages) rather than as a global toast here.

    return Promise.reject(error);
  },
);
