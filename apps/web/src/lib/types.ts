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

export type OptionRight = "C" | "P";

export interface OptionGreekSummary {
  delta: number | null;
  gamma: number | null;
  theta: number | null;
  vega: number | null;
}

export interface OptionComboLegApi {
  id: string;
  combo_id: string | null;
  underlying: string;
  expiry: string;
  strike: number;
  right: OptionRight;
  quantity: number;
  mark_price: number | null;
  mark_source: MarkSource;
  mark_time: string | null;
  delta: number | null;
  gamma: number | null;
  theta: number | null;
  vega: number | null;
  iv?: number | null;
  day_pnl_amount: number | null;
  day_pnl_percent: number | null;
  total_pnl_amount: number | null;
  total_pnl_percent: number | null;
  labels?: string[];
}

export interface OptionComboApi {
  id: string;
  strategy: string;
  underlying: string;
  expiry: string;
  dte: number;
  side: "credit" | "debit";
  net_premium: number;
  mark_price: number | null;
  mark_source: MarkSource;
  mark_time: string | null;
  greeks: OptionGreekSummary;
  day_pnl_amount: number | null;
  day_pnl_percent: number | null;
  total_pnl_amount: number | null;
  total_pnl_percent: number | null;
  legs: OptionComboLegApi[];
}

export interface OptionsApiResponse {
  combos: OptionComboApi[];
  legs: OptionComboLegApi[];
  as_of?: string | null;
}

export interface OptionComboLegRow {
  id: string;
  strike: number;
  right: OptionRight;
  quantity: number;
  markPrice: number | null;
  markSource: MarkSource;
  markTime: string | null;
  delta: number | null;
  gamma: number | null;
  theta: number | null;
  vega: number | null;
  dayPnlAmount: number | null;
  dayPnlPercent: number | null;
  totalPnlAmount: number | null;
  totalPnlPercent: number | null;
}

export interface OptionComboRow extends OptionGreekSummary {
  id: string;
  strategy: string;
  underlying: string;
  expiry: string;
  dte: number;
  side: "credit" | "debit";
  netPremium: number;
  markPrice: number | null;
  markSource: MarkSource;
  markTime: string | null;
  dayPnlAmount: number | null;
  dayPnlPercent: number | null;
  totalPnlAmount: number | null;
  totalPnlPercent: number | null;
  legs: OptionComboLegRow[];
}

export interface OptionLegRow extends OptionGreekSummary {
  id: string;
  comboId: string | null;
  underlying: string;
  expiry: string;
  dte: number;
  strike: number;
  right: OptionRight;
  quantity: number;
  markPrice: number | null;
  markSource: MarkSource;
  markTime: string | null;
  iv: number | null;
  dayPnlAmount: number | null;
  dayPnlPercent: number | null;
  totalPnlAmount: number | null;
  totalPnlPercent: number | null;
  isOrphan: boolean;
}
