import { useEffect } from "react";
import { useAuthStore } from "@/stores/auth";

/**
 * Auth accessor. Ensures the one-time bootstrap (Firebase listener / dev-session
 * restore) has been kicked off. Token refresh is handled by the Firebase SDK
 * (or by the axios 401 handler in dev mode), so nothing to poll here.
 */
export const useAuth = () => {
  const auth = useAuthStore();
  useEffect(() => {
    auth.bootstrap();
  }, [auth]);
  return auth;
};
