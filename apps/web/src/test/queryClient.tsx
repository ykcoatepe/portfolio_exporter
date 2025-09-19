import type { ReactElement } from "react";
import {
  QueryClient,
  QueryClientProvider,
  type DefaultOptions,
} from "@tanstack/react-query";
import { render } from "@testing-library/react";

const defaultQueryOptions: DefaultOptions = {
  queries: {
    retry: false,
    refetchOnWindowFocus: false,
    refetchInterval: false,
    staleTime: Infinity,
    gcTime: 0,
  },
};

export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: defaultQueryOptions,
    logger: {
      log: console.log,
      warn: console.warn,
      error: () => {
        // Silence query errors in tests; assertions handle failures.
      },
    },
  });
}

export function renderWithClient(ui: ReactElement) {
  const client = createTestQueryClient();
  return {
    client,
    ...render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>),
  };
}
