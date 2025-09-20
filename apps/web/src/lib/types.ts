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

export interface PortfolioStatsApiResponse {
  equity_count?: number | null;
  quote_count?: number | null;
  option_legs_count?: number | null;
  combos_matched?: number | null;
  stale_quotes_count?: number | null;
  rules_count?: number | null;
  breaches_count?: number | null;
  rules_eval_ms?: number | null;
  combos_detection_ms?: number | null;
  trades_prior_positions?: boolean | null;
  net_liq?: number | null;
  netLiq?: number | null;
  var95?: number | null;
  var_95?: number | null;
  var95_1d_pct?: number | null;
  margin_pct?: number | null;
  marginPct?: number | null;
  margin_used_pct?: number | null;
  updated_at?: string | null;
  updatedAt?: string | null;
}

export interface PortfolioStatsCounts {
  equities: number;
  quotes: number;
  optionLegs: number;
  combos: number;
  staleQuotes: number;
  rules?: number;
  breaches?: number;
}

export interface PortfolioStats {
  netLiq: number | null;
  var95: number | null;
  marginPct: number | null;
  updatedAt: string | null;
  counts: PortfolioStatsCounts;
  rulesEvalMs: number | null;
  tradesPriorPositions: boolean;
}

export type PSDGreeks = {
  delta?: number;
  gamma?: number;
  theta?: number;
};

export type PSDLeg = {
  secType: "STK" | "OPT" | "FOP";
  symbol: string;
  qty: number;
  avg_cost: number;
  multiplier?: number;
  mark: number;
  price_source: string;
  stale_s: number;
  pnl_intraday: number;
  greeks?: PSDGreeks;
  right?: string;
  strike?: number;
  expiry?: string;
  conId?: number;
};

export type PSDCombo = {
  combo_id: string;
  name: string;
  underlier?: string;
  legs: PSDLeg[];
  pnl_intraday: number;
  greeks_agg?: PSDGreeks;
};

export type PSDPositionsView = {
  single_stocks: PSDLeg[];
  option_combos: PSDCombo[];
  single_options: PSDLeg[];
};

export type PSDSnapshot = {
  ts?: number | null;
  session: "RTH" | "EXT" | "CLOSED";
  positions?: unknown[];
  positions_view?: PSDPositionsView;
  quotes?: Record<string, unknown>;
  risk?: Record<string, unknown>;
  [key: string]: unknown;
};
