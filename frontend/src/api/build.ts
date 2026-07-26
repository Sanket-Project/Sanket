import { apiClient } from "./client";

export interface BuildInfo {
  /** Commit the running backend was built from, or "unknown" outside CI. */
  git_sha: string;
  status: string;
  db?: string;
  ml?: string;
}

/**
 * Reads the running backend's build stamp.
 *
 * This exists so "is what I reviewed actually deployed?" is answerable from
 * the UI. It was not: two rounds of payment fixes were reviewed as shipped
 * while the running build predated all of them, and nothing on screen could
 * contradict that.
 */
export const buildApi = {
  info: async (): Promise<BuildInfo> => {
    const { data } = await apiClient.get<BuildInfo>("/health");
    return data;
  },
};

/** First 7 characters, the length git itself abbreviates to. */
export function shortSha(sha: string | undefined): string {
  if (!sha) return "unknown";
  return sha === "unknown" || sha === "dev-local" ? sha : sha.slice(0, 7);
}
