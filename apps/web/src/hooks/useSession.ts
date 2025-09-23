import { useEffect } from "react";
import { useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";

import type { MarketSession } from "../lib/types";
import { normalizeSession } from "../lib/session";

const SESSION_QUERY_KEY = ["portfolio", "session"] as const;

async function fetchSession(baseUrl = ""): Promise<MarketSession> {
  const origin =
    baseUrl ||
    (typeof window !== "undefined" ? window.location.origin : "http://localhost");
  const sanitizedBase = origin.replace(/\/+$/, "");
  const endpoint = `${sanitizedBase}/session`;
  const response = await fetch(endpoint, {
    headers: { Accept: "application/json" },
    credentials: "include",
  });

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

  useEffect(() => {
    if (sessionSeed === undefined) {
      return;
    }
    if (sessionSeed === null) {
      queryClient.setQueryData(SESSION_QUERY_KEY, null);
      queryClient.invalidateQueries({ queryKey: SESSION_QUERY_KEY, refetchType: "active" });
      return;
    }
    queryClient.setQueryData(SESSION_QUERY_KEY, sessionSeed);
  }, [queryClient, sessionSeed]);

  return useQuery<MarketSession | null, Error>({
    queryKey: SESSION_QUERY_KEY,
    queryFn: () => fetchSession(),
    staleTime: 15_000,
    refetchInterval: 30_000,
    retry: false,
  });
}
