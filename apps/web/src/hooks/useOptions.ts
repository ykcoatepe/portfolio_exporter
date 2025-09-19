import { useMemo } from "react";
import { useQuery, UseQueryResult } from "@tanstack/react-query";

import type {
  OptionComboApi,
  OptionComboLegApi,
  OptionComboLegRow,
  OptionComboRow,
  OptionLegRow,
  OptionsApiResponse,
} from "../lib/types";

const OPTIONS_QUERY_KEY = ["positions", "options"] as const;

const toNumber = (value: unknown, fallback: number | null = null): number | null => {
  const next = Number(value);
  if (Number.isFinite(next)) {
    return next;
  }
  return fallback;
};

const toInteger = (value: unknown, fallback: number): number => {
  const next = Number(value);
  if (Number.isFinite(next)) {
    return Math.trunc(next);
  }
  return fallback;
};

const normalizeMarkTime = (value: unknown): string | null =>
  typeof value === "string" && value.length > 0 ? value : null;

const normalizeSide = (value: unknown): "credit" | "debit" =>
  value === "credit" ? "credit" : "debit";

const computeDte = (expiry: string, asOf?: string | null): number => {
  const baseTs = asOf ? Date.parse(asOf) : Date.now();
  const expiryTs = Date.parse(expiry);
  if (Number.isNaN(baseTs) || Number.isNaN(expiryTs)) {
    return 0;
  }
  const diffMs = expiryTs - baseTs;
  const diffDays = diffMs / (1000 * 60 * 60 * 24);
  return Math.max(0, Math.round(diffDays));
};

const mapLegApiToRow = (
  leg: OptionComboLegApi,
  asOf?: string | null,
): OptionComboLegRow => ({
  id: leg.id,
  strike: toNumber(leg.strike, 0) ?? 0,
  right: leg.right,
  quantity: toInteger(leg.quantity, 0),
  markPrice: toNumber(leg.mark_price),
  markSource: leg.mark_source,
  markTime: normalizeMarkTime(leg.mark_time),
  delta: toNumber(leg.delta),
  gamma: toNumber(leg.gamma),
  theta: toNumber(leg.theta),
  vega: toNumber(leg.vega),
  dayPnlAmount: toNumber(leg.day_pnl_amount),
  dayPnlPercent: toNumber(leg.day_pnl_percent),
  totalPnlAmount: toNumber(leg.total_pnl_amount),
  totalPnlPercent: toNumber(leg.total_pnl_percent),
});

const mapComboApiToRow = (
  combo: OptionComboApi,
  legMap: Map<string, OptionComboLegApi[]>,
  asOf?: string | null,
): OptionComboRow => ({
  id: combo.id,
  strategy: combo.strategy,
  underlying: combo.underlying,
  expiry: combo.expiry,
  dte: toInteger(combo.dte, computeDte(combo.expiry, asOf)),
  side: normalizeSide(combo.side),
  netPremium: toNumber(combo.net_premium, 0) ?? 0,
  markPrice: toNumber(combo.mark_price),
  markSource: combo.mark_source,
  markTime: normalizeMarkTime(combo.mark_time),
  delta: toNumber(combo.greeks?.delta),
  gamma: toNumber(combo.greeks?.gamma),
  theta: toNumber(combo.greeks?.theta),
  vega: toNumber(combo.greeks?.vega),
  dayPnlAmount: toNumber(combo.day_pnl_amount),
  dayPnlPercent: toNumber(combo.day_pnl_percent),
  totalPnlAmount: toNumber(combo.total_pnl_amount),
  totalPnlPercent: toNumber(combo.total_pnl_percent),
  legs: (legMap.get(combo.id) ?? []).map((leg) => mapLegApiToRow(leg, asOf)),
});

const mapLegApiToStandaloneRow = (
  leg: OptionComboLegApi,
  asOf?: string | null,
): OptionLegRow => ({
  id: leg.id,
  comboId: leg.combo_id ?? null,
  underlying: leg.underlying,
  expiry: leg.expiry,
  dte: computeDte(leg.expiry, asOf),
  strike: toNumber(leg.strike, 0) ?? 0,
  right: leg.right,
  quantity: toInteger(leg.quantity, 0),
  markPrice: toNumber(leg.mark_price),
  markSource: leg.mark_source,
  markTime: normalizeMarkTime(leg.mark_time),
  delta: toNumber(leg.delta),
  gamma: toNumber(leg.gamma),
  theta: toNumber(leg.theta),
  vega: toNumber(leg.vega),
  iv: toNumber(leg.iv),
  dayPnlAmount: toNumber(leg.day_pnl_amount),
  dayPnlPercent: toNumber(leg.day_pnl_percent),
  totalPnlAmount: toNumber(leg.total_pnl_amount),
  totalPnlPercent: toNumber(leg.total_pnl_percent),
  isOrphan: leg.combo_id === null,
});

async function fetchOptions(baseUrl = ""): Promise<OptionsApiResponse> {
  const origin =
    baseUrl ||
    (typeof window !== "undefined" ? window.location.origin : "http://localhost");
  const sanitizedBase = origin.replace(/\/+$/, "");
  const endpoint = `${sanitizedBase}/positions/options`;
  const response = await fetch(endpoint, {
    headers: { Accept: "application/json" },
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }
  const payload = (await response.json()) as OptionsApiResponse;
  const combos = Array.isArray(payload.combos) ? payload.combos : [];
  const legs = Array.isArray(payload.legs) ? payload.legs : [];
  return {
    as_of: payload.as_of ?? null,
    combos,
    legs,
  };
}

export interface OptionCombosResult
  extends UseQueryResult<OptionComboRow[], Error> {
  asOf: string | null;
}

export interface OptionLegsResult extends UseQueryResult<OptionLegRow[], Error> {
  asOf: string | null;
  underlyings: string[];
  expiries: string[];
}

export function useOptionCombos(): OptionCombosResult {
  const query = useQuery<OptionsApiResponse, Error>({
    queryKey: OPTIONS_QUERY_KEY,
    queryFn: () => fetchOptions(),
    staleTime: 15_000,
    refetchInterval: 30_000,
  });

  const legMap = useMemo(() => {
    const map = new Map<string, OptionComboLegApi[]>();
    if (!query.data) {
      return map;
    }
    for (const leg of query.data.legs) {
      if (!leg.combo_id) {
        continue;
      }
      const current = map.get(leg.combo_id) ?? [];
      current.push(leg);
      map.set(leg.combo_id, current);
    }
    return map;
  }, [query.data]);

  const combos = useMemo<OptionComboRow[]>(() => {
    if (!query.data) {
      return [];
    }
    return query.data.combos
      .map((combo) => mapComboApiToRow(combo, legMap, query.data?.as_of))
      .sort((a, b) => (b.dayPnlAmount ?? 0) - (a.dayPnlAmount ?? 0));
  }, [query.data, legMap]);

  return {
    ...query,
    data: combos,
    asOf: query.data?.as_of ?? null,
  };
}

export function useOptionLegs(): OptionLegsResult {
  const query = useQuery<OptionsApiResponse, Error>({
    queryKey: OPTIONS_QUERY_KEY,
    queryFn: () => fetchOptions(),
    staleTime: 15_000,
    refetchInterval: 30_000,
  });

  const legs = useMemo<OptionLegRow[]>(() => {
    if (!query.data) {
      return [];
    }
    return query.data.legs
      .map((leg) => mapLegApiToStandaloneRow(leg, query.data?.as_of))
      .sort((a, b) => {
        if (a.isOrphan !== b.isOrphan) {
          return a.isOrphan ? -1 : 1;
        }
        if (a.underlying !== b.underlying) {
          return a.underlying.localeCompare(b.underlying);
        }
        const expiryDiff = Date.parse(a.expiry) - Date.parse(b.expiry);
        if (expiryDiff !== 0 && !Number.isNaN(expiryDiff)) {
          return expiryDiff;
        }
        return a.strike - b.strike;
      });
  }, [query.data]);

  const underlyings = useMemo(() => {
    const set = new Set<string>();
    for (const leg of legs) {
      set.add(leg.underlying);
    }
    return Array.from(set).sort((a, b) => a.localeCompare(b));
  }, [legs]);

  const expiries = useMemo(() => {
    const set = new Set<string>();
    for (const leg of legs) {
      set.add(leg.expiry);
    }
    return Array.from(set).sort((a, b) => Date.parse(a) - Date.parse(b));
  }, [legs]);

  return {
    ...query,
    data: legs,
    underlyings,
    expiries,
    asOf: query.data?.as_of ?? null,
  };
}

export { fetchOptions };
