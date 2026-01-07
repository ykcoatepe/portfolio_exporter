import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import App from "./App";
import "./index.css";

const queryClient = new QueryClient();

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
