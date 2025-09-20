import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import type { PortfolioStats, PortfolioStatsApiResponse } from "../lib/types";

const toNumber = (value: unknown): number | null => {
  if (value === null || value === undefined) {
    return null;
  }
  const num = Number(value);
  return Number.isFinite(num) ? num : null;
};

const toCount = (value: unknown): number => {
  const num = Number(value);
  return Number.isFinite(num) && num >= 0 ? num : 0;
};

const toOptionalCount = (value: unknown): number | undefined => {
  const num = Number(value);
  return Number.isFinite(num) && num >= 0 ? num : undefined;
};

const normalizeTimestamp = (value: unknown): string | null =>
  typeof value === "string" && value.length > 0 ? value : null;

const normalizeBoolean = (value: unknown, fallback = false): boolean =>
  typeof value === "boolean" ? value : fallback;

export async function fetchStats(baseUrl = ""): Promise<PortfolioStats> {
  const origin =
    baseUrl ||
    (typeof window !== "undefined" ? window.location.origin : "http://localhost");
  const sanitizedBase = origin.replace(/\/+$/, "");
  const endpoint = `${sanitizedBase}/stats`;
  const response = await fetch(endpoint, {
    headers: { Accept: "application/json" },
    credentials: "include",
  });

  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }

  const payload = (await response.json()) as PortfolioStatsApiResponse | null;

  return {
    netLiq: toNumber(payload?.net_liq ?? payload?.netLiq),
    var95: toNumber(payload?.var95_1d_pct ?? payload?.var95 ?? payload?.var_95),
    marginPct: toNumber(payload?.margin_used_pct ?? payload?.margin_pct ?? payload?.marginPct),
    updatedAt: normalizeTimestamp(payload?.updated_at ?? payload?.updatedAt),
    counts: {
      equities: toCount(payload?.equity_count),
      quotes: toCount(payload?.quote_count),
      optionLegs: toCount(payload?.option_legs_count),
      combos: toCount(payload?.combos_matched),
      staleQuotes: toCount(payload?.stale_quotes_count),
      rules: toOptionalCount(payload?.rules_count),
      breaches: toOptionalCount(payload?.breaches_count),
    },
    rulesEvalMs:
      toNumber(payload?.rules_eval_ms ?? payload?.combos_detection_ms) ?? null,
    tradesPriorPositions: normalizeBoolean(payload?.trades_prior_positions),
  };
}

export function useStats(): UseQueryResult<PortfolioStats, Error> {
  return useQuery<PortfolioStats, Error>({
    queryKey: ["portfolio", "stats"],
    queryFn: () => fetchStats(),
    staleTime: 15_000,
    refetchInterval: 30_000,
    retry: false,
  });
}
