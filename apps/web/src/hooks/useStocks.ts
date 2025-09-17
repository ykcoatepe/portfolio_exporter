import { useMemo } from "react";
import { useQuery, UseQueryResult } from "@tanstack/react-query";

import type { StockRow, StocksApiResponse } from "../lib/types";

const toNumber = (value: unknown, fallback = Number.NaN): number => {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
};

function mapApiToRow(entry: StocksApiResponse["data"][number]): StockRow {
  return {
    symbol: entry.symbol,
    quantity: toNumber(entry.quantity, 0),
    averagePrice: toNumber(entry.average_price),
    markPrice: toNumber(entry.mark_price),
    markSource: entry.mark_source,
    markTime: typeof entry.mark_time === "string" ? entry.mark_time : "",
    dayPnlAmount: toNumber(entry.day_pnl_amount),
    dayPnlPercent: toNumber(entry.day_pnl_percent),
    totalPnlAmount: toNumber(entry.total_pnl_amount),
    totalPnlPercent: toNumber(entry.total_pnl_percent),
    currency: entry.currency ?? "USD",
    exposure: entry.exposure !== undefined ? toNumber(entry.exposure) : undefined,
  };
}

export async function fetchStocks(baseUrl = ""): Promise<StockRow[]> {
  const origin =
    baseUrl ||
    (typeof window !== "undefined" ? window.location.origin : "http://localhost");
  const sanitizedBase = origin.replace(/\/+$/, "");
  const endpoint = `${sanitizedBase}/positions/stocks`;
  const response = await fetch(endpoint, {
    headers: { Accept: "application/json" },
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(`Request failed with status ${response.status}`);
  }
  const payload = (await response.json()) as StocksApiResponse;
  const rows = Array.isArray(payload.data) ? payload.data.map(mapApiToRow) : [];
  return rows.sort((a, b) => b.dayPnlAmount - a.dayPnlAmount);
}

export function useStocks(): UseQueryResult<StockRow[], Error> {
  const query = useQuery<StockRow[], Error>({
    queryKey: ["stocks"],
    queryFn: () => fetchStocks(),
    staleTime: 15_000,
    refetchInterval: 30_000,
  });

  const data = useMemo(() => query.data ?? [], [query.data]);

  return { ...query, data };
}
