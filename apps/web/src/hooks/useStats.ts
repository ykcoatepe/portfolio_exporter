import { useEffect } from "react";
import { useQuery, useQueryClient, type UseQueryResult } from "@tanstack/react-query";

import type { PortfolioStats, PortfolioStatsApiResponse } from "../lib/types";
import { normalizeSession } from "../lib/session";

const DEFAULT_BASE_URL = "http://localhost";
export const PSD_STATS_QUERY_KEY = ["psd", "stats", "current"] as const;
const STATS_SSE_EVENT = "psd.stats.update";
const SSE_PATH = "/sse";

const resolveBaseUrl = (baseUrl = ""): string => {
  const origin =
    baseUrl ||
    (typeof window !== "undefined" ? window.location.origin : DEFAULT_BASE_URL);
  return origin.replace(/\/+$/, "");
};

const toNullableNumber = (value: unknown): number | null => {
  if (value === null || value === undefined) {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const toPositiveCount = (value: unknown): number => {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0;
};

const toOptionalCount = (value: unknown): number | undefined => {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : undefined;
};

const toNullableString = (value: unknown): string | null => {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
};

const parseStatsPayload = (payload: PortfolioStatsApiResponse | null): PortfolioStats => {
  if (!payload) {
    return {
      netLiq: null,
      var95: null,
      marginPct: null,
      updatedAt: null,
      dayPnl: null,
      unrealizedPnl: null,
      sigmaTotal: null,
      sigmaPerDay: null,
      stalenessSec: null,
      servedAt: null,
      latestTs: null,
      dataSource: null,
      counts: {
        equities: 0,
        quotes: 0,
        optionLegs: 0,
        combos: 0,
        staleQuotes: 0,
      },
      rulesEvalMs: null,
      tradesPriorPositions: false,
      session: null,
      sessionInfo: null,
    };
  }

  const session = normalizeSession(payload.session ?? null);
  const sessionInfo = normalizeSession(payload.session_info ?? null);

  return {
    netLiq: toNullableNumber(payload.net_liq ?? payload.netLiq),
    var95: toNullableNumber(payload.var_95 ?? payload.var95 ?? payload.var95_1d_pct),
    marginPct: toNullableNumber(
      payload.margin_pct ?? payload.marginPct ?? payload.margin_used_pct,
    ),
    updatedAt: toNullableString(payload.updated_at ?? payload.updatedAt),
    dayPnl: toNullableNumber(payload.day_pnl ?? payload.dayPnl),
    unrealizedPnl: toNullableNumber(
      payload.unrealized_pnl ?? payload.unrealizedPnl,
    ),
    sigmaTotal: toNullableNumber(payload.sigma_total ?? payload.sigmaTotal),
    sigmaPerDay: toNullableNumber(payload.sigma_per_day ?? payload.sigmaPerDay),
    stalenessSec: toNullableNumber(payload.staleness_sec ?? payload.stalenessSec),
    servedAt: toNullableString(payload.served_at ?? payload.servedAt),
    latestTs: toNullableString(payload.meta?.latest_ts ?? null),
    dataSource: toNullableString(payload.data_source ?? payload.dataSource ?? null),
    counts: {
      equities: toPositiveCount(payload.equity_count),
      quotes: toPositiveCount(payload.quote_count),
      optionLegs: toPositiveCount(payload.option_legs_count),
      combos: toPositiveCount(payload.combos_matched),
      staleQuotes: toPositiveCount(payload.stale_quotes_count),
      rules: toOptionalCount(payload.rules_count),
      breaches: toOptionalCount(payload.breaches_count),
    },
    rulesEvalMs: toNullableNumber(
      payload.rules_eval_ms ?? payload.combos_detection_ms,
    ),
    tradesPriorPositions: Boolean(payload.trades_prior_positions ?? false),
    session,
    sessionInfo,
  };
};

export const fetchStats = async (baseUrl = ""): Promise<PortfolioStats> => {
  const origin = resolveBaseUrl(baseUrl);
  const endpoint = `${origin}/stats/current`;
  const response = await fetch(endpoint, {
    headers: { Accept: "application/json" },
    credentials: "include",
  });

  if (response.status === 204) {
    return parseStatsPayload(null);
  }

  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }

  const payload = (await response.json()) as PortfolioStatsApiResponse | null;
  return parseStatsPayload(payload ?? null);
};

export function useStats(baseUrl?: string): UseQueryResult<PortfolioStats, Error> {
  const queryClient = useQueryClient();
  const resolvedBaseUrl = resolveBaseUrl(baseUrl ?? "");

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.EventSource === "undefined") {
      return;
    }

    const source = new window.EventSource(`${resolvedBaseUrl}${SSE_PATH}`, {
      withCredentials: true,
    });

    const handler = (event: MessageEvent<string>) => {
      try {
        const data = event.data ? JSON.parse(event.data) : null;
        const parsed = parseStatsPayload(data);
        queryClient.setQueryData(PSD_STATS_QUERY_KEY, (current) => ({
          ...current,
          ...parsed,
        }));
      } catch (error) {
        if (import.meta.env?.DEV) {
          // eslint-disable-next-line no-console -- useful for diagnosing malformed payloads.
          console.warn("Failed to process PSD stats SSE payload", error);
        }
      }
    };

    const onError = () => {
      source.close();
    };

    source.addEventListener(STATS_SSE_EVENT, handler);
    source.addEventListener("error", onError);

    return () => {
      source.removeEventListener(STATS_SSE_EVENT, handler);
      source.removeEventListener("error", onError);
      source.close();
    };
  }, [queryClient, resolvedBaseUrl]);

  return useQuery<PortfolioStats, DefaultError>({
    queryKey: PSD_STATS_QUERY_KEY,
    queryFn: () => fetchStats(baseUrl),
    staleTime: 15_000,
    refetchInterval: 30_000,
    retry: false,
  });
}
