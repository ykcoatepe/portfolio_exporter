import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "./index.css";
import PSDPage from "./pages/PSD";

const queryClient = new QueryClient();

async function enableMocking() {
  if (!import.meta.env.DEV) {
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
      <QueryClientProvider client={queryClient}>
        <PSDPage />
      </QueryClientProvider>
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
