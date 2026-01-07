import { useEffect } from "react";
import {
  useQuery,
  useQueryClient,
  type QueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";

import { parseMsbReading, resolveMsbBaseUrl, MSB_CURRENT_QUERY_KEY } from "../lib/msb";
import type { MsbReading } from "../lib/types";

export interface UseMsbCurrentOptions {
  baseUrl?: string;
}

const SSE_EVENT_NAME = "msb.update";
const SSE_PATH = "/sse";

const updateHistoryCache = (client: QueryClient, reading: MsbReading): void => {
  client.setQueriesData<MsbReading[]>({ queryKey: ["msb.history"] }, (existing) => {
    if (!existing) {
      return existing;
    }
    const filtered = existing.filter((entry) => entry.date !== reading.date);
    const next = [reading, ...filtered];
    const maxLength = existing.length > 0 ? existing.length : next.length;
    return next.slice(0, maxLength);
  });
};

export const fetchMsbCurrent = async (baseUrl?: string): Promise<MsbReading> => {
  const origin = resolveMsbBaseUrl(baseUrl);
  const endpoint = `${origin}/msb/current`;
  const response = await fetch(endpoint, {
    headers: { Accept: "application/json" },
    credentials: "include",
  });

  if (!response.ok) {
    if (response.status === 404) {
      throw new Error("No MSB history available");
    }
    throw new Error(`MSB current request failed with status ${response.status}`);
  }

  const payload = (await response.json()) as unknown;
  return parseMsbReading(payload);
};

export function useMsbCurrent(
  options: UseMsbCurrentOptions = {},
): UseQueryResult<MsbReading, Error> {
  const { baseUrl } = options;
  const queryClient = useQueryClient();

  const queryResult = useQuery<MsbReading, Error>({
    queryKey: MSB_CURRENT_QUERY_KEY,
    queryFn: () => fetchMsbCurrent(baseUrl),
    retry: false,
  });

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.EventSource === "undefined") {
      return;
    }

    const origin = resolveMsbBaseUrl(baseUrl);
    const source = new window.EventSource(`${origin}${SSE_PATH}`, {
      withCredentials: true,
    });

    const handler = (event: MessageEvent<string>) => {
      try {
        const payload = JSON.parse(event.data) as unknown;
        const reading = parseMsbReading(payload);
        queryClient.setQueryData(MSB_CURRENT_QUERY_KEY, reading);
        updateHistoryCache(queryClient, reading);
      } catch (error) {
        if (import.meta.env?.DEV) {
          // eslint-disable-next-line no-console -- surface parsing issues in development only.
          console.warn("Failed to process MSB SSE payload", error);
        }
      }
    };

    source.addEventListener(SSE_EVENT_NAME, handler);

    const onError = () => {
      source.close();
    };

    source.addEventListener("error", onError);

    return () => {
      source.removeEventListener(SSE_EVENT_NAME, handler);
      source.removeEventListener("error", onError);
      source.close();
    };
  }, [baseUrl, queryClient]);

  return queryResult;
}
