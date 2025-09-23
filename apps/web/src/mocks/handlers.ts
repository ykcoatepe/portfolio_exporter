import { http, HttpResponse } from "msw";

import type {
  OptionsApiResponse,
  OptionComboGroupApi,
  OptionComboLegApi,
  OptionGreekSummary,
  PortfolioStatsApiResponse,
  PSDSnapshot,
  StocksApiResponse,
} from "../lib/types";
import fundamentalsFixture from "./data/fundamentals.json";

const minutesAgo = (anchor: Date, minutes: number) =>
  new Date(anchor.getTime() - minutes * 60_000).toISOString();

interface RulesSummaryCounters {
  total?: number;
  critical: number;
  warning: number;
  info: number;
}

interface RuleBreachFixture {
  id: string;
  rule: string;
  severity: "CRITICAL" | "WARNING" | "INFO";
  subject: string;
  symbol?: string | null;
  occurred_at: string;
  description?: string | null;
  status?: string | null;
}

interface RulesSummaryFixture {
  as_of: string;
  breaches: RulesSummaryCounters;
  top: RuleBreachFixture[];
  focus_symbols: string[];
  rules_total?: number;
  evaluation_ms?: number;
  fundamentals?: typeof fundamentalsFixture;
}

interface RulesCatalogFixture {
  version: number;
  updated_at: string;
  updated_by: string | null;
  rules: Array<Record<string, unknown>>;
}

interface CatalogDiffFixture {
  added: Array<Record<string, unknown>>;
  removed: Array<Record<string, unknown>>;
  changed: Array<Record<string, unknown>>;
}

interface RulesCatalogValidationFixture {
  ok: boolean;
  counters: RulesSummaryCounters;
  top: RuleBreachFixture[];
  errors: string[];
  diff?: CatalogDiffFixture;
}

const seedCatalogRules: Array<Record<string, unknown>> = [
  {
    rule_id: "combo__annualized_premium_high",
    name: "Annualized premium >=30% within a week",
    severity: "CRITICAL",
    scope: "COMBO",
    filter: "dte <= 7",
    expr: "annualized_premium_pct >= 30",
  },
  {
    rule_id: "leg__iv_missing_near_term",
    name: "Missing IV for near-term legs",
    severity: "WARNING",
    scope: "LEG",
    filter: "dte <= 5",
    expr: "iv is None",
  },
];

let catalogState: RulesCatalogFixture;

export const resetCatalogState = (): void => {
  catalogState = {
    version: 12,
    updated_at: new Date().toISOString(),
    updated_by: "ops-admin",
    rules: seedCatalogRules.map((rule) => ({ ...rule })),
  };
};

resetCatalogState();

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

export const buildOptionsResponse = (
  overrides: Partial<OptionsApiResponse> = {},
): OptionsApiResponse => {
  const now = new Date();
  const minutesAgoFromNow = (minutes: number) => minutesAgo(now, minutes);

  const baseLegs: OptionComboLegApi[] = [
    {
      id: "leg-condor-short-call",
      combo_id: "combo-iron-condor",
      combo_group_id: "group-iron-condor",
      symbol: "SPX  20241018C00460000",
      underlying: "SPX",
      expiry: "2024-10-18",
      strike: 4600,
      right: "C",
      quantity: -10,
      mark_price: 1.05,
      mark_source: "MID",
      mark_time: minutesAgoFromNow(2),
      delta: 0.12,
      gamma: 0.01,
      theta: -4.2,
      vega: -18.5,
      iv: 0.19,
      day_pnl_amount: 480,
      day_pnl_percent: 12.4,
      total_pnl_amount: 1240,
      total_pnl_percent: 18.1,
      label: "SPX 4600C • Oct 18 '24",
      display: {
        leg_label: "SPX 4600C • Oct 18 '24",
        short_ul: "SPX",
        expiry_short: "Oct 18 '24",
      },
    },
    {
      id: "leg-condor-long-call",
      combo_id: "combo-iron-condor",
      combo_group_id: "group-iron-condor",
      symbol: "SPX20241018C00465000",
      underlying: "SPX",
      expiry: "2024-10-18",
      strike: 4650,
      right: "C",
      quantity: 10,
      mark_price: 0.52,
      mark_source: "MID",
      mark_time: minutesAgoFromNow(2),
      delta: -0.04,
      gamma: -0.01,
      theta: 1.6,
      vega: 9.3,
      iv: 0.19,
      day_pnl_amount: -140,
      day_pnl_percent: -8.4,
      total_pnl_amount: -260,
      total_pnl_percent: -11.3,
      label: "SPX 4650C • Oct 18 '24",
      display: {
        leg_label: "SPX 4650C • Oct 18 '24",
        short_ul: "SPX",
        expiry_short: "Oct 18 '24",
      },
    },
    {
      id: "leg-condor-short-put",
      combo_id: "combo-iron-condor",
      combo_group_id: "group-iron-condor",
      symbol: "SPX  20241018P00430000",
      underlying: "SPX",
      expiry: "2024-10-18",
      strike: 4300,
      right: "P",
      quantity: -10,
      mark_price: 1.12,
      mark_source: "MID",
      mark_time: minutesAgoFromNow(3),
      delta: -0.18,
      gamma: 0.0,
      theta: -4.7,
      vega: -21.2,
      iv: 0.21,
      day_pnl_amount: 520,
      day_pnl_percent: 14.2,
      total_pnl_amount: 1420,
      total_pnl_percent: 21.6,
      label: "SPX 4300P • Oct 18 '24",
      display: {
        leg_label: "SPX 4300P • Oct 18 '24",
        short_ul: "SPX",
        expiry_short: "Oct 18 '24",
      },
    },
    {
      id: "leg-condor-long-put",
      combo_id: "combo-iron-condor",
      combo_group_id: "group-iron-condor",
      symbol: "SPX20241018P00425000",
      underlying: "SPX",
      expiry: "2024-10-18",
      strike: 4250,
      right: "P",
      quantity: 10,
      mark_price: 0.46,
      mark_source: "MID",
      mark_time: minutesAgoFromNow(3),
      delta: 0.06,
      gamma: -0.0,
      theta: 1.9,
      vega: 10.1,
      iv: 0.21,
      day_pnl_amount: -160,
      day_pnl_percent: -9.8,
      total_pnl_amount: -330,
      total_pnl_percent: -12.1,
      label: "SPX 4250P • Oct 18 '24",
      display: {
        leg_label: "SPX 4250P • Oct 18 '24",
        short_ul: "SPX",
        expiry_short: "Oct 18 '24",
      },
    },
    {
      id: "leg-diagonal-long-call",
      combo_id: "combo-call-diagonal",
      combo_group_id: "group-call-diagonal",
      symbol: "AAPL 20241115C00195000",
      underlying: "AAPL",
      expiry: "2024-11-15",
      strike: 195,
      right: "C",
      quantity: 5,
      mark_price: 7.4,
      mark_source: "LAST",
      mark_time: minutesAgoFromNow(5),
      delta: 0.28,
      gamma: 0.02,
      theta: -0.3,
      vega: 6.8,
      iv: 0.27,
      day_pnl_amount: 260,
      day_pnl_percent: 3.7,
      total_pnl_amount: 620,
      total_pnl_percent: 9.3,
      label: "AAPL 195C • Nov 15 '24",
      display: {
        leg_label: "AAPL 195C • Nov 15 '24",
        short_ul: "AAPL",
        expiry_short: "Nov 15 '24",
      },
    },
    {
      id: "leg-diagonal-short-call",
      combo_id: "combo-call-diagonal",
      combo_group_id: "group-call-diagonal",
      symbol: "AAPL 20240920C00195000",
      underlying: "AAPL",
      expiry: "2024-09-20",
      strike: 195,
      right: "C",
      quantity: -5,
      mark_price: 2.8,
      mark_source: "LAST",
      mark_time: minutesAgoFromNow(6),
      delta: -0.14,
      gamma: -0.01,
      theta: 1.0,
      vega: -3.2,
      iv: 0.31,
      day_pnl_amount: -70,
      day_pnl_percent: -2.6,
      total_pnl_amount: 160,
      total_pnl_percent: 5.8,
      label: "AAPL 195C • Sep 20 '24",
      display: {
        leg_label: "AAPL 195C • Sep 20 '24",
        short_ul: "AAPL",
        expiry_short: "Sep 20 '24",
      },
    },
    {
      id: "leg-msft-vertical-long",
      combo_id: "combo-msft-put-vertical",
      combo_group_id: "group-msft-put-vertical",
      symbol: "MSFT 20241018P00330000",
      underlying: "MSFT",
      expiry: "2024-10-18",
      strike: 330,
      right: "P",
      quantity: 3,
      mark_price: 3.9,
      mark_source: "MID",
      mark_time: minutesAgoFromNow(4),
      delta: -0.32,
      gamma: 0.01,
      theta: -1.3,
      vega: 8.4,
      iv: 0.29,
      day_pnl_amount: 210,
      day_pnl_percent: 6.1,
      total_pnl_amount: 420,
      total_pnl_percent: 12.4,
      label: "MSFT 330P • Oct 18 '24",
      display: {
        leg_label: "MSFT 330P • Oct 18 '24",
        short_ul: "MSFT",
        expiry_short: "Oct 18 '24",
      },
    },
    {
      id: "leg-msft-vertical-short",
      combo_id: "combo-msft-put-vertical",
      combo_group_id: "group-msft-put-vertical",
      symbol: "MSFT 20241018P00325000",
      underlying: "MSFT",
      expiry: "2024-10-18",
      strike: 325,
      right: "P",
      quantity: -3,
      mark_price: 2.05,
      mark_source: "MID",
      mark_time: minutesAgoFromNow(4),
      delta: 0.22,
      gamma: -0.01,
      theta: 0.8,
      vega: -6.1,
      iv: 0.28,
      day_pnl_amount: -95,
      day_pnl_percent: -4.4,
      total_pnl_amount: -210,
      total_pnl_percent: -9.9,
      label: "MSFT 325P • Oct 18 '24",
      display: {
        leg_label: "MSFT 325P • Oct 18 '24",
        short_ul: "MSFT",
        expiry_short: "Oct 18 '24",
      },
    },
    {
      id: "leg-es-stop-short-call",
      combo_id: "combo-es-credit-stop",
      combo_group_id: "group-es-credit-stop",
      symbol: "ES  20241004C00455000",
      underlying: "ES",
      expiry: "2024-10-04",
      strike: 4550,
      right: "C",
      quantity: -4,
      mark_price: 0.85,
      mark_source: "MID",
      mark_time: minutesAgoFromNow(7),
      delta: 0.09,
      gamma: 0.01,
      theta: -1.2,
      vega: -6.8,
      iv: 0.24,
      day_pnl_amount: 120,
      day_pnl_percent: 9.1,
      total_pnl_amount: 280,
      total_pnl_percent: 18.6,
      label: "ES 4550C • Oct 4 '24",
      display: {
        leg_label: "ES 4550C • Oct 4 '24",
        short_ul: "ES",
        expiry_short: "Oct 4 '24",
      },
    },
    {
      id: "leg-es-stop-long-call",
      combo_id: "combo-es-credit-stop",
      combo_group_id: "group-es-credit-stop",
      symbol: "ES  20241004C00457500",
      underlying: "ES",
      expiry: "2024-10-04",
      strike: 4575,
      right: "C",
      quantity: 4,
      mark_price: 0.32,
      mark_source: "MID",
      mark_time: minutesAgoFromNow(7),
      delta: -0.03,
      gamma: -0.0,
      theta: 0.5,
      vega: 2.9,
      iv: 0.24,
      day_pnl_amount: -40,
      day_pnl_percent: -6.2,
      total_pnl_amount: -120,
      total_pnl_percent: -11.3,
      label: "ES 4575C • Oct 4 '24",
      display: {
        leg_label: "ES 4575C • Oct 4 '24",
        short_ul: "ES",
        expiry_short: "Oct 4 '24",
      },
    },
    {
      id: "leg-es-stop-short-put",
      combo_id: "combo-es-credit-stop",
      combo_group_id: "group-es-credit-stop",
      symbol: "ES  20241004P00440000",
      underlying: "ES",
      expiry: "2024-10-04",
      strike: 4400,
      right: "P",
      quantity: -4,
      mark_price: 0.88,
      mark_source: "MID",
      mark_time: minutesAgoFromNow(7),
      delta: -0.11,
      gamma: 0.0,
      theta: -1.4,
      vega: -7.1,
      iv: 0.25,
      day_pnl_amount: 135,
      day_pnl_percent: 10.6,
      total_pnl_amount: 300,
      total_pnl_percent: 19.2,
      label: "ES 4400P • Oct 4 '24",
      display: {
        leg_label: "ES 4400P • Oct 4 '24",
        short_ul: "ES",
        expiry_short: "Oct 4 '24",
      },
    },
    {
      id: "leg-es-stop-long-put",
      combo_id: "combo-es-credit-stop",
      combo_group_id: "group-es-credit-stop",
      symbol: "ES  20241004P00437500",
      underlying: "ES",
      expiry: "2024-10-04",
      strike: 4375,
      right: "P",
      quantity: 4,
      mark_price: 0.41,
      mark_source: "MID",
      mark_time: minutesAgoFromNow(7),
      delta: 0.05,
      gamma: -0.0,
      theta: 0.7,
      vega: 3.5,
      iv: 0.25,
      day_pnl_amount: -55,
      day_pnl_percent: -7.4,
      total_pnl_amount: -140,
      total_pnl_percent: -12.9,
      label: "ES 4375P • Oct 4 '24",
      display: {
        leg_label: "ES 4375P • Oct 4 '24",
        short_ul: "ES",
        expiry_short: "Oct 4 '24",
      },
    },
    {
      id: "leg-iwm-credit-short-call",
      combo_id: "combo-iwm-credit-near",
      combo_group_id: "group-iwm-credit-near",
      symbol: "IWM 20240906C00205000",
      underlying: "IWM",
      expiry: "2024-09-06",
      strike: 205,
      right: "C",
      quantity: -2,
      mark_price: 1.38,
      mark_source: "MID",
      mark_time: minutesAgoFromNow(1),
      delta: 0.21,
      gamma: 0.01,
      theta: -0.9,
      vega: -4.4,
      iv: 0.26,
      day_pnl_amount: 65,
      day_pnl_percent: 5.9,
      total_pnl_amount: 140,
      total_pnl_percent: 16.9,
      label: "IWM 205C • Sep 6 '24",
      display: {
        leg_label: "IWM 205C • Sep 6 '24",
        short_ul: "IWM",
        expiry_short: "Sep 6 '24",
      },
    },
    {
      id: "leg-iwm-credit-long-call",
      combo_id: "combo-iwm-credit-near",
      combo_group_id: "group-iwm-credit-near",
      symbol: "IWM 20240906C00210000",
      underlying: "IWM",
      expiry: "2024-09-06",
      strike: 210,
      right: "C",
      quantity: 2,
      mark_price: 0.62,
      mark_source: "MID",
      mark_time: minutesAgoFromNow(1),
      delta: -0.12,
      gamma: -0.0,
      theta: 0.4,
      vega: 2.1,
      iv: 0.26,
      day_pnl_amount: -25,
      day_pnl_percent: -3.8,
      total_pnl_amount: -70,
      total_pnl_percent: -9.6,
      label: "IWM 210C • Sep 6 '24",
      display: {
        leg_label: "IWM 210C • Sep 6 '24",
        short_ul: "IWM",
        expiry_short: "Sep 6 '24",
      },
    },
    {
      id: "leg-rut-debit-long-call",
      combo_id: "combo-rut-debit-near",
      combo_group_id: "group-rut-debit-near",
      symbol: "RUT 20240913C02005000",
      underlying: "RUT",
      expiry: "2024-09-13",
      strike: 2005,
      right: "C",
      quantity: 2,
      mark_price: 5.2,
      mark_source: "MID",
      mark_time: minutesAgoFromNow(9),
      delta: 0.18,
      gamma: 0.01,
      theta: -0.6,
      vega: 5.5,
      iv: 0.23,
      day_pnl_amount: 180,
      day_pnl_percent: 3.6,
      total_pnl_amount: 420,
      total_pnl_percent: 8.8,
      label: "RUT 2005C • Sep 13 '24",
      display: {
        leg_label: "RUT 2005C • Sep 13 '24",
        short_ul: "RUT",
        expiry_short: "Sep 13 '24",
      },
    },
    {
      id: "leg-rut-debit-short-call",
      combo_id: "combo-rut-debit-near",
      combo_group_id: "group-rut-debit-near",
      symbol: "RUT 20240913C02015000",
      underlying: "RUT",
      expiry: "2024-09-13",
      strike: 2015,
      right: "C",
      quantity: -2,
      mark_price: 2.8,
      mark_source: "MID",
      mark_time: minutesAgoFromNow(9),
      delta: -0.11,
      gamma: -0.01,
      theta: 0.4,
      vega: -3.3,
      iv: 0.23,
      day_pnl_amount: -70,
      day_pnl_percent: -2.8,
      total_pnl_amount: -180,
      total_pnl_percent: -7.2,
      label: "RUT 2015C • Sep 13 '24",
      display: {
        leg_label: "RUT 2015C • Sep 13 '24",
        short_ul: "RUT",
        expiry_short: "Sep 13 '24",
      },
    },
  ];

  const baseCombos = [
    {
      id: "combo-iron-condor",
      strategy: "Iron Condor",
      underlying: "SPX",
      expiry: "2024-10-18",
      dte: 32,
      side: "credit" as const,
      net_premium: 2.21,
      net_price: 2.21,
      combo_group_id: "group-iron-condor",
      combo_qty: -10,
      label: "SPX 4250/4300P + 4600/4650C • 32d • Credit 2.21",
      display: {
        combo_label: "SPX 4250/4300P + 4600/4650C • 32d • Credit 2.21",
        short_ul: "SPX",
        expiry_short: "Oct 18 '24",
      },
      mark_price: 1.98,
      mark_source: "MID" as const,
      mark_time: minutesAgoFromNow(2),
      greeks: {
        delta: -0.04,
        gamma: 0.01,
        theta: -5.4,
        vega: -20.3,
      },
      day_pnl_amount: 700,
      day_pnl_percent: 11.2,
      total_pnl_amount: 1850,
      total_pnl_percent: 24.8,
      tp_band_pct: [0.4, 0.6],
      tp_band_low_pct: 0.4,
      tp_band_high_pct: 0.6,
      tp_hit: true,
      tp_done: false,
      sl_hit: false,
      progress_pct: 0.62,
      progress_pct_of_goal: 0.62,
      progress_pct_of_max: 0.62,
      progress: {
        pct_of_goal: 0.62,
      },
    },
    {
      id: "combo-call-diagonal",
      strategy: "Call Diagonal",
      underlying: "AAPL",
      expiry: "2024-11-15",
      dte: 60,
      side: "debit" as const,
      net_premium: -4.4,
      net_price: -4.4,
      combo_group_id: "group-call-diagonal",
      combo_qty: -5,
      label: "AAPL 195C CAL • Sep→Nov • Debit 4.40",
      display: {
        combo_label: "AAPL 195C CAL • Sep→Nov • Debit 4.40",
        short_ul: "AAPL",
        expiry_short: "Nov 15 '24",
      },
      mark_price: 4.62,
      mark_source: "LAST" as const,
      mark_time: minutesAgoFromNow(5),
      greeks: {
        delta: 0.14,
        gamma: 0.02,
        theta: 0.7,
        vega: 6.4,
      },
      day_pnl_amount: 190,
      day_pnl_percent: 3.1,
      total_pnl_amount: 780,
      total_pnl_percent: 9.5,
      tp_hit: false,
      tp_done: false,
      sl_hit: false,
      progress_pct: 0.35,
      progress_pct_of_goal: 0.35,
      progress_pct_of_max: 0.35,
      progress: {
        pct_of_goal: 0.35,
      },
    },
    {
      id: "combo-msft-put-vertical",
      strategy: "Put Vertical",
      underlying: "MSFT",
      expiry: "2024-10-18",
      dte: 30,
      side: "debit" as const,
      net_premium: -1.85,
      net_price: -1.85,
      combo_group_id: "group-msft-put-vertical",
      combo_qty: 3,
      label: "MSFT 330/325P • 30d • Debit 1.85",
      display: {
        combo_label: "MSFT 330/325P • 30d • Debit 1.85",
        short_ul: "MSFT",
        expiry_short: "Oct 18 '24",
      },
      mark_price: 1.9,
      mark_source: "MID" as const,
      mark_time: minutesAgoFromNow(4),
      greeks: {
        delta: -0.1,
        gamma: 0.02,
        theta: -0.5,
        vega: 2.3,
      },
      day_pnl_amount: 115,
      day_pnl_percent: 6.6,
      total_pnl_amount: 260,
      total_pnl_percent: 14.1,
      tp_hit: false,
      tp_done: true,
      sl_hit: false,
      progress_pct: 1,
      progress_pct_of_goal: 1.0,
      progress_pct_of_max: 1.0,
      progress: {
        pct_of_goal: 1.0,
      },
    },
    {
      id: "combo-es-credit-stop",
      strategy: "Iron Condor",
      underlying: "ES",
      expiry: "2024-10-04",
      dte: 21,
      side: "credit" as const,
      net_premium: 1.15,
      net_price: 1.15,
      combo_group_id: "group-es-credit-stop",
      combo_qty: -4,
      label: "ES 4400/4425P + 4550/4575C • 21d • Credit 1.15",
      display: {
        combo_label: "ES 4400/4425P + 4550/4575C • 21d • Credit 1.15",
        short_ul: "ES",
        expiry_short: "Oct 4 '24",
      },
      mark_price: 1.32,
      mark_source: "MID" as const,
      mark_time: minutesAgoFromNow(7),
      greeks: {
        delta: -0.02,
        gamma: 0.01,
        theta: -2.7,
        vega: -10.6,
      },
      day_pnl_amount: 160,
      day_pnl_percent: 8.9,
      total_pnl_amount: 340,
      total_pnl_percent: 19.8,
      tp_band_pct: [0.35, 0.55],
      tp_band_low_pct: 0.35,
      tp_band_high_pct: 0.55,
      tp_hit: false,
      tp_done: false,
      sl_hit: true,
      progress_pct: 0.18,
      progress_pct_of_goal: 0.18,
      progress_pct_of_max: 0.18,
      progress: {
        pct_of_goal: 0.18,
      },
    },
    {
      id: "combo-iwm-credit-near",
      strategy: "Call Credit Spread",
      underlying: "IWM",
      expiry: "2024-09-06",
      dte: 7,
      side: "credit" as const,
      net_premium: 0.76,
      net_price: 0.76,
      combo_group_id: "group-iwm-credit-near",
      combo_qty: -2,
      label: "IWM 205/210C • 7d • Credit 0.76",
      display: {
        combo_label: "IWM 205/210C • 7d • Credit 0.76",
        short_ul: "IWM",
        expiry_short: "Sep 6 '24",
      },
      mark_price: 0.74,
      mark_source: "MID" as const,
      mark_time: minutesAgoFromNow(1),
      greeks: {
        delta: 0.09,
        gamma: 0.01,
        theta: -0.4,
        vega: -1.8,
      },
      day_pnl_amount: 40,
      day_pnl_percent: 5.5,
      total_pnl_amount: 110,
      total_pnl_percent: 14.4,
      tp_band_pct: [0.5, 0.65],
      tp_band_low_pct: 0.5,
      tp_band_high_pct: 0.65,
      tp_hit: false,
      tp_done: false,
      sl_hit: false,
      progress_pct: 0.46,
      progress_pct_of_goal: 0.46,
      progress_pct_of_max: 0.46,
      progress: {
        pct_of_goal: 0.46,
      },
    },
    {
      id: "combo-rut-debit-near",
      strategy: "Call Debit Spread",
      underlying: "RUT",
      expiry: "2024-09-13",
      dte: 12,
      side: "debit" as const,
      net_premium: -2.4,
      net_price: -2.4,
      combo_group_id: "group-rut-debit-near",
      combo_qty: 2,
      label: "RUT 2005/2015C • 12d • Debit 2.40",
      display: {
        combo_label: "RUT 2005/2015C • 12d • Debit 2.40",
        short_ul: "RUT",
        expiry_short: "Sep 13 '24",
      },
      mark_price: -2.35,
      mark_source: "MID" as const,
      mark_time: minutesAgoFromNow(9),
      greeks: {
        delta: 0.07,
        gamma: 0.01,
        theta: -0.2,
        vega: 2.6,
      },
      day_pnl_amount: 55,
      day_pnl_percent: 2.4,
      total_pnl_amount: 180,
      total_pnl_percent: 8.1,
      tp_hit: false,
      tp_done: false,
      sl_hit: false,
      progress_pct: 0.95,
      progress_pct_of_goal: 0.95,
      progress_pct_of_max: 0.95,
      progress: {
        pct_of_goal: 0.95,
        pct_of_r: 0.95,
      },
    },
  ].map((combo) => ({
    ...combo,
    legs: baseLegs.filter((leg) => leg.combo_id === combo.id),
  }));

  const comboLookup = new Map(baseCombos.map((combo) => [combo.id, combo]));

  const buildGroupLegs = (groupId: string, staleSeconds: number) =>
    baseLegs
      .filter((leg) => leg.combo_group_id === groupId)
      .map((leg) => ({
        symbol: leg.symbol ?? leg.id ?? `${leg.underlying}-${leg.expiry}-${leg.right}-${leg.strike}`,
        underlying: leg.underlying,
        right: leg.right,
        strike: leg.strike,
        expiry: leg.expiry,
        quantity: leg.quantity,
        sum_greeks: {
          delta: leg.delta ?? 0,
          gamma: leg.gamma ?? 0,
          theta: leg.theta ?? 0,
          vega: leg.vega ?? 0,
        },
        mark: leg.mark_price ?? null,
        mark_source: leg.mark_source ?? "MID",
        stale_seconds: staleSeconds,
        combo_group_id: groupId,
        label: leg.label,
        display: leg.display,
      }));

  const zeroGreeks = { delta: 0, gamma: 0, theta: 0, vega: 0 } as OptionGreekSummary;

  const comboGroups: OptionComboGroupApi[] = [
    {
      combo_group_id: "group-iron-condor",
      strategy: "IRON_CONDOR",
      underlying: "SPX",
      group_qty: -10,
      group_net_price: 2.21,
      group_mark: 1.98,
      group_mark_price: 1.98,
      group_pnl_unrealized: 1850,
      dte: 32,
      sum_greeks: comboLookup.get("combo-iron-condor")?.greeks ?? zeroGreeks,
      mark_source: "MID" as const,
      stale_seconds: 180,
      tp_band_pct: [0.4, 0.6],
      tp_band_low_pct: 0.4,
      tp_band_high_pct: 0.6,
      tp_hit: true,
      tp_done: false,
      sl_hit: false,
      progress_pct: 0.62,
      progress_pct_of_goal: 0.62,
      progress: { pct_of_goal: 0.62 },
      label: comboLookup.get("combo-iron-condor")?.label ?? "SPX 4250/4300P + 4600/4650C • 32d • Credit 2.21",
      display: comboLookup.get("combo-iron-condor")?.display ?? null,
      legs: buildGroupLegs("group-iron-condor", 180),
    },
    {
      combo_group_id: "group-call-diagonal",
      strategy: "CALENDAR",
      underlying: "AAPL",
      group_qty: -5,
      group_net_price: -4.4,
      group_mark: 4.62,
      group_mark_price: 4.62,
      group_pnl_unrealized: 780,
      dte: 60,
      sum_greeks: comboLookup.get("combo-call-diagonal")?.greeks ?? zeroGreeks,
      mark_source: "LAST" as const,
      stale_seconds: 300,
      tp_hit: false,
      tp_done: false,
      sl_hit: false,
      progress_pct: 0.35,
      progress_pct_of_goal: 0.35,
      progress: { pct_of_goal: 0.35 },
      label: comboLookup.get("combo-call-diagonal")?.label ?? "AAPL 195C CAL • Sep→Nov • Debit 4.40",
      display: comboLookup.get("combo-call-diagonal")?.display ?? null,
      legs: buildGroupLegs("group-call-diagonal", 240),
    },
    {
      combo_group_id: "group-msft-put-vertical",
      strategy: "PUT_VERTICAL",
      underlying: "MSFT",
      group_qty: 3,
      group_net_price: -1.85,
      group_mark: -1.9,
      group_mark_price: -1.9,
      group_pnl_unrealized: 260,
      dte: 30,
      sum_greeks: comboLookup.get("combo-msft-put-vertical")?.greeks ?? zeroGreeks,
      mark_source: "MID" as const,
      stale_seconds: 240,
      tp_hit: false,
      tp_done: true,
      sl_hit: false,
      progress_pct: 1,
      progress_pct_of_goal: 1.0,
      progress: { pct_of_goal: 1.0 },
      label: comboLookup.get("combo-msft-put-vertical")?.label ?? "MSFT 330/325P • 30d • Debit 1.85",
      display: comboLookup.get("combo-msft-put-vertical")?.display ?? null,
      legs: buildGroupLegs("group-msft-put-vertical", 240),
    },
    {
      combo_group_id: "group-es-credit-stop",
      strategy: "IRON_CONDOR",
      underlying: "ES",
      group_qty: -4,
      group_net_price: 1.15,
      group_mark: 1.32,
      group_mark_price: 1.32,
      group_pnl_unrealized: 340,
      dte: 21,
      sum_greeks: comboLookup.get("combo-es-credit-stop")?.greeks ?? zeroGreeks,
      mark_source: "MID" as const,
      stale_seconds: 210,
      tp_band_pct: [0.35, 0.55],
      tp_band_low_pct: 0.35,
      tp_band_high_pct: 0.55,
      tp_hit: false,
      tp_done: false,
      sl_hit: true,
      progress_pct: 0.18,
      progress_pct_of_goal: 0.18,
      progress: { pct_of_goal: 0.18 },
      label: comboLookup.get("combo-es-credit-stop")?.label ?? "ES 4400/4425P + 4550/4575C • 21d • Credit 1.15",
      display: comboLookup.get("combo-es-credit-stop")?.display ?? null,
      legs: buildGroupLegs("group-es-credit-stop", 210),
    },
    {
      combo_group_id: "group-iwm-credit-near",
      strategy: "CALL_CREDIT_SPREAD",
      underlying: "IWM",
      group_qty: -2,
      group_net_price: 0.76,
      group_mark: 0.74,
      group_mark_price: 0.74,
      group_pnl_unrealized: 110,
      dte: 7,
      sum_greeks: comboLookup.get("combo-iwm-credit-near")?.greeks ?? zeroGreeks,
      mark_source: "MID" as const,
      stale_seconds: 90,
      tp_band_pct: [0.5, 0.65],
      tp_band_low_pct: 0.5,
      tp_band_high_pct: 0.65,
      tp_hit: false,
      tp_done: false,
      sl_hit: false,
      progress_pct: 0.46,
      progress_pct_of_goal: 0.46,
      progress: { pct_of_goal: 0.46 },
      label: comboLookup.get("combo-iwm-credit-near")?.label ?? "IWM 205/210C • 7d • Credit 0.76",
      display: comboLookup.get("combo-iwm-credit-near")?.display ?? null,
      legs: buildGroupLegs("group-iwm-credit-near", 90),
    },
    {
      combo_group_id: "group-rut-debit-near",
      strategy: "CALL_DEBIT_SPREAD",
      underlying: "RUT",
      group_qty: 2,
      group_net_price: -2.4,
      group_mark: -2.35,
      group_mark_price: -2.35,
      group_pnl_unrealized: 180,
      dte: 12,
      sum_greeks: comboLookup.get("combo-rut-debit-near")?.greeks ?? zeroGreeks,
      mark_source: "MID" as const,
      stale_seconds: 360,
      tp_hit: false,
      tp_done: false,
      sl_hit: false,
      progress_pct: 0.95,
      progress_pct_of_goal: 0.95,
      progress: { pct_of_goal: 0.95, pct_of_r: 0.95 },
      label: comboLookup.get("combo-rut-debit-near")?.label ?? "RUT 2005/2015C • 12d • Debit 2.40",
      display: comboLookup.get("combo-rut-debit-near")?.display ?? null,
      legs: buildGroupLegs("group-rut-debit-near", 360),
    },
  ];

  const base: OptionsApiResponse = {
    as_of: now.toISOString(),
    combos: baseCombos,
    legs: baseLegs,
    combo_groups: comboGroups,
  };

  return {
    as_of: overrides.as_of ?? base.as_of,
    combos: overrides.combos ?? base.combos,
    legs: overrides.legs ?? base.legs,
    combo_groups: overrides.combo_groups ?? base.combo_groups,
  };
};


export const buildStatsResponse = (
  overrides: Partial<PortfolioStatsApiResponse> = {},
): PortfolioStatsApiResponse => {
  const nowIso = new Date().toISOString();
  const baseSession: PortfolioStatsApiResponse["session"] = {
    exchange: "XNYS",
    tz: "America/New_York",
    state: "RTH",
    as_of: nowIso,
    source: "fallback",
    rth_open: nowIso,
    rth_close: nowIso,
  };
  const base: PortfolioStatsApiResponse = {
    equity_count: 24,
    option_legs_count: 68,
    combos_matched: 12,
    stale_quotes_count: 1,
    data_source: "internal",
    net_liq: 1_245_320.54,
    var95_1d_pct: 58_320.12,
    margin_used_pct: 0.37,
    updated_at: nowIso,
    session: baseSession,
    session_info: baseSession,
    meta: { latest_ts: nowIso },
  };

  const hasOwn = (key: keyof PortfolioStatsApiResponse) =>
    Object.prototype.hasOwnProperty.call(overrides, key);

  const pickMany = <K extends keyof PortfolioStatsApiResponse>(
    keys: readonly K[],
    fallback: PortfolioStatsApiResponse[K],
  ): PortfolioStatsApiResponse[K] => {
    for (const key of keys) {
      if (hasOwn(key)) {
        const value = overrides[key];
        if (value !== undefined) {
          return value;
        }
      }
    }
    return fallback;
  };

  const sessionValue = pickMany(["session"], base.session);
  const sessionInfoValue = pickMany(["session_info"], sessionValue);
  const metaOverride = overrides.meta;
  const metaValue =
    metaOverride === undefined
      ? base.meta
      : metaOverride === null
        ? null
        : { ...base.meta, ...metaOverride };

  return {
    equity_count: pickMany(["equity_count"], base.equity_count),
    option_legs_count: pickMany(["option_legs_count"], base.option_legs_count),
    combos_matched: pickMany(["combos_matched"], base.combos_matched),
    stale_quotes_count: pickMany(["stale_quotes_count"], base.stale_quotes_count),
    net_liq: pickMany(["net_liq", "netLiq"], base.net_liq),
    var95_1d_pct: pickMany(["var95_1d_pct", "var95", "var_95"], base.var95_1d_pct),
    margin_used_pct: pickMany([
      "margin_used_pct",
      "margin_pct",
      "marginPct",
    ], base.margin_used_pct),
    margin_pct: pickMany(["margin_pct", "marginPct"], base.margin_used_pct),
    updated_at: pickMany(["updated_at", "updatedAt"], base.updated_at),
    session: sessionValue,
    session_info: sessionInfoValue,
    meta: metaValue,
    data_source: pickMany(["data_source", "dataSource"], base.data_source ?? null),
  };
};

export const buildPsdSnapshot = (overrides: Partial<PSDSnapshot> = {}): PSDSnapshot => {
  const now = Date.now();
  const baseView = {
    single_stocks: [
      {
        secType: "STK" as const,
        symbol: "AAPL",
        qty: 120,
        avg_cost: 150,
        multiplier: 1,
        mark: 152.34,
        mark_source: "MID",
        price_source: "mid",
        stale_s: 25,
        pnl_intraday: 280.8,
        pnl_unrealized: 310.8,
        previous_close: 150.0,
        updated_at: new Date(now - 30_000).toISOString(),
        greeks: { delta: 120 },
        conId: 101,
      },
    ],
    option_combos: [
      {
        combo_id: "combo-aapl-call-spread",
        name: "AAPL CALL SPREAD",
        underlier: "AAPL",
        pnl_intraday: 420.0,
        greeks_agg: { delta: 0.22, gamma: 0.08, theta: -0.05 },
        legs: [
          {
            secType: "OPT" as const,
            symbol: "AAPL",
            qty: 1,
            avg_cost: 5,
            multiplier: 100,
            mark: 6.4,
            price_source: "mid",
            stale_s: 40,
            pnl_intraday: 140,
            greeks: { delta: 0.4, gamma: 0.02, theta: -0.08 },
            right: "CALL",
            strike: 180,
            expiry: "20240119",
            conId: 2001,
          },
          {
            secType: "OPT" as const,
            symbol: "AAPL",
            qty: -1,
            avg_cost: 3,
            multiplier: 100,
            mark: 2.2,
            price_source: "mid",
            stale_s: 44,
            pnl_intraday: 280,
            greeks: { delta: -0.18, gamma: -0.01, theta: -0.02 },
            right: "CALL",
            strike: 190,
            expiry: "20240119",
            conId: 2002,
          },
        ],
      },
    ],
    single_options: [
      {
        secType: "OPT" as const,
        symbol: "MSFT",
        qty: 1,
        avg_cost: 2,
        multiplier: 100,
        mark: 2.6,
        price_source: "mid",
        stale_s: 35,
        pnl_intraday: 60,
        greeks: { delta: -0.4, theta: -0.02 },
        right: "PUT",
        strike: 300,
        expiry: "20240216",
        conId: 3001,
      },
    ],
  } satisfies PSDSnapshot["positions_view"];

  const mergedView = {
    single_stocks: overrides.positions_view?.single_stocks ?? baseView.single_stocks,
    option_combos: overrides.positions_view?.option_combos ?? baseView.option_combos,
    single_options: overrides.positions_view?.single_options ?? baseView.single_options,
  };

  return {
    ts: overrides.ts ?? now,
    session: (overrides.session as PSDSnapshot["session"]) ?? "RTH",
    session_info:
      overrides.session_info ??
      ({
        exchange: "XNYS",
        tz: "America/New_York",
        state: "RTH",
        asOf: new Date(now).toISOString(),
        rthOpen: null,
        rthClose: null,
        source: "fallback",
        note: null,
      } satisfies PSDSnapshot["session_info"]),
    positions: overrides.positions ?? [],
    quotes: overrides.quotes ?? {},
    risk: overrides.risk ?? {},
    ...overrides,
    positions_view: mergedView,
  };
};

export const buildRulesSummaryResponse = (
  overrides: Partial<RulesSummaryFixture> = {},
): RulesSummaryFixture => {
  const now = new Date();
  const minutesAgoFromNow = (minutes: number) => minutesAgo(now, minutes);

  const top: RuleBreachFixture[] = [
    {
      id: "breach-portfolio-var",
      rule: "Portfolio VaR Limit",
      severity: "CRITICAL",
      subject: "Aggregate VaR",
      symbol: "SPX",
      occurred_at: minutesAgoFromNow(3),
      description: "Portfolio level VaR exceeded the configured 2.0% limit.",
      status: "OPEN",
    },
    {
      id: "breach-tsla-delta",
      rule: "Single Name Delta",
      severity: "CRITICAL",
      subject: "TSLA Delta Exposure",
      symbol: "TSLA",
      occurred_at: minutesAgoFromNow(5),
      description: "TSLA directional delta drifted beyond the configured band.",
      status: "OPEN",
    },
    {
      id: "breach-aapl-theta",
      rule: "Theta Budget",
      severity: "WARNING",
      subject: "AAPL Short Theta",
      symbol: "AAPL",
      occurred_at: minutesAgoFromNow(12),
      description: "Short theta pacing is outside plan for the overnight window.",
      status: "OPEN",
    },
    {
      id: "breach-msft-vol",
      rule: "Implied Vol Spike",
      severity: "WARNING",
      subject: "MSFT Earnings Run-up",
      symbol: "MSFT",
      occurred_at: minutesAgoFromNow(18),
      description: "MSFT implied volatility spiked ahead of next earnings.",
      status: "OPEN",
    },
    {
      id: "breach-gld-roll",
      rule: "Roll Reminder",
      severity: "INFO",
      subject: "GLD Hedge Roll",
      symbol: "GLD",
      occurred_at: minutesAgoFromNow(25),
      description: "Reminder to roll GLD hedge to maintain target duration.",
      status: "OPEN",
    },
  ];

  const breachesCounts: RulesSummaryCounters = {
    critical: top.filter((item) => item.severity === "CRITICAL").length,
    warning: top.filter((item) => item.severity === "WARNING").length,
    info: top.filter((item) => item.severity === "INFO").length,
  };

  const base: RulesSummaryFixture = {
    as_of: now.toISOString(),
    breaches: breachesCounts,
    top,
    focus_symbols: ["SPX", "TSLA", "AAPL", "MSFT", "GLD"],
    rules_total: overrides.rules_total ?? 32,
    evaluation_ms: overrides.evaluation_ms ?? 4.2,
    fundamentals: overrides.fundamentals ?? fundamentalsFixture,
  };

  return {
    as_of: overrides.as_of ?? base.as_of,
    breaches: overrides.breaches ?? base.breaches,
    top: overrides.top ?? base.top,
    focus_symbols: overrides.focus_symbols ?? base.focus_symbols,
    rules_total: overrides.rules_total ?? base.rules_total,
    evaluation_ms: overrides.evaluation_ms ?? base.evaluation_ms,
    fundamentals: overrides.fundamentals ?? base.fundamentals,
  };
};

export const buildRulesCatalogResponse = (
  overrides: Partial<RulesCatalogFixture> = {},
): RulesCatalogFixture => {
  const baseRules = overrides.rules ?? catalogState.rules;
  return {
    version: overrides.version ?? catalogState.version,
    updated_at: overrides.updated_at ?? catalogState.updated_at,
    updated_by: overrides.updated_by ?? catalogState.updated_by,
    rules: baseRules.map((rule) => ({ ...rule })),
  };
};

export const buildRulesCatalogValidationResponse = (
  overrides: Partial<RulesCatalogValidationFixture> = {},
): RulesCatalogValidationFixture => {
  const nowIso = new Date().toISOString();
  const counters: RulesSummaryCounters = {
    total: overrides.counters?.total ?? 5,
    critical: overrides.counters?.critical ?? 2,
    warning: overrides.counters?.warning ?? 2,
    info: overrides.counters?.info ?? 1,
  };
  const top: RuleBreachFixture[] =
    overrides.top ??
    [
      {
        id: "preview-portfolio-var",
        rule: "Portfolio VaR Limit",
        severity: "CRITICAL",
        subject: "Aggregate VaR",
        symbol: "SPX",
        occurred_at: nowIso,
        description: "Portfolio limit would remain triggered.",
        status: "OPEN",
      },
      {
        id: "preview-tsla-delta",
        rule: "Single Name Delta",
        severity: "CRITICAL",
        subject: "TSLA Delta Exposure",
        symbol: "TSLA",
        occurred_at: nowIso,
        description: "Delta drift still above threshold.",
        status: "OPEN",
      },
    ];
  const diff: CatalogDiffFixture =
    overrides.diff ??
    {
      added: [
        {
          rule_id: "combo__risk_budget",
          name: "Combo Risk Budget",
          severity: "WARNING",
          scope: "COMBO",
          expr: "risk_budget_pct > 0.5",
        },
      ],
      removed: [],
      changed: [
        {
          rule_id: "port__theta_negative",
          changes: {
            severity: { old: "INFO", new: "WARNING" },
            expr: { old: "net_theta_per_day < 0", new: "net_theta_per_day < -5" },
          },
        },
      ],
    };

  return {
    ok: overrides.ok ?? true,
    counters,
    top,
    errors: overrides.errors ?? [],
    diff,
  };
};

export const handlers = [
  http.get("*/state", () => HttpResponse.json(buildPsdSnapshot())),
  http.get("*/rules/catalog", () => HttpResponse.json(buildRulesCatalogResponse())),
  http.post("*/rules/validate", async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as { catalog_text?: string };
    if (!body.catalog_text || typeof body.catalog_text !== "string") {
      return HttpResponse.json(
        {
          ok: false,
          counters: { total: 0, critical: 0, warning: 0, info: 0 },
          top: [],
          errors: ["catalog_text is required"],
        },
        { status: 400 },
      );
    }
    const { diff, ...rest } = buildRulesCatalogValidationResponse();
    return HttpResponse.json(rest);
  }),
  http.post("*/rules/preview", async ({ request }) => {
    await request.json().catch(() => ({}));
    return HttpResponse.json(buildRulesCatalogValidationResponse());
  }),
  http.post("*/rules/publish", async ({ request }) => {
    const body = (await request.json().catch(() => ({}))) as { author?: string | null };
    const author = typeof body.author === "string" && body.author ? body.author : "ops-bot";
    catalogState = {
      ...catalogState,
      version: catalogState.version + 1,
      updated_at: new Date().toISOString(),
      updated_by: author,
    };
    return HttpResponse.json({
      version: catalogState.version,
      updated_at: catalogState.updated_at,
      updated_by: catalogState.updated_by,
    });
  }),
  http.post("*/rules/reload", () => HttpResponse.json(buildRulesCatalogResponse())),
  http.get("*/positions/stocks", () => HttpResponse.json(buildStocksResponse())),
  http.get("*/positions/options", () => HttpResponse.json(buildOptionsResponse())),
  http.get("*/stats", () => HttpResponse.json(buildStatsResponse())),
  http.get("*/rules/summary", () => HttpResponse.json(buildRulesSummaryResponse())),
  http.get("*/fundamentals.json", () => HttpResponse.json(fundamentalsFixture)),
];
