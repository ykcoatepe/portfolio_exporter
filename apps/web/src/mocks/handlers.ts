import { http, HttpResponse } from "msw";

import type {
  OptionsApiResponse,
  OptionComboLegApi,
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
  severity: "critical" | "warning" | "info";
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
    },
    {
      id: "leg-condor-long-call",
      combo_id: "combo-iron-condor",
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
    },
    {
      id: "leg-condor-short-put",
      combo_id: "combo-iron-condor",
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
    },
    {
      id: "leg-condor-long-put",
      combo_id: "combo-iron-condor",
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
    },
    {
      id: "leg-diagonal-long-call",
      combo_id: "combo-call-diagonal",
      underlying: "AAPL",
      expiry: "2024-11-15",
      strike: 195,
      right: "C",
      quantity: 5,
      mark_price: 7.65,
      mark_source: "LAST",
      mark_time: minutesAgoFromNow(6),
      delta: 0.38,
      gamma: 0.04,
      theta: -3.4,
      vega: 28.5,
      iv: 0.32,
      day_pnl_amount: 280,
      day_pnl_percent: 3.8,
      total_pnl_amount: 1040,
      total_pnl_percent: 12.6,
    },
    {
      id: "leg-diagonal-short-call",
      combo_id: "combo-call-diagonal",
      underlying: "AAPL",
      expiry: "2024-09-20",
      strike: 190,
      right: "C",
      quantity: -5,
      mark_price: 3.25,
      mark_source: "LAST",
      mark_time: minutesAgoFromNow(4),
      delta: -0.28,
      gamma: -0.03,
      theta: 4.1,
      vega: -22.1,
      iv: 0.29,
      day_pnl_amount: -90,
      day_pnl_percent: -2.7,
      total_pnl_amount: -260,
      total_pnl_percent: -6.3,
    },
    {
      id: "leg-orphan-put",
      combo_id: null,
      underlying: "TSLA",
      expiry: "2024-09-06",
      strike: 210,
      right: "P",
      quantity: 3,
      mark_price: 4.9,
      mark_source: "PREV",
      mark_time: minutesAgoFromNow(18),
      delta: -0.32,
      gamma: 0.02,
      theta: -2.1,
      vega: 14.3,
      iv: 0.41,
      day_pnl_amount: -35,
      day_pnl_percent: -1.9,
      total_pnl_amount: -128,
      total_pnl_percent: -8.2,
    },
    {
      id: "leg-orphan-call",
      combo_id: null,
      underlying: "MSFT",
      expiry: "2024-12-20",
      strike: 360,
      right: "C",
      quantity: -2,
      mark_price: 6.1,
      mark_source: "MID",
      mark_time: minutesAgoFromNow(12),
      delta: -0.18,
      gamma: 0.01,
      theta: 1.2,
      vega: -9.8,
      iv: 0.27,
      day_pnl_amount: 75,
      day_pnl_percent: 1.6,
      total_pnl_amount: 210,
      total_pnl_percent: 5.1,
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
    },
    {
      id: "combo-call-diagonal",
      strategy: "Call Diagonal",
      underlying: "AAPL",
      expiry: "2024-11-15",
      dte: 60,
      side: "debit" as const,
      net_premium: -4.4,
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
    },
  ].map((combo) => ({
    ...combo,
    legs: baseLegs.filter((leg) => leg.combo_id === combo.id),
  }));

  const base: OptionsApiResponse = {
    as_of: now.toISOString(),
    combos: baseCombos,
    legs: baseLegs,
  };

  return {
    as_of: overrides.as_of ?? base.as_of,
    combos: overrides.combos ?? base.combos,
    legs: overrides.legs ?? base.legs,
  };
};

export const buildStatsResponse = (
  overrides: Partial<PortfolioStatsApiResponse> = {},
): PortfolioStatsApiResponse => {
  const nowIso = new Date().toISOString();
  const base: PortfolioStatsApiResponse = {
    equity_count: 24,
    option_legs_count: 68,
    combos_matched: 12,
    stale_quotes_count: 1,
    net_liq: 1_245_320.54,
    var95_1d_pct: 58_320.12,
    margin_used_pct: 0.37,
    updated_at: nowIso,
  };

  return {
    equity_count: overrides.equity_count ?? base.equity_count,
    option_legs_count: overrides.option_legs_count ?? base.option_legs_count,
    combos_matched: overrides.combos_matched ?? base.combos_matched,
    stale_quotes_count: overrides.stale_quotes_count ?? base.stale_quotes_count,
    net_liq: overrides.net_liq ?? overrides.netLiq ?? base.net_liq,
    var95_1d_pct:
      overrides.var95_1d_pct ?? overrides.var95 ?? overrides.var_95 ?? base.var95_1d_pct,
    margin_used_pct:
      overrides.margin_used_pct ?? overrides.margin_pct ?? overrides.marginPct ?? base.margin_used_pct,
    margin_pct: overrides.margin_pct ?? overrides.marginPct ?? base.margin_used_pct,
    updated_at: overrides.updated_at ?? overrides.updatedAt ?? base.updated_at,
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
        price_source: "last",
        stale_s: 25,
        pnl_intraday: 280.8,
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
      severity: "critical",
      subject: "Aggregate VaR",
      symbol: "SPX",
      occurred_at: minutesAgoFromNow(3),
      description: "Portfolio level VaR exceeded the configured 2.0% limit.",
      status: "OPEN",
    },
    {
      id: "breach-tsla-delta",
      rule: "Single Name Delta",
      severity: "critical",
      subject: "TSLA Delta Exposure",
      symbol: "TSLA",
      occurred_at: minutesAgoFromNow(5),
      description: "TSLA directional delta drifted beyond the configured band.",
      status: "OPEN",
    },
    {
      id: "breach-aapl-theta",
      rule: "Theta Budget",
      severity: "warning",
      subject: "AAPL Short Theta",
      symbol: "AAPL",
      occurred_at: minutesAgoFromNow(12),
      description: "Short theta pacing is outside plan for the overnight window.",
      status: "OPEN",
    },
    {
      id: "breach-msft-vol",
      rule: "Implied Vol Spike",
      severity: "warning",
      subject: "MSFT Earnings Run-up",
      symbol: "MSFT",
      occurred_at: minutesAgoFromNow(18),
      description: "MSFT implied volatility spiked ahead of next earnings.",
      status: "OPEN",
    },
    {
      id: "breach-gld-roll",
      rule: "Roll Reminder",
      severity: "info",
      subject: "GLD Hedge Roll",
      symbol: "GLD",
      occurred_at: minutesAgoFromNow(25),
      description: "Reminder to roll GLD hedge to maintain target duration.",
      status: "OPEN",
    },
  ];

  const breachesCounts: RulesSummaryCounters = {
    critical: top.filter((item) => item.severity === "critical").length,
    warning: top.filter((item) => item.severity === "warning").length,
    info: top.filter((item) => item.severity === "info").length,
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
        severity: "critical",
        subject: "Aggregate VaR",
        symbol: "SPX",
        occurred_at: nowIso,
        description: "Portfolio limit would remain triggered.",
        status: "OPEN",
      },
      {
        id: "preview-tsla-delta",
        rule: "Single Name Delta",
        severity: "critical",
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
