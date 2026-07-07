/**
 * Firebase initialisation.
 *
 * When the `VITE_FIREBASE_*` build vars are present we initialise the Firebase
 * Auth SDK and the app authenticates against Firebase. When they are absent
 * (local dev) `firebaseEnabled` is false and the app falls back to the backend
 * dev-login endpoint — no Firebase project required.
 *
 * Only public, non-secret config is read here; it is safe in the browser bundle.
 */
import { initializeApp, type FirebaseApp } from "firebase/app";
import { getAuth, type Auth } from "firebase/auth";

const config = {
  apiKey: import.meta.env.VITE_FIREBASE_API_KEY as string | undefined,
  authDomain: import.meta.env.VITE_FIREBASE_AUTH_DOMAIN as string | undefined,
  projectId: import.meta.env.VITE_FIREBASE_PROJECT_ID as string | undefined,
  appId: import.meta.env.VITE_FIREBASE_APP_ID as string | undefined,
};

/** True when real Firebase credentials are configured for the frontend. */
export const firebaseEnabled = Boolean(config.apiKey && config.projectId);

let app: FirebaseApp | null = null;
let auth: Auth | null = null;

if (firebaseEnabled) {
  app = initializeApp({
    apiKey: config.apiKey,
    authDomain: config.authDomain ?? `${config.projectId}.firebaseapp.com`,
    projectId: config.projectId,
    appId: config.appId,
  });
  auth = getAuth(app);
}

/** Firebase Auth instance, or null in dev-fallback mode. */
export const firebaseAuth = auth;
