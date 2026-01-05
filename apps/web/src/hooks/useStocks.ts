import { useQuery, type UseQueryResult } from "@tanstack/react-query";

import { PSD_SNAPSHOT_QUERY_KEY, fetchPsdSnapshot } from "./usePsdSnapshot";
import { resolveApiBaseUrl } from "../lib/http";
import type {
  MarkSource,
  PSDSnapshot,
  PSDLeg,
  StockPositionApi,
  StocksApiResponse,
  StockRow,
} from "../lib/types";

const MARK_SOURCE_FALLBACK: MarkSource = "MISSING";

const toNumber = (value: unknown, fallback = 0): number => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

const toNullableNumber = (value: unknown): number | null => {
  if (value === null || value === undefined) {
    return null;
  }
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const toNullablePercent = (value: unknown): number | null => {
  const parsed = toNullableNumber(value);
  if (parsed === null) {
    return null;
  }
  return parsed / 100;
};

const coerceTimestamp = (value: unknown, fallback?: unknown): string | null => {
  const pick = (candidate: unknown): string | null => {
    if (typeof candidate !== "string") {
      return null;
    }
    const trimmed = candidate.trim();
    return trimmed ? trimmed : null;
  };
  return pick(value) ?? pick(fallback);
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

const computePercent = (amount: number | null, basis: number | null): number | null => {
  if (amount === null || basis === null) {
    return null;
  }
  if (!Number.isFinite(amount) || !Number.isFinite(basis)) {
    return null;
  }
  const denominator = Math.abs(basis);
  if (denominator === 0) {
    return null;
  }
  const ratio = amount / denominator;
  return Number.isFinite(ratio) ? ratio : null;
};

const mapSingleStock = (entry: PSDLeg, snapshot: PSDSnapshot | undefined): StockRow => {
  const quantity = toNumber(entry.qty, 0);
  const avgCostValue = toNullableNumber(entry.avg_cost);
  const avgCost = avgCostValue ?? 0;
  const markPriceValue = toNullableNumber(entry.mark);
  const markPrice = markPriceValue ?? 0;
  const dayPnlAmount = toNullableNumber(entry.day_pnl ?? entry.pnl_intraday);
  const totalPnlAmount = toNullableNumber(
    entry.pnl_unrealized ?? entry.total_pnl ?? entry.pnl_intraday,
  );
  const previousClose = toNullableNumber(entry.previous_close);

  const dayBasis =
    previousClose !== null ? Math.abs(quantity) * previousClose : null;
  const totalBasis =
    avgCostValue !== null ? Math.abs(quantity) * avgCostValue : null;

  const dayPercentFromApi = toNullableNumber(
    entry.day_pnl_percent ?? entry.day_pnl_pct,
  );
  const totalPercentFromApi = toNullableNumber(
    entry.pnl_unrealized_percent ?? entry.pnl_unrealized_pct ?? entry.total_pnl_percent,
  );

  const dayPnlPercent =
    dayPercentFromApi !== null
      ? dayPercentFromApi / 100
      : computePercent(dayPnlAmount, dayBasis);
  const totalPnlPercent =
    totalPercentFromApi !== null
      ? totalPercentFromApi / 100
      : computePercent(totalPnlAmount, totalBasis);

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
    dayPnlPercent,
    totalPnlAmount,
    totalPnlPercent,
    currency: "USD",
  };
};

const mapStockPosition = (
  entry: StockPositionApi,
  asOf: string | null,
): StockRow => {
  const quantity = toNumber(entry.quantity, 0);
  const averagePrice = toNullableNumber(entry.average_price) ?? 0;
  const markPrice = toNullableNumber(entry.mark_price) ?? 0;
  const dayPnlAmount = toNullableNumber(entry.day_pnl_amount);
  const totalPnlAmount = toNullableNumber(entry.total_pnl_amount);
  const dayPnlPercent = toNullablePercent(entry.day_pnl_percent);
  const totalPnlPercent = toNullablePercent(entry.total_pnl_percent);
  const markSource = normalizeMarkSource(entry.mark_source);
  const markTime = coerceTimestamp(entry.mark_time, asOf);
  const currency =
    typeof entry.currency === "string" && entry.currency.trim()
      ? entry.currency.trim()
      : "USD";
  const exposure = toNullableNumber(entry.exposure);

  const row: StockRow = {
    symbol: entry.symbol,
    quantity,
    averagePrice,
    markPrice,
    markSource,
    markTime,
    dayPnlAmount,
    dayPnlPercent,
    totalPnlAmount,
    totalPnlPercent,
    currency,
  };
  if (exposure !== null) {
    row.exposure = exposure;
  }
  return row;
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

async function fetchStocks(baseUrl = ""): Promise<StockRow[]> {
  const origin = resolveApiBaseUrl(baseUrl);
  const response = await fetch(`${origin}/positions/stocks`, {
    headers: { accept: "application/json" },
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }
  const payload = (await response.json()) as StocksApiResponse;
  const asOf = typeof payload.as_of === "string" ? payload.as_of : null;
  const data = Array.isArray(payload.data) ? payload.data : [];
  return data.map((entry) => mapStockPosition(entry, asOf));
}

export { fetchStocks };
