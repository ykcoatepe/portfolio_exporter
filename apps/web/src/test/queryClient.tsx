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

const isTestEnvironment = typeof process !== "undefined" && process.env?.NODE_ENV === "test";

if (isTestEnvironment) {
  const originalError = console.error.bind(console);
  console.error = (...args: Parameters<typeof originalError>) => {
    if (typeof args[0] === "string" && args[0].includes("react-query")) {
      return;
    }
    originalError(...args);
  };
}

export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: defaultQueryOptions,
  });
}

export function renderWithClient(ui: ReactElement) {
  const client = createTestQueryClient();
  return {
    client,
    ...render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>),
  };
}
