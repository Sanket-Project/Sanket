import { QueryClient } from "@tanstack/react-query";

/** App-wide query defaults; one client is created per signed-in identity. */
export function createAppQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: (count, err) => {
          const status = (err as { response?: { status?: number } })?.response?.status;
          if (status && status < 500 && status !== 408) return false;
          return count < 2;
        },
        staleTime: 30_000,
        refetchOnWindowFocus: false,
      },
    },
  });
}
