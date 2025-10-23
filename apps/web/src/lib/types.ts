export type MarkSource = "MID" | "LAST" | "PREV" | "MISSING";

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
  markTime: string | null;
  dayPnlAmount: number | null;
  dayPnlPercent: number | null;
  totalPnlAmount: number | null;
  totalPnlPercent: number | null;
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

export interface OptionComboDisplay {
  combo_label: string;
  short_ul: string;
  expiry_short: string | null;
}

export interface OptionLegDisplay {
  leg_label: string;
  short_ul: string;
  expiry_short: string | null;
}

/** @deprecated use OptionComboRow.progressPct */
export type ComboProgress = {
  pctOfGoal: number | null;
  pctOfR: number | null;
};

export interface OptionComboLegApi {
  id?: string;
  leg_id?: string;
  combo_id: string | null;
  combo_group_id?: string | null;
  symbol?: string;
  underlying: string;
  expiry: string;
  strike: number;
  right: OptionRight | string;
  quantity: number;
  mark_price: number | null;
  mark_source: MarkSource;
  mark_time: string | null;
  mark?: number | null;
  bid?: number | null;
  ask?: number | null;
  last?: number | null;
  previous_close?: number | null;
  bid_ts?: string | null;
  ask_ts?: string | null;
  last_ts?: string | null;
  previous_close_ts?: string | null;
  mark_ts?: string | null;
  ts?: string | null;
  updated_at?: string | null;
  delta: number | null;
  gamma: number | null;
  theta: number | null;
  vega: number | null;
  iv?: number | null;
  day_pnl_amount: number | null;
  day_pnl_percent: number | null;
  total_pnl_amount: number | null;
  total_pnl_percent: number | null;
  tp_band_pct?: number[] | null;
  tp_band_low_pct?: number | null;
  tp_band_high_pct?: number | null;
  tp_hit?: boolean;
  tp_done?: boolean;
  sl_hit?: boolean;
  next_action?: string;
  /** Canonical progress toward target in [0..1]. */
  progress_pct?: number | null;
  /** @deprecated use progress_pct */
  progress_pct_of_goal?: number | null;
  /** @deprecated use progress_pct */
  progress_pct_of_r?: number | null;
  /** @deprecated use progress_pct */
  progress_pct_of_max?: number | null;
  label?: string;
  display?: OptionLegDisplay;
}

export interface OptionComboApi {
  id?: string;
  combo_id?: string;
  strategy: string;
  underlying: string;
  expiry: string;
  dte: number;
  side?: "credit" | "debit";
  net_price?: number;
  net_premium?: number;
  mark_price: number | null;
  mark_source: MarkSource;
  mark_time: string | null;
  greeks?: OptionGreekSummary;
  sum_greeks?: OptionGreekSummary;
  day_pnl_amount: number | null;
  day_pnl_percent: number | null;
  total_pnl_amount: number | null;
  total_pnl_percent: number | null;
  tp_band_pct?: number[] | null;
  tp_band_low_pct?: number | null;
  tp_band_high_pct?: number | null;
  tp_hit?: boolean;
  tp_done?: boolean;
  sl_hit?: boolean;
  sl_r?: number | null;
  next_action?: string;
  /** Canonical progress toward target in [0..1]. */
  progress_pct?: number | null;
  /** @deprecated use progress_pct */
  progress_pct_of_goal?: number | null;
  /** @deprecated use progress_pct */
  progress_pct_of_r?: number | null;
  /** @deprecated use progress_pct */
  progress_pct_of_max?: number | null;
  /** @deprecated use progress_pct */
  progress?: { pct_of_goal?: number | null; pct_of_r?: number | null } | null;
  legs: OptionComboLegApi[];
  combo_group_id?: string | null;
  combo_qty?: number | null;
  label?: string;
  display?: OptionComboDisplay | null;
}

export interface OptionComboGroupLegApi {
  symbol: string;
  underlying: string;
  right: OptionRight | string;
  strike: number;
  expiry: string;
  quantity: number;
  sum_greeks: OptionGreekSummary;
  mark: number | null;
  mark_source: MarkSource | string;
  stale_seconds: number | null;
  combo_group_id: string;
  label?: string;
  display?: OptionLegDisplay;
}

export interface OptionComboGroupApi {
  combo_group_id: string;
  strategy: string;
  underlying: string;
  group_qty: number;
  group_net_price: number;
  group_mark?: number | null;
  group_mark_price?: number | null;
  group_pnl_unrealized?: number | null;
  mark_price?: number | null;
  mark?: number | null;
  dte: number;
  sum_greeks: OptionGreekSummary;
  mark_source: MarkSource;
  stale_seconds: number | null;
  tp_band_pct?: number[] | null;
  tp_band_low_pct?: number | null;
  tp_band_high_pct?: number | null;
  tp_hit?: boolean;
  tp_done?: boolean;
  sl_hit?: boolean;
  sl_r?: number | null;
  next_action?: string | null;
  /** Canonical progress toward target in [0..1]. */
  progress_pct?: number | null;
  /** @deprecated use progress_pct */
  progress_pct_of_goal?: number | null;
  /** @deprecated use progress_pct */
  progress_pct_of_r?: number | null;
  /** @deprecated use progress_pct */
  progress?: { pct_of_goal?: number | null; pct_of_r?: number | null } | null;
  label?: string;
  display?: OptionComboDisplay | null;
  legs: OptionComboGroupLegApi[];
}

export interface PlaybookApiMeta {
  vix?: number | null;
  vix_source?: string | null;
  tp_band_pct?: number[] | null;
}

export interface PlaybookMeta {
  vix: number | null;
  vixSource: string | null;
  tpBandLowPct: number | null;
  tpBandHighPct: number | null;
}

export interface OptionsApiResponse {
  combos: OptionComboApi[];
  legs: OptionComboLegApi[];
  combo_groups?: OptionComboGroupApi[];
  playbook?: PlaybookApiMeta | null;
  as_of?: string | null;
}

export interface OptionComboLegRow {
  id: string;
  symbol: string;
  label: string;
  labelText: string;
  labelTooltip: string;
  underlying: string;
  shortUnderlying: string;
  expiry: string;
  expiryShort: string | null;
  strike: number;
  right: string;
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
  comboGroupId: string | null;
  tpBandLowPct: number | null;
  tpBandHighPct: number | null;
  tpHit: boolean;
  tpDone: boolean;
  slHit: boolean;
  nextAction: string;
  /** Canonical progress toward target in [0..1]. */
  progressPct: number | null;
  /** @deprecated use progressPct */
  progressPctOfGoal?: number | null;
  /** @deprecated use progressPct */
  progressPctOfR?: number | null;
  /** @deprecated use progressPct */
  progressPctOfMax?: number | null;
  isNearTarget: boolean;
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
  label: string;
  display: OptionComboDisplay | null;
  comboGroupId: string | null;
  comboQty: number;
  groupNetPrice: number;
  tpBandLowPct: number | null;
  tpBandHighPct: number | null;
  tpBandPct: readonly [number, number] | null;
  tpHit: boolean;
  tpDone: boolean;
  slHit: boolean;
  slR: number | null;
  nextAction: string;
  /** Canonical progress toward target in [0..1]. */
  progressPct: number | null;
  /** @deprecated use progressPct */
  progressPctOfGoal?: number | null;
  /** @deprecated use progressPct */
  progressPctOfR?: number | null;
  /** @deprecated use progressPct */
  progressPctOfMax?: number | null;
  /** @deprecated use progressPct */
  progress?: ComboProgress | null;
  isNearTarget: boolean;
  statusPriority: number;
}

export interface OptionComboGroupRow extends OptionGreekSummary {
  id: string;
  strategy: string;
  underlying: string;
  dte: number;
  groupQty: number;
  groupNetPrice: number;
  netPrice: number;
  mark: number | null;
  markSource: MarkSource;
  staleSeconds: number | null;
  label: string;
  display: OptionComboDisplay | null;
  legs: OptionComboLegRow[];
  pnlUnrealized: number | null;
  tpBandLowPct: number | null;
  tpBandHighPct: number | null;
  tpBandPct: readonly [number, number] | null;
  tpHit: boolean;
  tpDone: boolean;
  slHit: boolean;
  slR: number | null;
  nextAction: string | null;
  /** Canonical progress toward target in [0..1]. */
  progressPct: number | null;
  /** @deprecated use progressPct */
  progressPctOfGoal?: number | null;
  /** @deprecated use progressPct */
  progressPctOfR?: number | null;
  /** @deprecated use progressPct */
  progress?: ComboProgress | null;
}

export interface OptionLegRow extends OptionGreekSummary {
  id: string;
  comboId: string | null;
  comboGroupId: string | null;
  symbol: string;
  label: string;
  labelText: string;
  labelTooltip: string;
  shortUnderlying: string;
  expiryShort: string | null;
  underlying: string;
  expiry: string;
  dte: number;
  strike: number;
  right: string;
  quantity: number;
  markPrice: number | null;
  markSource: MarkSource;
  markTime: string | null;
  iv: number | null;
  dayPnlAmount: number | null;
  dayPnlPercent: number | null;
  totalPnlAmount: number | null;
  totalPnlPercent: number | null;
  tpBandLowPct: number | null;
  tpBandHighPct: number | null;
  tpHit: boolean;
  tpDone: boolean;
  slHit: boolean;
  nextAction: string;
  /** Canonical progress toward target in [0..1]. */
  progressPct: number | null;
  /** @deprecated use progressPct */
  progressPctOfGoal?: number | null;
  /** @deprecated use progressPct */
  progressPctOfR?: number | null;
  /** @deprecated use progressPct */
  progressPctOfMax?: number | null;
  isNearTarget: boolean;
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
  data_source?: string | null;
  dataSource?: string | null;
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
  session?: MarketSessionApiResponse | null;
  session_info?: MarketSessionApiResponse | null;
  meta?: {
    latest_ts?: string | null;
    [key: string]: unknown;
  } | null;
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

export type MarketSessionState = "RTH" | "ETH" | "CLOSED";

export interface MarketSessionApiResponse {
  exchange?: string | null;
  tz?: string | null;
  state?: string | null;
  as_of?: string | null;
  asOf?: string | null;
  rth_open?: string | null;
  rthOpen?: string | null;
  rth_close?: string | null;
  rthClose?: string | null;
  source?: string | null;
  note?: string | null;
}

export interface MarketSession {
  exchange: string;
  tz: string;
  state: MarketSessionState;
  asOf: string;
  rthOpen: string | null;
  rthClose: string | null;
  source: string;
  note: string | null;
}

export interface PortfolioStats {
  netLiq: number | null;
  var95: number | null;
  marginPct: number | null;
  updatedAt: string | null;
  counts: PortfolioStatsCounts;
  rulesEvalMs: number | null;
  tradesPriorPositions: boolean;
  dataSource: string | null;
  session: MarketSession | null;
  sessionInfo?: MarketSession | null;
  latestTs: string | null;
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
  price_source?: string;
  mark_source?: string;
  stale_s: number;
  day_pnl?: number;
  day_pnl_percent?: number;
  day_pnl_pct?: number;
  pnl_intraday: number;
  pnl_unrealized?: number;
  pnl_unrealized_percent?: number;
  pnl_unrealized_pct?: number;
  total_pnl?: number;
  total_pnl_percent?: number;
  greeks?: PSDGreeks;
  right?: string;
  strike?: number;
  expiry?: string;
  previous_close?: number;
  updated_at?: string;
  mark_time?: string;
  conId?: number;
};

export type PSDCombo = {
  combo_id: string;
  name: string;
  underlier?: string;
  legs: PSDLeg[];
  pnl_intraday: number;
  pnl_unrealized?: number;
  day_pnl_percent?: number;
  day_pnl_pct?: number;
  pnl_unrealized_percent?: number;
  pnl_unrealized_pct?: number;
  total_pnl?: number;
  total_pnl_percent?: number;
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
  session_info?: MarketSession;
  meta?: {
    session?: MarketSession;
    [key: string]: unknown;
  };
  positions?: unknown[];
  positions_view?: PSDPositionsView;
  quotes?: Record<string, unknown>;
  risk?: Record<string, unknown>;
  [key: string]: unknown;
};
