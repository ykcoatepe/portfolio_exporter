import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { PSD_SNAPSHOT_QUERY_KEY, fetchPsdSnapshot } from "./usePsdSnapshot";
import type { MarkSource, PSDSnapshot, PSDLeg, StockRow } from "../lib/types";

const MARK_SOURCE_FALLBACK: MarkSource = "MISSING";

const toNumber = (value: unknown, fallback = 0): number => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

const normalizeMarkSource = (value: unknown): MarkSource => {
  if (typeof value !== "string") {
    return MARK_SOURCE_FALLBACK;
  }
  const upper = value.trim().toUpperCase();
  if (upper === "MID" || upper === "LAST" || upper === "PREV" || upper === "MISSING") {
    return upper as MarkSource;
  }
  return MARK_SOURCE_FALLBACK;
};

const fallbackMarkTime = (entry: PSDLeg, snapshot: PSDSnapshot | undefined): string | null => {
  if (typeof entry.updated_at === "string" && entry.updated_at) {
    return entry.updated_at;
  }
  if (typeof entry.mark_time === "string" && entry.mark_time) {
    return entry.mark_time;
  }
  if (typeof snapshot?.ts === "number" && Number.isFinite(snapshot.ts)) {
    return new Date(snapshot.ts).toISOString();
  }
  return null;
};

const computePercent = (amount: number, basis: number): number => {
  if (!Number.isFinite(amount) || !Number.isFinite(basis) || basis === 0) {
    return 0;
  }
  return amount / basis;
};

const mapSingleStock = (entry: PSDLeg, snapshot: PSDSnapshot | undefined): StockRow => {
  const quantity = toNumber(entry.qty, 0);
  const avgCost = toNumber(entry.avg_cost, 0);
  const markPrice = toNumber(entry.mark, 0);
  const dayPnlAmount = toNumber(entry.pnl_intraday, 0);
  const totalPnlAmount = toNumber(entry.pnl_unrealized, 0);
  const previousClose = toNumber(entry.previous_close, Number.NaN);

  const dayBasis = Number.isFinite(previousClose)
    ? Math.abs(quantity) * previousClose
    : Number.NaN;
  const totalBasis = Math.abs(quantity) * avgCost;

  const markSource = normalizeMarkSource(entry.mark_source ?? entry.price_source);
  const markTime = fallbackMarkTime(entry, snapshot);

  return {
    symbol: entry.symbol,
    quantity,
    averagePrice: avgCost,
    markPrice,
    markSource,
    markTime,
    dayPnlAmount,
    dayPnlPercent: computePercent(dayPnlAmount, dayBasis),
    totalPnlAmount,
    totalPnlPercent: computePercent(totalPnlAmount, totalBasis),
    currency: "USD",
  };
};

export function useStocks(): UseQueryResult<StockRow[], Error> {
  return useQuery<PSDSnapshot, Error, StockRow[]>({
    queryKey: PSD_SNAPSHOT_QUERY_KEY,
    queryFn: () => fetchPsdSnapshot(),
    select: (snapshot) => {
      const view = snapshot.positions_view;
      if (!view || !Array.isArray(view.single_stocks)) {
        return [];
      }
      return view.single_stocks.map((entry) => mapSingleStock(entry as PSDLeg, snapshot));
    },
    staleTime: 15_000,
    refetchInterval: 30_000,
  });
}
