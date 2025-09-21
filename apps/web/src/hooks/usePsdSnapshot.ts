import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import type { PSDSnapshot, PSDPositionsView } from "../lib/types";

export const PSD_SNAPSHOT_QUERY_KEY = ["psd", "snapshot"] as const;

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
    queryKey: PSD_SNAPSHOT_QUERY_KEY,
    queryFn: () => fetchPsdSnapshot(),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });
}

export function usePsdPositionsView(): UseQueryResult<PSDPositionsView | null, Error> {
  return useQuery<PSDSnapshot, Error, PSDPositionsView | null>({
    queryKey: PSD_SNAPSHOT_QUERY_KEY,
    queryFn: () => fetchPsdSnapshot(),
    select: (snapshot) => (snapshot.positions_view ?? null),
    refetchInterval: 30_000,
    staleTime: 15_000,
  });
}
