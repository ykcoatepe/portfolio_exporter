import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { msbHistoryQueryKey, parseMsbHistory, resolveMsbBaseUrl } from "../lib/msb";
import type { MsbReading } from "../lib/types";

export interface UseMsbHistoryOptions {
  days?: number;
  baseUrl?: string;
}

interface FetchMsbHistoryOptions {
  days?: number;
  baseUrl?: string;
}

const sanitizeDays = (input?: number): number => {
  if (typeof input !== "number" || !Number.isFinite(input)) {
    return 365;
  }
  const coerced = Math.floor(input);
  return coerced > 0 ? coerced : 365;
};

export const fetchMsbHistory = async (
  options: FetchMsbHistoryOptions = {},
): Promise<MsbReading[]> => {
  const days = sanitizeDays(options.days);
  const origin = resolveMsbBaseUrl(options.baseUrl);
  const endpoint = `${origin}/msb/history?days=${encodeURIComponent(days)}`;
  const response = await fetch(endpoint, {
    headers: { Accept: "application/json" },
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error(`MSB history request failed with status ${response.status}`);
  }

  const payload = (await response.json()) as unknown;
  return parseMsbHistory(payload);
};

export function useMsbHistory(
  options: UseMsbHistoryOptions = {},
): UseQueryResult<MsbReading[], Error> {
  const days = sanitizeDays(options.days);
  return useQuery<MsbReading[], Error>({
    queryKey: msbHistoryQueryKey(days),
    queryFn: () => fetchMsbHistory({ days, baseUrl: options.baseUrl }),
    staleTime: 5 * 60 * 1000,
  });
}
