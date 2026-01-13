import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import App from "./App";
import "./index.css";
import { setupQueryPersistence } from "./lib/queryPersistence";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5_000, // Consider data stale after 5 seconds
      gcTime: 1000 * 60 * 60 * 24, // Keep in cache for 24 hours
      refetchOnMount: true, // Refetch on mount
      refetchOnWindowFocus: false, // Don't refetch on focus
      retry: 1,
    },
  },
});

// Setup query persistence to localStorage
setupQueryPersistence(queryClient);

function AppProviders(): JSX.Element {
  return (
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  );
}

async function enableMocking() {
  // Only use MSW if explicitly enabled with VITE_USE_MOCKS=true
  // By default, use real backend via Vite proxy
  if (!import.meta.env.DEV || import.meta.env.VITE_USE_MOCKS !== "true") {
    return;
  }
  const { worker } = await import("./mocks/browser");
  await worker.start({ onUnhandledRequest: "bypass" });
}

const container = document.getElementById("root");
if (!container) {
  throw new Error("Root container not found");
}

const renderApp = () => {
  ReactDOM.createRoot(container).render(
    <React.StrictMode>
      <AppProviders />
    </React.StrictMode>,
  );
};

enableMocking()
  .catch((error) => {
    if (import.meta.env.DEV) {
      // eslint-disable-next-line no-console
      console.error("Failed to start mock service worker", error);
    }
  })
  .finally(renderApp);
