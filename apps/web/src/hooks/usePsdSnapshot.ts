import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import type { PSDSnapshot } from "../lib/types";

export async function fetchPsdSnapshot(baseUrl = ""): Promise<PSDSnapshot> {
  const origin =
    baseUrl ||
    (typeof window !== "undefined" ? window.location.origin : "http://localhost");
  const sanitizedBase = origin.replace(/\/+$/, "");
  const endpoint = `${sanitizedBase}/state`;
  const response = await fetch(endpoint, {
    headers: { Accept: "application/json" },
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }

  const payload = (await response.json()) as PSDSnapshot;
  return payload;
}

export function usePsdSnapshot(): UseQueryResult<PSDSnapshot, Error> {
  return useQuery<PSDSnapshot, Error>({
    queryKey: ["psd", "snapshot"],
    queryFn: () => fetchPsdSnapshot(),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });
}
