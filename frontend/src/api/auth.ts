import { apiClient } from "@/api/client";
import type {
  AuthConfig,
  DevLoginResponse,
  LoginRequest,
  SandboxSessionResponse,
  SessionInfo,
  SignUpRequest,
} from "@/types/api";

export interface GoogleSignUpRequest {
  id_token: string;
  workspace_slug: string;
  name: string;
}

export const authApi = {
  /** Public: which auth mode the backend is running (Firebase vs dev fallback). */
  config: () => apiClient.get<AuthConfig>("/auth/config").then((r) => r.data),

  /** Exchange a verified bearer token for the user's tenant context. */
  session: (token: string) =>
    apiClient
      .post<SessionInfo>("/auth/session", null, {
        headers: { Authorization: `Bearer ${token}` },
        timeout: 60000,
      })
      .then((r) => r.data),

  /** Local dev-only login (returns a short-lived dev token). */
  devLogin: (body: LoginRequest) =>
    apiClient.post<DevLoginResponse>("/auth/dev-login", body).then((r) => r.data),

  /** Start the shared public demo session (auth happens server-side). */
  sandboxSession: () =>
    apiClient
      .post<SandboxSessionResponse>("/auth/sandbox-session", null, { timeout: 60000 })
      .then((r) => r.data),

  /** Register a new user and tenant context (email/password signup). */
  signUp: (body: SignUpRequest) =>
    apiClient.post<{ status: string; user_id: string; tenant_id: string }>("/auth/signup", body).then((r) => r.data),

  /**
   * Provision a new SANKET tenant + user for a first-time Google sign-in.
   * Verifies the Firebase ID token server-side — no password involved.
   * Returns a SessionInfo on success (201).
   */
  googleSignup: (body: GoogleSignUpRequest) =>
    apiClient.post<SessionInfo>("/auth/google-signup", body, { timeout: 60000 }).then((r) => r.data),

  logout: () => apiClient.post("/auth/logout").then((r) => r.data),
};