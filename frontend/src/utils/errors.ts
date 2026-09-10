/**
 * Safely extract a human-readable message from an API error (axios) or any
 * thrown value, so it can be passed to toast.error() / rendered in JSX.
 *
 * FastAPI validation errors (HTTP 422) return `detail` as an ARRAY of
 * objects shaped like { type, loc, msg, input, ctx }. Passing that array
 * (or one of its objects) directly to toast.error()/JSX crashes the app
 * with "Objects are not valid as a React child" (minified React error #31).
 * This helper guarantees a string is always returned.
 */
export function getErrorMessage(err: unknown, fallback = "Something went wrong"): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;

  if (detail != null) {
    if (typeof detail === "string") return detail;

    if (Array.isArray(detail)) {
      const msgs = detail
        .map((d) => {
          if (typeof d === "string") return d;
          if (d && typeof d === "object" && "msg" in d) return String((d as { msg?: unknown }).msg ?? "");
          return "";
        })
        .filter(Boolean);
      if (msgs.length) return msgs.join(", ");
    }

    if (typeof detail === "object" && "msg" in (detail as Record<string, unknown>)) {
      return String((detail as { msg?: unknown }).msg ?? fallback);
    }

    // Last resort: don't render the raw object, but don't lose the info either.
    if (typeof detail === "object") {
      try {
        return JSON.stringify(detail);
      } catch {
        return fallback;
      }
    }
  }

  const message = (err as { message?: unknown })?.message;
  if (typeof message === "string" && message.length) return message;

  return fallback;
}

/** Whether the API returned a 5xx response handled by the global interceptor. */
export function isServerError(err: unknown): boolean {
  const status = (err as { response?: { status?: unknown } })?.response?.status;
  return typeof status === "number" && status >= 500;
}

/**
 * Surface intentional upstream-unavailable responses while keeping unexpected
 * application failures generic so internal details never reach the browser.
 */
export function getServerErrorMessage(err: unknown): string {
  const status = (err as { response?: { status?: unknown } })?.response?.status;
  if (status === 502 || status === 503) {
    return getErrorMessage(err, "Server error — try again shortly");
  }
  return "Server error — try again shortly";
}
