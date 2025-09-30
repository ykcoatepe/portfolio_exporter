import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { MatchersV3, PactV3 } from "@pact-foundation/pact";

import { fetchOptions } from "../../src/hooks/useOptions";

const { eachLike, like, decimal, regex, datetime, nullValue } = MatchersV3;

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const pactDir = path.resolve(__dirname, "../../pacts");

describe("contracts: /positions/options", () => {
  const provider = new PactV3({
    consumer: "web-ui",
    provider: "positions-engine-api",
    dir: pactDir,
    logLevel: "warn",
    pactFileWriteMode: "overwrite",
  });

  it("generates a pact for fetching option combos and legs", async () => {
    provider.addInteraction({
      state: "option positions exist",
      uponReceiving: "a request for option combos and legs",
      withRequest: {
        method: "GET",
        path: "/positions/options",
        headers: {
          accept: "application/json",
        },
      },
      willRespondWith: {
        status: 200,
        headers: {
          "Content-Type": "application/json; charset=utf-8",
        },
        body: like({
          combos: eachLike({
            id: like("combo-iron-condor"),
            strategy: like("Iron Condor"),
            underlying: like("SPX"),
            expiry: regex("\\d{4}-\\d{2}-\\d{2}", "2024-10-18"),
            dte: decimal(32),
            side: regex("credit|debit", "credit"),
            net_premium: decimal(2.21),
            net_price: decimal(2.21),
            mark_price: decimal(1.98),
            mark_source: regex("MID|LAST|PREV", "MID"),
            mark_time: datetime("yyyy-MM-dd'T'HH:mm:ss.SSSxxx", "2024-10-18T14:02:00.000Z"),
            greeks: like({
              delta: decimal(-0.04),
              gamma: decimal(0.01),
              theta: decimal(-5.4),
              vega: decimal(-20.3),
            }),
            day_pnl_amount: decimal(700),
            day_pnl_percent: decimal(11.2),
            total_pnl_amount: decimal(1850),
            total_pnl_percent: decimal(24.8),
            progress_pct: decimal(0.62),
            progress_pct_of_goal: decimal(0.62),
            progress_pct_of_max: decimal(0.62),
            progress: like({
              pct_of_goal: decimal(0.62),
            }),
            combo_group_id: like("group-iron-condor"),
            combo_qty: decimal(-10),
            label: like("SPX 4250/4300P + 4600/4650C • 32d • Credit 2.21"),
            display: like({
              combo_label: like("SPX 4250/4300P + 4600/4650C • 32d • Credit 2.21"),
              short_ul: like("SPX"),
              expiry_short: like("Oct 18 '24"),
            }),
            legs: eachLike({
              id: like("leg-condor-short-call"),
              combo_id: like("combo-iron-condor"),
              combo_group_id: like("group-iron-condor"),
              symbol: like("SPX  20241018C00460000"),
              underlying: like("SPX"),
              expiry: regex("\\d{4}-\\d{2}-\\d{2}", "2024-10-18"),
              strike: decimal(4600),
              right: regex("C|P", "C"),
              quantity: decimal(-10),
              mark_price: decimal(1.05),
              mark_source: regex("MID|LAST|PREV", "MID"),
              mark_time: datetime("yyyy-MM-dd'T'HH:mm:ss.SSSxxx", "2024-10-18T14:02:00.000Z"),
              delta: decimal(0.12),
              gamma: decimal(0.01),
              theta: decimal(-4.2),
              vega: decimal(-18.5),
              iv: decimal(0.19),
              day_pnl_amount: decimal(480),
              day_pnl_percent: decimal(12.4),
              total_pnl_amount: decimal(1240),
              total_pnl_percent: decimal(18.1),
              label: like("SPX 4600C • Oct 18 '24"),
              display: like({
                leg_label: like("SPX 4600C • Oct 18 '24"),
                short_ul: like("SPX"),
                expiry_short: like("Oct 18 '24"),
              }),
            }, 1),
          }, 1),
          combo_groups: eachLike({
            combo_group_id: like("group-iron-condor"),
            strategy: like("IRON_CONDOR"),
            underlying: like("SPX"),
            group_qty: decimal(-10),
            group_net_price: decimal(2.21),
            dte: decimal(32),
            sum_greeks: like({
              delta: decimal(-0.04),
              gamma: decimal(0.01),
              theta: decimal(-5.4),
              vega: decimal(-20.3),
            }),
            mark_source: regex("MID|LAST|PREV", "MID"),
            stale_seconds: decimal(180),
            progress_pct: decimal(0.62),
            progress_pct_of_goal: decimal(0.62),
            progress: like({
              pct_of_goal: decimal(0.62),
            }),
            label: like("SPX 4250/4300P + 4600/4650C • 32d • Credit 2.21"),
            display: like({
              combo_label: like("SPX 4250/4300P + 4600/4650C • 32d • Credit 2.21"),
              short_ul: like("SPX"),
              expiry_short: like("Oct 18 '24"),
            }),
            legs: eachLike({
              symbol: like("SPX  20241018C00460000"),
              underlying: like("SPX"),
              right: regex("C|P", "C"),
              strike: decimal(4600),
              expiry: regex("\\d{4}-\\d{2}-\\d{2}", "2024-10-18"),
              quantity: decimal(-10),
              sum_greeks: like({
                delta: decimal(0.12),
                gamma: decimal(0.01),
                theta: decimal(-4.2),
                vega: decimal(-18.5),
              }),
              mark: decimal(1.05),
              mark_source: regex("MID|LAST|PREV", "MID"),
              stale_seconds: decimal(180),
              combo_group_id: like("group-iron-condor"),
              label: like("SPX 4600C • Oct 18 '24"),
              display: like({
                leg_label: like("SPX 4600C • Oct 18 '24"),
                short_ul: like("SPX"),
                expiry_short: like("Oct 18 '24"),
              }),
            }, 1),
          }, 1),
          legs: eachLike({
            id: like("leg-orphan"),
            combo_id: nullValue(),
            combo_group_id: nullValue(),
            symbol: like("MSFT20241220C00360000"),
            underlying: like("MSFT"),
            expiry: regex("\\d{4}-\\d{2}-\\d{2}", "2024-12-20"),
            strike: decimal(360),
            right: regex("C|P", "C"),
            quantity: decimal(-2),
            mark_price: decimal(6.1),
            mark_source: regex("MID|LAST|PREV", "MID"),
            mark_time: datetime("yyyy-MM-dd'T'HH:mm:ss.SSSxxx", "2024-12-20T14:12:00.000Z"),
            delta: decimal(-0.18),
            gamma: decimal(0.01),
            theta: decimal(1.2),
            vega: decimal(-9.8),
            iv: decimal(0.27),
            day_pnl_amount: decimal(75),
            day_pnl_percent: decimal(1.6),
            total_pnl_amount: decimal(210),
            total_pnl_percent: decimal(5.1),
            label: like("MSFT 360C • Dec 20 '24"),
            display: like({
              leg_label: like("MSFT 360C • Dec 20 '24"),
              short_ul: like("MSFT"),
              expiry_short: like("Dec 20 '24"),
            }),
          }, 1),
          as_of: datetime("yyyy-MM-dd'T'HH:mm:ss.SSSxxx", "2024-10-18T14:05:00.000Z"),
        }),
      },
    });

    await provider.executeTest(async (mockServer) => {
      const payload = await fetchOptions(mockServer.url);
      expect(Array.isArray(payload.combos)).toBe(true);
      expect(Array.isArray(payload.legs)).toBe(true);
      expect(payload.combos.length).toBeGreaterThan(0);
      expect(payload.legs.length).toBeGreaterThan(0);
    });
  });
});
