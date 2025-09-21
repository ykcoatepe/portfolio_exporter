import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import type { UseQueryResult } from "@tanstack/react-query";

import {
  deriveGroupKey,
  formatComboLabel,
  formatExpiryShort,
  formatLegLabel,
  parseOsi,
} from "../lib/labels";
import type {
  OptionComboApi,
  OptionComboGroupApi,
  OptionComboGroupRow,
  OptionComboLegApi,
  OptionComboLegRow,
  OptionComboRow,
  OptionGreekSummary,
  OptionLegRow,
  OptionsApiResponse,
  MarkSource,
} from "../lib/types";

const OPTIONS_QUERY_KEY = ["positions", "options"] as const;
const MARK_SOURCE_PRIORITY: Record<string, number> = { MID: 0, LAST: 1, PREV: 2, MISSING: 3 };
const OSI_SYMBOL_FRAGMENT = /\d{6}[CP]\d{8}/;

const sanitizeLabel = (candidate: string | undefined | null, fallback: string): string => {
  if (typeof candidate !== "string") {
    return fallback;
  }
  const trimmed = candidate.trim();
  if (!trimmed) {
    return fallback;
  }
  return OSI_SYMBOL_FRAGMENT.test(trimmed) ? fallback : trimmed;
};

const normalizeRightCode = (value: string | null | undefined): "C" | "P" => {
  if (typeof value !== "string") {
    return "C";
  }
  return value.toUpperCase().startsWith("P") ? "P" : "C";
};

const toNumber = (value: unknown, fallback: number | null = null): number | null => {
  const next = Number(value);
  return Number.isFinite(next) ? next : fallback;
};

const toInteger = (value: unknown, fallback: number): number => {
  const next = Number(value);
  return Number.isFinite(next) ? Math.trunc(next) : fallback;
};

const normalizeMarkTime = (value: unknown): string | null =>
  typeof value === "string" && value.length > 0 ? value : null;

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

const chooseMarkSource = (current: string | null | undefined, candidate: string | null | undefined) => {
  const currentKey = (current ?? "MISSING").toUpperCase();
  const candidateKey = (candidate ?? "MISSING").toUpperCase();
  const currentRank = MARK_SOURCE_PRIORITY[currentKey] ?? MARK_SOURCE_PRIORITY.MISSING;
  const candidateRank = MARK_SOURCE_PRIORITY[candidateKey] ?? MARK_SOURCE_PRIORITY.MISSING;
  return candidateRank < currentRank ? candidateKey : currentKey;
};

const deriveComboQuantity = (legs: OptionComboLegRow[]): number => {
  const shorts = legs.filter((leg) => leg.quantity < 0);
  if (shorts.length) {
    const total = shorts.reduce((sum, leg) => sum + leg.quantity, 0);
    return total / shorts.length;
  }
  const longs = legs.filter((leg) => leg.quantity > 0);
  if (longs.length) {
    const total = longs.reduce((sum, leg) => sum + leg.quantity, 0);
    return total / longs.length;
  }
  return 0;
};

const toComboLegRow = (leg: OptionComboLegApi, asOf?: string | null): OptionComboLegRow => {
  const strike = toNumber(leg.strike, 0) ?? 0;
  const quantity = toInteger(leg.quantity, 0);
  const markPrice = toNumber(leg.mark_price);
  const delta = toNumber(leg.delta);
  const gamma = toNumber(leg.gamma);
  const theta = toNumber(leg.theta);
  const vega = toNumber(leg.vega);
  const markTime = normalizeMarkTime(leg.mark_time);
  const markSourceRaw = typeof leg.mark_source === "string" ? leg.mark_source.toUpperCase() : leg.mark_source;
  const markSource: MarkSource =
    markSourceRaw === "MID" || markSourceRaw === "LAST" || markSourceRaw === "PREV"
      ? (markSourceRaw as MarkSource)
      : "MISSING";
  const rawRight = typeof leg.right === "string" ? leg.right : String(leg.right ?? "");
  const parsedSymbol = parseOsi(leg.symbol);
  const parsedLabel = parseOsi(typeof leg.label === "string" ? leg.label : undefined);
  const normalizedRight = parsedSymbol?.side ?? normalizeRightCode(rawRight);
  const underlyingRoot = (parsedSymbol?.ul ?? leg.underlying).toUpperCase();
  const expiryIsoCandidate = parsedSymbol?.expiryISO ?? (typeof leg.expiry === "string" ? leg.expiry : "");
  const fallbackExpiry = expiryIsoCandidate || leg.expiry || "";
  const fallbackLabel = formatLegLabel({
    ul: underlyingRoot,
    strike,
    side: normalizedRight,
    expiryISO: fallbackExpiry,
  });
  const displayLabelCandidate =
    typeof leg.display?.leg_label === "string" ? leg.display.leg_label : undefined;
  const parsedLabelText = parsedLabel ? formatLegLabel(parsedLabel) : undefined;
  const rawLabelCandidate = typeof leg.label === "string" ? leg.label : undefined;
  const label = sanitizeLabel(displayLabelCandidate ?? parsedLabelText ?? rawLabelCandidate, fallbackLabel);
  const shortUnderlying = leg.display?.short_ul ?? underlyingRoot;
  const expiryShort =
    leg.display?.expiry_short ?? formatExpiryShort(fallbackExpiry) ?? fallbackExpiry;
  const legId = leg.id ?? leg.leg_id ?? `${leg.combo_id ?? "orphan"}:${fallbackExpiry}:${normalizedRight}:${strike}`;
  const expiryValue = fallbackExpiry;

  return {
    id: legId,
    symbol: leg.symbol ?? legId,
    label: typeof label === "string" ? label : fallbackLabel,
    underlying: leg.underlying,
    shortUnderlying,
    expiry: expiryValue,
    expiryShort,
    strike,
    right: normalizedRight,
    quantity,
    markPrice,
    markSource,
    markTime,
    delta,
    gamma,
    theta,
    vega,
    dayPnlAmount: toNumber(leg.day_pnl_amount),
    dayPnlPercent: toNumber(leg.day_pnl_percent),
    totalPnlAmount: toNumber(leg.total_pnl_amount),
    totalPnlPercent: toNumber(leg.total_pnl_percent),
    comboGroupId: leg.combo_group_id ?? null,
  };
};

const mapComboApiToRow = (
  combo: OptionComboApi,
  legMap: Map<string, OptionComboLegApi[]>,
  asOf?: string | null,
): OptionComboRow => {
  const comboId = combo.id ?? combo.combo_id ?? `${combo.strategy}-${combo.underlying}-${combo.expiry}`;
  const legCandidates = [combo.id, combo.combo_id].filter((value): value is string => typeof value === "string" && value.length > 0);
  const rawLegs = legCandidates.reduce<OptionComboLegApi[] | undefined>((acc, key) => {
    if (acc && acc.length > 0) {
      return acc;
    }
    return legMap.get(key);
  }, undefined) ?? [];
  const legs = rawLegs.map((leg) => toComboLegRow(leg, asOf));
  const netPremium = toNumber(combo.net_premium ?? combo.net_price, 0) ?? 0;
  const side = combo.side ?? (netPremium >= 0 ? "credit" : "debit");
  const dte = toInteger(combo.dte, computeDte(combo.expiry, asOf));
  const fallbackLabel = formatComboLabel(combo.strategy, rawLegs, dte, netPremium, combo.underlying);
  const displayLabelCandidate =
    typeof combo.display?.combo_label === "string" ? combo.display.combo_label : undefined;
  const label = sanitizeLabel(displayLabelCandidate ?? combo.label, fallbackLabel);
  const display =
    combo.display != null
      ? { ...combo.display, combo_label: sanitizeLabel(combo.display.combo_label, fallbackLabel) }
      : null;
  const comboQty = Number.isFinite(combo.combo_qty) ? Number(combo.combo_qty) : deriveComboQuantity(legs);
  const greeks = combo.sum_greeks ?? combo.greeks ?? {};
  const markSourceRaw = typeof combo.mark_source === "string" ? combo.mark_source.toUpperCase() : combo.mark_source;
  const markSource: MarkSource =
    markSourceRaw === "MID" || markSourceRaw === "LAST" || markSourceRaw === "PREV"
      ? (markSourceRaw as MarkSource)
      : "MISSING";

  return {
    id: comboId,
    strategy: combo.strategy,
    underlying: combo.underlying,
    expiry: combo.expiry,
    dte,
    side: side === "credit" ? "credit" : "debit",
    netPremium,
    markPrice: toNumber(combo.mark_price),
    markSource,
    markTime: normalizeMarkTime(combo.mark_time),
    delta: toNumber((greeks as OptionGreekSummary).delta),
    gamma: toNumber((greeks as OptionGreekSummary).gamma),
    theta: toNumber((greeks as OptionGreekSummary).theta),
    vega: toNumber((greeks as OptionGreekSummary).vega),
    dayPnlAmount: toNumber(combo.day_pnl_amount),
    dayPnlPercent: toNumber(combo.day_pnl_percent),
    totalPnlAmount: toNumber(combo.total_pnl_amount),
    totalPnlPercent: toNumber(combo.total_pnl_percent),
    legs,
    label,
    display,
    comboGroupId: combo.combo_group_id ?? null,
    comboQty,
    groupNetPrice: netPremium,
  };
};

const mapLegToStandaloneRow = (leg: OptionComboLegApi, asOf?: string | null): OptionLegRow => {
  const legRow = toComboLegRow(leg, asOf);
  return {
    id: legRow.id,
    comboId: leg.combo_id ?? null,
    comboGroupId: leg.combo_group_id ?? null,
    symbol: legRow.symbol,
    label: legRow.label,
    shortUnderlying: legRow.shortUnderlying,
    expiryShort: legRow.expiryShort,
    underlying: legRow.underlying,
    expiry: legRow.expiry,
    dte: computeDte(legRow.expiry, asOf),
    strike: legRow.strike,
    right: legRow.right,
    quantity: legRow.quantity,
    markPrice: legRow.markPrice,
    markSource: legRow.markSource,
    markTime: legRow.markTime,
    delta: legRow.delta,
    gamma: legRow.gamma,
    theta: legRow.theta,
    vega: legRow.vega,
    iv: toNumber(leg.iv),
    dayPnlAmount: legRow.dayPnlAmount,
    dayPnlPercent: legRow.dayPnlPercent,
    totalPnlAmount: legRow.totalPnlAmount,
    totalPnlPercent: legRow.totalPnlPercent,
    isOrphan: leg.combo_id === null,
  };
};

const buildGroupRowFromApi = (
  group: OptionComboGroupApi,
): OptionComboGroupRow => {
  const legs: OptionComboLegRow[] = group.legs.map((leg) => {
    const parsedSymbol = parseOsi(leg.symbol);
    const parsedLabel = parseOsi(typeof leg.label === "string" ? leg.label : undefined);
    const rawRight = typeof leg.right === "string" ? leg.right : String(leg.right ?? "");
    const normalizedRight = parsedSymbol?.side ?? normalizeRightCode(rawRight);
    const underlyingRoot = (parsedSymbol?.ul ?? leg.underlying).toUpperCase();
    const expiryIso = parsedSymbol?.expiryISO ?? (typeof leg.expiry === "string" ? leg.expiry : "");
    const fallbackExpiry = expiryIso || leg.expiry || "";
    const fallbackLabel = formatLegLabel({
      ul: underlyingRoot,
      strike: toNumber(leg.strike, 0) ?? 0,
      side: normalizedRight,
      expiryISO: fallbackExpiry,
    });
    const labelCandidate =
      typeof leg.display?.leg_label === "string"
        ? leg.display.leg_label
        : parsedLabel
          ? formatLegLabel(parsedLabel)
          : typeof leg.label === "string"
            ? leg.label
            : undefined;
    const label = sanitizeLabel(labelCandidate, fallbackLabel);
    const shortUnderlying = leg.display?.short_ul ?? underlyingRoot;
    const expiryShort = leg.display?.expiry_short ?? formatExpiryShort(fallbackExpiry) ?? fallbackExpiry;
    const markSourceRaw = typeof leg.mark_source === "string" ? leg.mark_source.toUpperCase() : leg.mark_source;
    const markSource: MarkSource =
      markSourceRaw === "MID" || markSourceRaw === "LAST" || markSourceRaw === "PREV"
        ? (markSourceRaw as MarkSource)
        : "MISSING";
    const symbol = leg.symbol ?? `${group.combo_group_id}:${fallbackExpiry}:${normalizedRight}:${leg.strike}`;
    return {
      id: `${group.combo_group_id}:${symbol}`,
      symbol,
      label,
      shortUnderlying,
      expiryShort,
      strike: toNumber(leg.strike, 0) ?? 0,
      right: normalizedRight,
      quantity: toNumber(leg.quantity, 0) ?? 0,
      markPrice: toNumber(leg.mark),
      markSource,
      markTime: null,
      delta: toNumber(leg.sum_greeks?.delta),
      gamma: toNumber(leg.sum_greeks?.gamma),
      theta: toNumber(leg.sum_greeks?.theta),
      vega: toNumber(leg.sum_greeks?.vega),
      dayPnlAmount: null,
      dayPnlPercent: null,
      totalPnlAmount: null,
      totalPnlPercent: null,
      comboGroupId: group.combo_group_id,
      underlying: leg.underlying,
      expiry: fallbackExpiry,
    };
  });

  const fallbackLabel = formatComboLabel(
    group.strategy,
    group.legs as unknown as OptionComboLegApi[],
    group.dte,
    group.group_net_price,
    group.underlying,
  );
  const label = sanitizeLabel(group.label, fallbackLabel);
  const display =
    group.display != null
      ? { ...group.display, combo_label: sanitizeLabel(group.display.combo_label, fallbackLabel) }
      : null;

  return {
    id: group.combo_group_id,
    strategy: group.strategy,
    underlying: group.underlying,
    dte: toInteger(group.dte, 0),
    groupQty: toNumber(group.group_qty, 0) ?? 0,
    netPrice: toNumber(group.group_net_price, 0) ?? 0,
    delta: toNumber(group.sum_greeks?.delta),
    gamma: toNumber(group.sum_greeks?.gamma),
    theta: toNumber(group.sum_greeks?.theta),
    vega: toNumber(group.sum_greeks?.vega),
    markSource: group.mark_source ?? "MID",
    staleSeconds: group.stale_seconds ?? null,
    label,
    display,
    legs,
  };
};

const buildGroupsFallback = (
  combos: OptionComboRow[],
): { groups: OptionComboGroupRow[]; groupCombos: Map<string, OptionComboRow[]> } => {
  const groupsMap = new Map<string, OptionComboRow[]>();
  const groupRows = new Map<string, OptionComboGroupRow>();

  for (const combo of combos) {
    const key = combo.comboGroupId ?? `${combo.strategy}|${combo.underlying}|${deriveGroupKey(combo.legs)}|${combo.dte}`;
    const groupList = groupsMap.get(key) ?? [];
    groupList.push(combo);
    groupsMap.set(key, groupList);
  }

  groupsMap.forEach((entries, key) => {
    const first = entries[0];
    const netPriceWeights = entries.reduce((acc, item) => acc + Math.abs(item.comboQty || 1), 0);
    const weightedNet = entries.reduce((acc, item) => acc + (item.groupNetPrice ?? item.netPremium) * Math.abs(item.comboQty || 1), 0);
    const netPrice = netPriceWeights ? weightedNet / netPriceWeights : 0;
    const groupQty = entries.reduce((acc, item) => acc + (item.comboQty || 0), 0);
    const legsAggregation = entries[0].legs.map((leg, idx) => {
      const totalQuantity = entries.reduce((sum, combo) => sum + (combo.legs[idx]?.quantity ?? 0), 0);
      const label = leg.label;
      return {
        ...leg,
        id: `${key}:${leg.symbol}:${idx}`,
        quantity: totalQuantity,
        markPrice: leg.markPrice,
        comboGroupId: key,
      };
    });
    const legsForLabel = entries.flatMap((combo) =>
      combo.legs.map<Partial<OptionComboLegApi>>((legRow) => ({
        id: legRow.id,
        combo_id: combo.id,
        combo_group_id: key,
        underlying: legRow.underlying,
        expiry: legRow.expiry,
        strike: legRow.strike,
        right: legRow.right,
        quantity: legRow.quantity,
        mark_price: null,
        mark_source: "MID",
        mark_time: null,
        delta: null,
        gamma: null,
        theta: null,
        vega: null,
        day_pnl_amount: null,
        day_pnl_percent: null,
        total_pnl_amount: null,
        total_pnl_percent: null,
      }))
    );
    const markSourceRaw = entries.reduce<string | null>((current, combo) => chooseMarkSource(current, combo.markSource), null);
    const markSource = (markSourceRaw === "LAST" || markSourceRaw === "PREV" ? markSourceRaw : "MID") as MarkSource;
    const staleSeconds = entries.reduce<number | null>((max, combo) => {
      if (!combo.markTime) {
        return max;
      }
      const seconds = Math.floor((Date.now() - Date.parse(combo.markTime)) / 1000);
      if (!Number.isFinite(seconds)) {
        return max;
      }
      return max === null ? seconds : Math.max(max, seconds);
    }, null);
    groupRows.set(key, {
      id: key,
      strategy: first.strategy,
      underlying: first.underlying,
      dte: first.dte,
      groupQty,
      netPrice,
      delta: entries.reduce((acc, combo) => acc + (combo.delta ?? 0), 0),
      gamma: entries.reduce((acc, combo) => acc + (combo.gamma ?? 0), 0),
      theta: entries.reduce((acc, combo) => acc + (combo.theta ?? 0), 0),
      vega: entries.reduce((acc, combo) => acc + (combo.vega ?? 0), 0),
      markSource,
      staleSeconds,
      label: formatComboLabel(first.strategy, legsForLabel as OptionComboLegApi[], first.dte, netPrice, first.underlying),
      display: first.display,
      legs: legsAggregation,
    });
  });

  return {
    groups: Array.from(groupRows.values()),
    groupCombos: groupsMap,
  };
};

async function fetchOptions(baseUrl = ""): Promise<OptionsApiResponse> {
  const origin =
    baseUrl ||
    (typeof window !== "undefined" ? window.location.origin : "http://localhost");
  const sanitizedBase = origin.replace(/\/+$/, "");
  const response = await fetch(`${sanitizedBase}/positions/options`, {
    headers: { Accept: "application/json" },
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }
  const payload = (await response.json()) as OptionsApiResponse;
  return {
    as_of: payload.as_of ?? null,
    combos: Array.isArray(payload.combos) ? payload.combos : [],
    legs: Array.isArray(payload.legs) ? payload.legs : [],
    combo_groups: Array.isArray(payload.combo_groups) ? payload.combo_groups : [],
  };
}

export type OptionCombosResult = UseQueryResult<OptionComboRow[], Error> & {
  asOf: string | null;
  groups: OptionComboGroupRow[];
  groupCombos: Map<string, OptionComboRow[]>;
};

export type OptionLegsResult = UseQueryResult<OptionLegRow[], Error> & {
  asOf: string | null;
  underlyings: string[];
  expiries: string[];
};

export function useOptionCombos(): OptionCombosResult {
  const query = useQuery<OptionsApiResponse, Error>({
    queryKey: OPTIONS_QUERY_KEY,
    queryFn: () => fetchOptions(),
    staleTime: 15_000,
    refetchInterval: 30_000,
  });

  const { data: rawData } = query;

  const legMap = useMemo(() => {
    const map = new Map<string, OptionComboLegApi[]>();
    if (!rawData) {
      return map;
    }
    for (const leg of rawData.legs) {
      if (!leg.combo_id) {
        continue;
      }
      const current = map.get(leg.combo_id) ?? [];
      current.push(leg);
      map.set(leg.combo_id, current);
    }
    return map;
  }, [rawData]);

  const combos = useMemo<OptionComboRow[]>(() => {
    if (!rawData) {
      return [];
    }
    return rawData.combos
      .map((combo) => mapComboApiToRow(combo, legMap, rawData.as_of))
      .sort((a, b) => (b.dayPnlAmount ?? 0) - (a.dayPnlAmount ?? 0));
  }, [rawData, legMap]);

  const grouping = useMemo(() => {
    if (!rawData) {
      return { groups: [], groupCombos: new Map<string, OptionComboRow[]>() };
    }
    if (rawData.combo_groups && rawData.combo_groups.length > 0) {
      const groupCombos = new Map<string, OptionComboRow[]>();
      for (const combo of combos) {
        const key = combo.comboGroupId ?? combo.id;
        const list = groupCombos.get(key) ?? [];
        list.push(combo);
        groupCombos.set(key, list);
      }
      const groups = rawData.combo_groups.map((group) => buildGroupRowFromApi(group)).sort((a, b) => b.netPrice - a.netPrice);
      return { groups, groupCombos };
    }
    return buildGroupsFallback(combos);
  }, [rawData, combos]);

  const typedQuery = query as unknown as UseQueryResult<OptionComboRow[], Error>;

  return {
    ...typedQuery,
    data: combos,
    asOf: rawData?.as_of ?? null,
    groups: grouping.groups,
    groupCombos: grouping.groupCombos,
  } as OptionCombosResult;
}

export function useOptionLegs(): OptionLegsResult {
  const query = useQuery<OptionsApiResponse, Error>({
    queryKey: OPTIONS_QUERY_KEY,
    queryFn: () => fetchOptions(),
    staleTime: 15_000,
    refetchInterval: 30_000,
  });

  const { data: rawData } = query;

  const legs = useMemo<OptionLegRow[]>(() => {
    if (!rawData) {
      return [];
    }
    return rawData.legs
      .map((leg) => mapLegToStandaloneRow(leg, rawData.as_of))
      .sort((a, b) => {
        if (a.isOrphan !== b.isOrphan) {
          return a.isOrphan ? -1 : 1;
        }
        if (a.shortUnderlying !== b.shortUnderlying) {
          return a.shortUnderlying.localeCompare(b.shortUnderlying);
        }
        const expiryDiff = Date.parse(a.expiry) - Date.parse(b.expiry);
        if (expiryDiff !== 0 && !Number.isNaN(expiryDiff)) {
          return expiryDiff;
        }
        return a.strike - b.strike;
      });
  }, [rawData]);

  const underlyings = useMemo(() => {
    const set = new Set<string>();
    for (const leg of legs) {
      set.add(leg.shortUnderlying);
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

  const typedQuery = query as unknown as UseQueryResult<OptionLegRow[], Error>;

  return {
    ...typedQuery,
    data: legs,
    underlyings,
    expiries,
    asOf: rawData?.as_of ?? null,
  } as OptionLegsResult;
}

export { fetchOptions };
