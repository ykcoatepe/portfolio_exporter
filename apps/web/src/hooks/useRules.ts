import { useMemo } from "react";
import { useQuery, useQueryClient, type QueryClient, type UseQueryResult } from "@tanstack/react-query";

import type { components } from "../lib/api";

type RawRulesSummary = components["schemas"]["RulesSummaryResponseModel"];
type RawRuleBreach = components["schemas"]["RulesSummaryTopModel"];
type RawBreaches = components["schemas"]["BreachCountsModel"];
export type RuleSeverity = components["schemas"]["RuleSeverity"];

export interface RuleBreachSummary {
  id: string;
  rule: string;
  severity: RuleSeverity;
  subject: string;
  symbol?: string | null;
  occurred_at: string;
  description?: string | null;
}

export interface RuleCounters {
  total: number;
  critical: number;
  warning: number;
  info: number;
}

export interface RulesSummaryResponse {
  as_of: string;
  breaches: RuleCounters;
  top: RuleBreachSummary[];
  focus_symbols?: string[];
  rules_total?: number;
  evaluation_ms?: number;
  fundamentals?: FundamentalsMap | null;
}

const RULES_SUMMARY_QUERY_KEY = ["rules", "summary"] as const;
const FUNDAMENTALS_QUERY_KEY = ["fundamentals"] as const;

interface FundamentalsEntry {
  company?: string | null;
  market_cap?: number | null;
  pe?: number | null;
  next_earnings?: string | null;
  dividend_yield?: number | null;
}

export type FundamentalsMap = Record<string, FundamentalsEntry>;

export interface SymbolFundamentals extends FundamentalsEntry {
  symbol: string;
}

export interface UseFundamentalsResult
  extends UseQueryResult<SymbolFundamentals[], Error> {
  allFundamentals: FundamentalsMap | null;
}

const isTestEnvironment =
  typeof import.meta !== "undefined" && import.meta.env?.MODE === "test";

const isDevelopmentEnvironment =
  typeof import.meta !== "undefined" && import.meta.env?.MODE === "development";

const allowAssetFallback = isTestEnvironment || isDevelopmentEnvironment;

const sanitizeSeverity = (value: unknown): RuleSeverity => {
  if (value === "critical" || value === "warning" || value === "info") {
    return value;
  }
  return "info";
};

const coerceString = (value: unknown, fallback = ""): string =>
  typeof value === "string" ? value : fallback;

const coerceNullableString = (value: unknown): string | null =>
  typeof value === "string" && value.length > 0 ? value : null;

const coerceNumber = (value: unknown, fallback = 0): number => {
  const next = Number(value);
  if (Number.isFinite(next)) {
    return next;
  }
  return fallback;
};

const coerceNullableNumber = (value: unknown): number | null => {
  const next = Number(value);
  if (Number.isFinite(next)) {
    return next;
  }
  return null;
};

const coerceNonNegativeInteger = (value: unknown, fallback = 0): number => {
  const next = Math.max(0, Math.trunc(Number(value)));
  if (Number.isFinite(next)) {
    return next;
  }
  return fallback;
};

const sanitizeBreach = (value: unknown): RuleBreachSummary | null => {
  if (typeof value !== "object" || value === null) {
    return null;
  }
  const record = value as Partial<RawRuleBreach> & Record<string, unknown>;
  const id = coerceString(record.id, "");
  const rule = coerceString(record.rule, "");
  const subject = coerceString(record.subject, "");
  const occurredAt = coerceString(record.occurred_at, "");
  if (!id || !rule || !subject || !occurredAt) {
    return null;
  }
  return {
    id,
    rule,
    subject,
    occurred_at: occurredAt,
    severity: sanitizeSeverity(record.severity),
    symbol: coerceNullableString(record.symbol),
    description: coerceNullableString(record.description),
  };
};

const sanitizeBreaches = (value: unknown): RuleCounters => {
  if (typeof value !== "object" || value === null) {
    return { total: 0, critical: 0, warning: 0, info: 0 };
  }
  const record = value as Partial<RawBreaches> & Record<string, unknown>;
  const critical = coerceNonNegativeInteger(record.critical, 0);
  const warning = coerceNonNegativeInteger(record.warning, 0);
  const info = coerceNonNegativeInteger(record.info, 0);
  const total = critical + warning + info;
  return { total, critical, warning, info };
};

const sanitizeFundamentalEntry = (value: unknown): FundamentalsEntry | null => {
  if (typeof value !== "object" || value === null) {
    return null;
  }
  const record = value as Partial<FundamentalsEntry> & Record<string, unknown>;
  return {
    company: coerceNullableString(record.company),
    market_cap: coerceNullableNumber(record.market_cap),
    pe: coerceNullableNumber(record.pe),
    next_earnings: coerceNullableString(record.next_earnings),
    dividend_yield: coerceNullableNumber(record.dividend_yield),
  } satisfies FundamentalsEntry;
};

const sanitizeFundamentalsMap = (value: unknown): FundamentalsMap | null => {
  if (typeof value !== "object" || value === null) {
    return null;
  }
  const entries = Object.entries(value as Record<string, unknown>);
  const result: FundamentalsMap = {};
  for (const [rawSymbol, entryValue] of entries) {
    if (typeof rawSymbol !== "string" || rawSymbol.trim() === "") {
      continue;
    }
    const sanitized = sanitizeFundamentalEntry(entryValue);
    if (!sanitized) {
      continue;
    }
    const symbol = rawSymbol.trim().toUpperCase();
    result[symbol] = sanitized;
  }
  return Object.keys(result).length > 0 ? result : null;
};

const resolveOrigin = (baseUrl = ""): string => {
  if (baseUrl) {
    return baseUrl.replace(/\/+$/, "");
  }
  if (typeof window !== "undefined" && window.location?.origin) {
    return window.location.origin;
  }
  return "http://localhost";
};

export async function fetchRulesSummary(baseUrl = ""): Promise<RulesSummaryResponse> {
  const origin = resolveOrigin(baseUrl);
  const endpoint = `${origin}/rules/summary`;
  const response = await fetch(endpoint, {
    headers: { Accept: "application/json" },
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }
  const record = (await response.json()) as Partial<RawRulesSummary> & Record<string, unknown>;
  const topCandidates = Array.isArray(record.top) ? record.top : [];
  const top = topCandidates
    .map(sanitizeBreach)
    .filter((item): item is RuleBreachSummary => item !== null);
  const breaches = sanitizeBreaches(record.breaches);
  const asOf = coerceString(record.as_of, new Date().toISOString());
  const focusSymbols = Array.isArray(record.focus_symbols)
    ? record.focus_symbols.filter((symbol): symbol is string => typeof symbol === "string")
    : undefined;
  const fundamentalsPayload = sanitizeFundamentalsMap(
    record.fundamentals ?? record.fundamentals_cache ?? record.fundamentalsCache,
  );
  if (fundamentalsPayload) {
    fundamentalsCache = fundamentalsPayload;
  }
  return {
    as_of: asOf,
    breaches,
    top,
    focus_symbols: focusSymbols,
    rules_total: typeof record.rules_total === "number" ? record.rules_total : undefined,
    evaluation_ms:
      typeof record.evaluation_ms === "number" ? record.evaluation_ms : undefined,
    fundamentals: fundamentalsPayload ?? fundamentalsCache,
  };
}

let fundamentalsCache: FundamentalsMap | null = null;

const resolveAssetUrl = (assetPath: string): string => {
  const base =
    (typeof import.meta !== "undefined" && typeof import.meta.env?.BASE_URL === "string"
      ? import.meta.env.BASE_URL
      : "/") || "/";
  const sanitizedBase = base.endsWith("/") ? base.slice(0, -1) : base;
  if (!sanitizedBase) {
    return `/${assetPath}`;
  }
  return `${sanitizedBase}/${assetPath}`;
};

async function loadFundamentalsFromAsset(): Promise<FundamentalsMap> {
  const url = resolveAssetUrl("fundamentals.json");
  const response = await fetch(url, {
    headers: { Accept: "application/json" },
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(`Failed to load fundamentals asset (${response.status})`);
  }
  const payload = sanitizeFundamentalsMap(await response.json());
  if (!payload) {
    throw new Error("Fundamentals asset did not contain usable data");
  }
  return payload;
}

async function fetchFundamentalsMap(queryClient: QueryClient): Promise<FundamentalsMap> {
  if (fundamentalsCache) {
    return fundamentalsCache;
  }

  try {
    const summary = await queryClient.ensureQueryData<RulesSummaryResponse>(RULES_SUMMARY_QUERY_KEY);
    if (summary?.fundamentals && Object.keys(summary.fundamentals).length > 0) {
      fundamentalsCache = summary.fundamentals;
      return fundamentalsCache;
    }
  } catch (error) {
    // Swallow and attempt fallback below; summary query handles surfacing its own errors.
  }

  if (allowAssetFallback) {
    const fallback = await loadFundamentalsFromAsset();
    fundamentalsCache = fallback;
    return fallback;
  }

  throw new Error("Fundamentals cache unavailable from API response");
}

export function useRulesSummary(): UseQueryResult<RulesSummaryResponse, Error> {
  return useQuery<RulesSummaryResponse, Error>({
    queryKey: RULES_SUMMARY_QUERY_KEY,
    queryFn: () => fetchRulesSummary(),
    retry: isTestEnvironment ? false : 1,
    staleTime: 30_000,
    refetchInterval: 60_000,
  });
}

const normalizeSymbols = (symbols: readonly string[]): string[] => {
  const seen = new Set<string>();
  for (const raw of symbols) {
    if (typeof raw !== "string") {
      continue;
    }
    const trimmed = raw.trim();
    if (!trimmed) {
      continue;
    }
    const upper = trimmed.toUpperCase();
    if (!seen.has(upper)) {
      seen.add(upper);
    }
  }
  return Array.from(seen);
};

export function useFundamentals(symbols: string[]): UseFundamentalsResult {
  const normalizedSymbols = useMemo(() => normalizeSymbols(symbols), [symbols]);
  const queryClient = useQueryClient();

  const query = useQuery<FundamentalsMap, Error>({
    queryKey: [...FUNDAMENTALS_QUERY_KEY, normalizedSymbols.join(",")],
    queryFn: () => fetchFundamentalsMap(queryClient),
    enabled: normalizedSymbols.length > 0,
    staleTime: Infinity,
    retry: isTestEnvironment ? false : 1,
  });

  const derived = useMemo<SymbolFundamentals[]>(() => {
    if (!query.data || normalizedSymbols.length === 0) {
      return [];
    }
    return normalizedSymbols
      .map((symbol) => {
        const entry = query.data?.[symbol];
        if (!entry) {
          return null;
        }
        return {
          symbol,
          company: entry.company ?? null,
          market_cap: entry.market_cap ?? null,
          pe: entry.pe ?? null,
          next_earnings: entry.next_earnings ?? null,
          dividend_yield: entry.dividend_yield ?? null,
        } satisfies SymbolFundamentals;
      })
      .filter((item): item is SymbolFundamentals => item !== null);
  }, [query.data, normalizedSymbols]);

  return {
    ...query,
    data: derived,
    allFundamentals: query.data ?? null,
  };
}

export { RULES_SUMMARY_QUERY_KEY };
