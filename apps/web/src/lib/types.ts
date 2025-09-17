export type MarkSource = "MID" | "LAST" | "PREV";

export interface StockPositionApi {
  symbol: string;
  quantity: number;
  average_price: number;
  mark_price: number;
  mark_source: MarkSource;
  mark_time: string;
  day_pnl_amount: number;
  day_pnl_percent: number;
  total_pnl_amount: number;
  total_pnl_percent: number;
  currency?: string;
  exposure?: number;
}

export interface StocksApiResponse {
  data: StockPositionApi[];
  as_of?: string | null;
}

export interface StockRow {
  symbol: string;
  quantity: number;
  averagePrice: number;
  markPrice: number;
  markSource: MarkSource;
  markTime: string;
  dayPnlAmount: number;
  dayPnlPercent: number;
  totalPnlAmount: number;
  totalPnlPercent: number;
  currency: string;
  exposure?: number;
}
