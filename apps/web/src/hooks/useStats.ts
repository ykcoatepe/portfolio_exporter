import { useEffect } from "react";
import {
  useQuery,
  useQueryClient,
  type UseQueryResult,
  type DefaultError,
} from "@tanstack/react-query";

import type {
  PortfolioStats,
  PortfolioStatsApiResponse,
  PortfolioTotals,
  PortfolioTotalsApiResponse,
} from "../lib/types";
import { normalizeSession } from "../lib/session";
import { resolveApiBaseUrl } from "../lib/http";

export const PSD_STATS_QUERY_KEY = ["psd", "stats", "current"] as const;
const STATS_SSE_EVENT = "psd.stats.update";
const SSE_PATH = "/sse";

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

const parseTotalsPayload = (
  payload: PortfolioTotalsApiResponse | null | undefined,
): PortfolioTotals | null => {
  if (!payload) {
    return null;
  }
  const source = typeof payload === "object" ? payload : null;
  if (!source) {
    return null;
  }
  const pnlDay = toNullableNumber(source.pnl_day ?? source.pnlDay);
  const unrealized = toNullableNumber(source.unrealized);
  const sumDelta = toNullableNumber(source.sum_delta ?? source.sumDelta);
  const sumTheta = toNullableNumber(source.sum_theta ?? source.sumTheta);
  const stalenessSecs = toNullableNumber(
    source.staleness_secs ?? source.stalenessSecs,
  );
  return {
    pnlDay,
    unrealized,
    sumDelta,
    sumTheta,
    stalenessSecs,
  };
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
      totals: null,
    };
  }

  const session = normalizeSession(payload.session ?? null);
  const sessionInfo = normalizeSession(payload.session_info ?? null);
  const totals = parseTotalsPayload(payload.totals ?? null);

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
    totals,
  };
};

export const fetchStats = async (baseUrl = ""): Promise<PortfolioStats> => {
  const origin = resolveApiBaseUrl(baseUrl);
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

export function useStats(
  baseUrl?: string,
): UseQueryResult<PortfolioStats, DefaultError> {
  const queryClient = useQueryClient();
  const resolvedBaseUrl = resolveApiBaseUrl(baseUrl ?? "");

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
        const raw = (data && typeof data === "object" ? data : null) as
          | Record<string, unknown>
          | null;
        queryClient.setQueryData<PortfolioStats | null>(
          PSD_STATS_QUERY_KEY,
          (current) => {
          if (!current) {
            return parsed;
          }

          const mergedCounts = current.counts
            ? { ...current.counts }
            : { ...parsed.counts };

          if (raw) {
            if ("equity_count" in raw) {
              mergedCounts.equities = parsed.counts.equities;
            }
            if ("quote_count" in raw) {
              mergedCounts.quotes = parsed.counts.quotes;
            }
            if ("option_legs_count" in raw) {
              mergedCounts.optionLegs = parsed.counts.optionLegs;
            }
            if ("combos_matched" in raw) {
              mergedCounts.combos = parsed.counts.combos;
            }
            if ("stale_quotes_count" in raw) {
              mergedCounts.staleQuotes = parsed.counts.staleQuotes;
            }
            if ("rules_count" in raw) {
              mergedCounts.rules = parsed.counts.rules;
            }
            if ("breaches_count" in raw) {
              mergedCounts.breaches = parsed.counts.breaches;
            }
          }

          const hasTotals = Boolean(raw && typeof raw === "object" && "totals" in raw);
          const nextTotals = hasTotals
            ? parsed.totals
            : current.totals ?? parsed.totals;

            return {
              ...current,
              ...parsed,
              counts: mergedCounts,
              totals: nextTotals,
            };
          },
        );
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
