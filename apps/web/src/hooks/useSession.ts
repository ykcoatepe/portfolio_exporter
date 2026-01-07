import { useEffect } from "react";
import { useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";

import { resolveApiBaseUrl } from "../lib/http";
import type { MarketSession } from "../lib/types";
import { normalizeSession } from "../lib/session";

const SESSION_QUERY_KEY = ["portfolio", "session"] as const;
const nodeEnv =
  typeof globalThis !== "undefined" && "process" in globalThis
    ? (globalThis as { process?: { env?: { NODE_ENV?: string } } }).process?.env
        ?.NODE_ENV
    : undefined;
const isTestEnvironment =
  (typeof import.meta !== "undefined" && import.meta.env?.MODE === "test") ||
  nodeEnv === "test";
let sessionEndpointDisabled = false;

async function fetchSession(baseUrl = ""): Promise<MarketSession | null> {
  const origin = resolveApiBaseUrl(baseUrl);
  const endpoint = `${origin}/session`;
  const response = await fetch(endpoint, {
    headers: { Accept: "application/json" },
    credentials: "include",
  });

  if (response.status === 404) {
    if (!isTestEnvironment) {
      sessionEndpointDisabled = true;
    }
    return null;
  }
  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }

  const payload = await response.json();
  const session = normalizeSession(payload);
  if (!session) {
    throw new Error("Invalid session payload");
  }
  return session;
}

export function useSession(
  sessionSeed?: MarketSession | null,
): UseQueryResult<MarketSession | null, Error> {
  const queryClient = useQueryClient();
  const shouldFetch = sessionSeed == null && !sessionEndpointDisabled;

  useEffect(() => {
    if (sessionSeed === undefined) {
      return;
    }
    if (sessionSeed === null) {
      return;
    }
    queryClient.setQueryData(SESSION_QUERY_KEY, sessionSeed);
  }, [queryClient, sessionSeed]);

  return useQuery<MarketSession | null, Error>({
    queryKey: SESSION_QUERY_KEY,
    queryFn: () => fetchSession(),
    staleTime: 15_000,
    refetchInterval: shouldFetch ? 30_000 : false,
    retry: false,
    enabled: shouldFetch,
  });
}
