import { create } from "zustand";
import {
  onIdTokenChanged,
  signInWithCustomToken,
  signInWithEmailAndPassword,
  signOut,
} from "firebase/auth";
import { authApi } from "@/api/auth";
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

interface AuthState {
  ready: boolean; // bootstrap finished — gates route guards to avoid flicker
  accessToken: string | null; // latest bearer (kept fresh for the WS handshake)
  userId: string | null;
  tenantId: string | null;
  role: UserRole | null;
  defaultIndustry: IndustryCode | null;
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
  defaultIndustry: null,
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
    set({
      accessToken: token,
      userId: s.user_id,
      tenantId: s.tenant_id,
      role: s.role,
      defaultIndustry: s.active_industry,
      email: s.email,
      fullName: s.full_name,
      isAuthenticated: true,
      onboarding: s.onboarding ?? null,
    });
  },

  setOnboarding: (o) => set({ onboarding: o }),

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
    // The active-industry store persists to localStorage independently of the
    // session and is NOT cleared above. Left alone, the next login (same
    // browser, possibly a different tenant/account) briefly renders with the
    // previous account's industry — e.g. a stale "GxP · 21 CFR Part 11" badge
    // flashing on a Fashion tenant right after login — until the post-login
    // sync overwrites it a moment later. Reset it here so every fresh session
    // starts from the same default the store itself defines.
    try {
      useIndustryStore.getState().reset();
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
      ind: s.defaultIndustry,
      email: s.email,
      name: s.fullName,
    };
  },
}));