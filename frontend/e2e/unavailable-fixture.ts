// frontend/e2e/unavailable-fixture.ts
// Synthetic browser-review responses only. Never imported by src/ or shipped.
// Every request fails as "service unavailable" so screens show their honest
// unavailable states. A 503 (not 401) keeps the client from logging out.
import { AxiosError, type AxiosResponse, type InternalAxiosRequestConfig } from "axios";
import { apiClient } from "../src/api/client";

export function installUnavailableFixture() {
  apiClient.defaults.adapter = async (config: InternalAxiosRequestConfig) => {
    const response = {
      data: { detail: "Unavailable in isolated design review" },
      status: 503,
      statusText: "Service Unavailable",
      headers: {},
      config,
    } as AxiosResponse;
    throw new AxiosError("Unavailable in isolated design review", "ERR_BAD_RESPONSE", config, null, response);
  };
}
