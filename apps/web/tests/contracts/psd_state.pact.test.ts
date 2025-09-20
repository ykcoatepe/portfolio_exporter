import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { MatchersV3, PactV3 } from "@pact-foundation/pact";

import { fetchPsdSnapshot } from "../../src/hooks/usePsdSnapshot";

const { eachLike, like, decimal, regex } = MatchersV3;

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const pactDir = path.resolve(__dirname, "../../pacts");

describe("contracts: /state", () => {
  const provider = new PactV3({
    consumer: "web-ui",
    provider: "psd-api",
    dir: pactDir,
    logLevel: "warn",
    pactFileWriteMode: "overwrite",
  });

  it("generates a pact for fetching the PSD snapshot", async () => {
    provider.addInteraction({
      state: "PSD snapshot is available",
      uponReceiving: "a request for the PSD state snapshot",
      withRequest: {
        method: "GET",
        path: "/state",
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
          session: regex("RTH|EXT|CLOSED", "RTH"),
          ts: decimal(1_700_000_000),
          positions_view: {
            single_stocks: eachLike(
              {
                secType: regex("STK|OPT|FOP", "STK"),
                symbol: like("AAPL"),
                qty: decimal(120),
                avg_cost: decimal(150),
                multiplier: decimal(1),
                mark: decimal(152.34),
                price_source: like("last"),
                stale_s: decimal(25),
                pnl_intraday: decimal(280.8),
                greeks: like({
                  delta: decimal(120),
                }),
                conId: like(101),
              },
              1,
            ),
            option_combos: eachLike(
              {
                combo_id: like("combo-aapl-call-spread"),
                name: like("AAPL CALL SPREAD"),
                underlier: like("AAPL"),
                pnl_intraday: decimal(420),
                greeks_agg: like({
                  delta: decimal(0.22),
                  gamma: decimal(0.08),
                  theta: decimal(-0.05),
                }),
                legs: eachLike(
                  {
                    secType: regex("OPT|FOP", "OPT"),
                    symbol: like("AAPL"),
                    qty: decimal(1),
                    avg_cost: decimal(5),
                    multiplier: decimal(100),
                    mark: decimal(6.4),
                    price_source: like("mid"),
                    stale_s: decimal(40),
                    pnl_intraday: decimal(140),
                    greeks: like({
                      delta: decimal(0.4),
                      gamma: decimal(0.02),
                      theta: decimal(-0.08),
                    }),
                    right: regex("CALL|PUT", "CALL"),
                    strike: decimal(180),
                    expiry: like("20240119"),
                    conId: like(2001),
                  },
                  1,
                ),
              },
              1,
            ),
            single_options: eachLike(
              {
                secType: regex("OPT|FOP", "OPT"),
                symbol: like("MSFT"),
                qty: decimal(1),
                avg_cost: decimal(2),
                multiplier: decimal(100),
                mark: decimal(2.6),
                price_source: like("mid"),
                stale_s: decimal(35),
                pnl_intraday: decimal(60),
                greeks: like({
                  delta: decimal(-0.4),
                  theta: decimal(-0.02),
                }),
                right: regex("CALL|PUT", "PUT"),
                strike: decimal(300),
                expiry: like("20240216"),
                conId: like(3001),
              },
              1,
            ),
          },
        }),
      },
    });

    await provider.executeTest(async (mockServer) => {
      const snapshot = await fetchPsdSnapshot(mockServer.url);
      expect(snapshot.session).toBe("RTH");
      expect(snapshot.positions_view).toBeDefined();
      expect(snapshot.positions_view?.single_stocks?.length ?? 0).toBeGreaterThan(0);
      expect(snapshot.positions_view?.option_combos?.length ?? 0).toBeGreaterThan(0);
      expect(snapshot.positions_view?.single_options?.length ?? 0).toBeGreaterThan(0);
    });
  });
});
