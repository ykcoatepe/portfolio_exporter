import { http, HttpResponse } from "msw";

import type { StocksApiResponse } from "../lib/types";

const minutesAgo = (anchor: Date, minutes: number) =>
  new Date(anchor.getTime() - minutes * 60_000).toISOString();

export const buildStocksResponse = (
  overrides: Partial<StocksApiResponse> = {},
): StocksApiResponse => {
  const now = new Date();
  const minutesAgoFromNow = (minutes: number) => minutesAgo(now, minutes);
  const base: StocksApiResponse = {
    as_of: now.toISOString(),
    data: [
      {
        symbol: "AAPL",
        quantity: 120,
        average_price: 173.52,
        mark_price: 176.18,
        mark_source: "MID",
        mark_time: minutesAgoFromNow(1),
        day_pnl_amount: 412.35,
        day_pnl_percent: 2.38,
        total_pnl_amount: 1185.67,
        total_pnl_percent: 6.85,
        currency: "USD",
      },
      {
        symbol: "MSFT",
        quantity: 96,
        average_price: 292.4,
        mark_price: 288.95,
        mark_source: "LAST",
        mark_time: minutesAgoFromNow(7),
        day_pnl_amount: -128.12,
        day_pnl_percent: -0.86,
        total_pnl_amount: 642.31,
        total_pnl_percent: 2.27,
        currency: "USD",
      },
      {
        symbol: "NVDA",
        quantity: 54,
        average_price: 446.75,
        mark_price: 452.21,
        mark_source: "PREV",
        mark_time: minutesAgoFromNow(16),
        day_pnl_amount: 238.91,
        day_pnl_percent: 1.42,
        total_pnl_amount: 1835.44,
        total_pnl_percent: 7.14,
        currency: "USD",
        exposure: 24419.34,
      },
    ],
  };

  return {
    as_of: overrides.as_of ?? base.as_of,
    data: overrides.data ?? base.data,
  };
};

export const handlers = [
  http.get("*/positions/stocks", () => HttpResponse.json(buildStocksResponse())),
];
