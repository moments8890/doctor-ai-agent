import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,        // 1 min default
      gcTime: 5 * 60_000,       // 5 min garbage collection
      retry: 1,
      refetchOnWindowFocus: true,
    },
  },
});
