import { create } from "zustand";
import {
  onIdTokenChanged,
  signInWithCustomToken,
  signInWithEmailAndPassword,
  signOut,
} from "firebase/auth";
import { authApi } from "@/api/auth";
import { onboardingApi } from "@/api/onboarding";
import { firebaseAuth, firebaseEnabled } from "@/lib/firebase";
import toast from "react-hot-toast";
import { useIndustryStore } from "@/stores/industry";
import { getErrorMessage } from "@/utils/errors";
import type {
  IndustryCode,
  LoginRequest,
  OnboardingState,
  SessionInfo,
  UserRole,
} from "@/types/api";

// Dev-fallback persistence keys. In Firebase mode the SDK owns token storage
// (IndexedDB), so we never persist a bearer token in localStorage there.
const DEV_TOKEN_KEY = "sanket.dev.token";
const DEV_SESSION_KEY = "sanket.dev.session";

/**
 * Keep the persisted session snapshot's onboarding slice in step with the store.
 *
 * The snapshot is written at login/signup and was never rewritten afterwards,
 * so it went stale the moment the wizard advanced. Anything that reloads the
 * page reads this blob, which is why a completed setup could still bounce to
 * step 1.
 */
function persistOnboarding(o: OnboardingState | null): void {
  try {
    const raw = localStorage.getItem(DEV_SESSION_KEY);
    if (!raw) return;
    const session = JSON.parse(raw) as SessionInfo;
    session.onboarding = o ?? undefined;
    localStorage.setItem(DEV_SESSION_KEY, JSON.stringify(session));
  } catch {
    /* storage unavailable or corrupt — the in-memory slice is still correct */
  }
}

interface AuthState {
  ready: boolean; // bootstrap finished — gates route guards to avoid flicker
  accessToken: string | null; // latest bearer (kept fresh for the WS handshake)
  userId: string | null;
  tenantId: string | null;
  role: UserRole | null;
  industry: IndustryCode | null;
  email: string | null;
  fullName: string | null;
  isAuthenticated: boolean;
  /** Setup readiness (null = legacy/demo tenant, treated as complete). */
  onboarding: OnboardingState | null;

  bootstrap: () => void;
  login: (body: LoginRequest, forceDev?: boolean) => Promise<SessionInfo>;
  /** Start the shared public demo session — no credentials touch the client. */
  loginSandbox: () => Promise<SessionInfo>;
  verifySession: (token: string) => Promise<SessionInfo>;
  logout: () => Promise<void>;
  /** Returns a valid (auto-refreshed in Firebase mode) bearer, or null. */
  getToken: () => Promise<string | null>;
  /** Back-compat shim for the axios 401 handler: refresh + return the token. */
  refresh: () => Promise<string | null>;
  setSession: (s: SessionInfo, token: string | null) => void;
  /** Update just the onboarding slice (after a wizard step persists). */
  setOnboarding: (o: OnboardingState | null) => void;
  /**
   * Swap in a re-minted bearer without re-running the whole session bootstrap.
   * Used after the industry step, which returns a token carrying the new `ind`
   * claim. Persists so a reload keeps the corrected claim.
   */
  replaceToken: (token: string) => void;
  /**
   * Re-read setup readiness from the server and persist it.
   *
   * The `onboarding` slice used to come only from the login-time
   * `sanket.dev.session` snapshot, which the wizard never rewrote — so a full
   * page load after finishing setup rehydrated `in_progress` and
   * OnboardingGate bounced the tenant back to step 1.
   */
  refreshOnboarding: () => Promise<OnboardingState | null>;
  /** Back-compat shim for TopBar: identity fields from store state. */
  decodeToken: () => {
    sub: string | null;
    tid: string | null;
    role: UserRole | null;
    ind: IndustryCode | null;
    email: string | null;
    name: string | null;
  } | null;
}

const CLEARED = {
  accessToken: null,
  userId: null,
  tenantId: null,
  role: null,
  industry: null,
  email: null,
  fullName: null,
  isAuthenticated: false,
  onboarding: null,
} as const;

let bootstrapped = false;

// First sign-in fans out into concurrent /auth/session calls (the explicit
// login() call races the onIdTokenChanged listener the sign-in triggers). They
// would each auto-provision the user and collide on uq_users_tenant_email, so
// we collapse any overlapping verifications into a single in-flight request.
const sessionCache = new Map<string, Promise<SessionInfo>>();
const verifySessionOnce = (token: string): Promise<SessionInfo> => {
  if (!sessionCache.has(token)) {
    const p = authApi.session(token).finally(() => {
      sessionCache.delete(token);
    });
    sessionCache.set(token, p);
  }
  return sessionCache.get(token)!;
};

export const useAuthStore = create<AuthState>()((set, get) => ({
  ready: false,
  ...CLEARED,

  setSession: (s, token) => {
    // Project the industry first, synchronously, so nothing can observe an
    // authenticated session that has no industry yet — that gap is what let
    // another industry's UI flash for a frame during bootstrap.
    useIndustryStore.getState().setSessionIndustry(s.active_industry);
    set({
      accessToken: token,
      userId: s.user_id,
      tenantId: s.tenant_id,
      role: s.role,
      industry: s.active_industry,
      email: s.email,
      fullName: s.full_name,
      isAuthenticated: true,
      onboarding: s.onboarding ?? null,
    });
  },

  // Also rewrite the persisted snapshot. Without this the update was
  // in-memory only: SPA navigation looked correct, but F5 / a typed URL / a
  // new tab rehydrated the stale login-time blob and OnboardingGate sent a
  // tenant who had just finished setup back to step 1 (docs/audit/02 P0-3).
  setOnboarding: (o) => {
    set({ onboarding: o });
    persistOnboarding(o);
  },

  replaceToken: (token) => {
    set({ accessToken: token });
    try {
      localStorage.setItem(DEV_TOKEN_KEY, token);
    } catch {
      /* storage may be unavailable; the in-memory token still works */
    }
  },

  refreshOnboarding: async () => {
    try {
      const state = await onboardingApi.getState();
      get().setOnboarding(state);
      return state;
    } catch {
      // Never block the app on this: the persisted snapshot is a usable
      // fallback, and a hard failure here would lock the user out of a
      // workspace they can legitimately reach.
      return get().onboarding;
    }
  },

  bootstrap: () => {
    if (bootstrapped) return;
    bootstrapped = true;

    if (firebaseEnabled && firebaseAuth) {
      // Firebase restores the session and rotates the ID token for us.
      onIdTokenChanged(firebaseAuth, async (user) => {
        if (!user) {
          set({ ...CLEARED, ready: true });
          return;
        }
        try {
          const token = await user.getIdToken();
          set({ accessToken: token });
          if (!get().isAuthenticated) {
            const s = await verifySessionOnce(token);
            get().setSession(s, token);
            // Server is authoritative for setup readiness — see below.
            void get().refreshOnboarding();
          }
        } catch (err) {
          const status = (err as { response?: { status?: number } })?.response?.status;
          const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
          // "google_account_not_provisioned" means the user just signed in via
          // Google for the first time but has no SANKET account yet.  The Login
          // page's handleGoogleSignIn handler will surface the onboarding modal;
          // we just clear auth silently here so the page stays on /login.
          if (status !== 404 || detail !== "google_account_not_provisioned") {
            console.error("Firebase session bootstrap failed:", err);
            toast.error(getErrorMessage(err, "Backend session verification failed. Please try again."));
          }
          set({ ...CLEARED });
        } finally {
          set({ ready: true });
        }

      });
      return;
    }

    // Dev fallback: restore the persisted dev session, if any.
    // Gated on whether Firebase is actually configured, NOT on Vite's build
    // mode — a production build of this frontend (e.g. the Docker image)
    // still uses the dev-login fallback whenever Firebase env vars are
    // unset, and import.meta.env.DEV is always false in that build, which
    // previously meant the token was never persisted and every hard
    // reload / direct URL navigation silently logged the user out.
    if (!firebaseEnabled) {
      try {
        const token = localStorage.getItem(DEV_TOKEN_KEY);
        const raw = localStorage.getItem(DEV_SESSION_KEY);
        if (token && raw) {
          // Decode the JWT payload (no signature verification — just check exp).
          // An expired token would be rejected by the middleware on the first
          // API call and trigger the "Session expired" logout flow, so we clear
          // it here instead so the user lands on the login page cleanly.
          const payloadB64 = token.split(".")[1];
          const payload = payloadB64
            ? JSON.parse(atob(payloadB64.replace(/-/g, "+").replace(/_/g, "/")))
            : null;
          const isExpired = payload?.exp && payload.exp * 1000 < Date.now();
          if (isExpired) {
            localStorage.removeItem(DEV_TOKEN_KEY);
            localStorage.removeItem(DEV_SESSION_KEY);
          } else {
            const s = JSON.parse(raw) as SessionInfo;
            get().setSession(s, token);
            // The snapshot gets the UI on screen without a round-trip, but the
            // server owns the truth. Re-read it so a stale `in_progress` from
            // signup cannot bounce a tenant who has since finished setup back
            // into the wizard (docs/audit/02 P0-3). Fire-and-forget: the guard
            // re-renders when the slice updates.
            void get().refreshOnboarding();
          }
        }
      } catch {
        /* ignore corrupt persisted state */
      }
    }
    set({ ready: true });
  },

  login: async (body, forceDev = false) => {
    if (!forceDev && firebaseEnabled && firebaseAuth) {
      const cred = await signInWithEmailAndPassword(
        firebaseAuth,
        body.email,
        body.password,
      );
      // Force-refresh so freshly-provisioned custom claims are in the token.
      const token = await cred.user.getIdToken(true);
      const s = await verifySessionOnce(token);
      get().setSession(s, token);
      return s;
    }

    const r = await authApi.devLogin(body);
    // Persist whenever Firebase isn't configured (this is the dev-login
    // path) — not gated on Vite build mode, see bootstrap() above.
    if (!firebaseEnabled) {
      try {
        localStorage.setItem(DEV_TOKEN_KEY, r.access_token);
        localStorage.setItem(DEV_SESSION_KEY, JSON.stringify(r));
      } catch {
        /* storage may be unavailable; session still works for this tab */
      }
    }
    get().setSession(r, r.access_token);
    return r;
  },

  loginSandbox: async () => {
    // Auth happens server-side: the backend returns a Firebase custom token
    // (real mode) or a dev token (local) — never a password. We never embed
    // demo credentials in the bundle.
    const r = await authApi.sandboxSession();

    if (r.mode === "firebase" && r.custom_token && firebaseEnabled && firebaseAuth) {
      const cred = await signInWithCustomToken(firebaseAuth, r.custom_token);
      // Custom token has claims embedded directly, so no force refresh is needed.
      const token = await cred.user.getIdToken();
      const s = await verifySessionOnce(token);
      get().setSession(s, token);
      return s;
    }

    if (r.mode === "dev" && r.access_token) {
      const session: SessionInfo = {
        user_id: r.user_id,
        tenant_id: r.tenant_id,
        role: r.role,
        active_industry: r.active_industry,
        email: r.email,
        full_name: r.full_name,
      };
      if (!firebaseEnabled) {
        try {
          localStorage.setItem(DEV_TOKEN_KEY, r.access_token);
          localStorage.setItem(DEV_SESSION_KEY, JSON.stringify(session));
        } catch {
          /* storage may be unavailable; session still works for this tab */
        }
      }
      get().setSession(session, r.access_token);
      return session;
    }

    throw new Error("Unexpected sandbox session response");
  },

  verifySession: async (token) => {
    const s = await verifySessionOnce(token);
    get().setSession(s, token);
    return s;
  },

  logout: async () => {
    try {
      await authApi.logout();
    } catch {
      /* best effort */
    }
    if (firebaseEnabled && firebaseAuth) {
      try {
        await signOut(firebaseAuth);
      } catch {
        /* ignore */
      }
    }
    try {
      localStorage.removeItem(DEV_TOKEN_KEY);
      localStorage.removeItem(DEV_SESSION_KEY);
    } catch {
      /* ignore */
    }
    // Clear the projected industry with the rest of the session. It no longer
    // persists, so this only guards the in-memory case: without it the next
    // login in the same tab could briefly render the previous account's
    // industry — a stale "GxP · 21 CFR Part 11" badge on a Fashion workspace.
    try {
      useIndustryStore.getState().setSessionIndustry(null);
    } catch {
      /* ignore */
    }
    set({ ...CLEARED, ready: true });
  },

  getToken: async () => {
    if (firebaseEnabled && firebaseAuth?.currentUser) {
      try {
        const token = await firebaseAuth.currentUser.getIdToken();
        set({ accessToken: token });
        return token;
      } catch {
        return null;
      }
    }
    return get().accessToken;
  },

  refresh: async () => {
    if (firebaseEnabled && firebaseAuth?.currentUser) {
      try {
        const token = await firebaseAuth.currentUser.getIdToken(true);
        set({ accessToken: token });
        return token;
      } catch {
        return null;
      }
    }
    // Dev tokens are not refreshable — signal the caller to re-authenticate.
    return null;
  },

  decodeToken: () => {
    const s = get();
    if (!s.isAuthenticated) return null;
    return {
      sub: s.userId,
      tid: s.tenantId,
      role: s.role,
      ind: s.industry,
      email: s.email,
      name: s.fullName,
    };
  },
}));