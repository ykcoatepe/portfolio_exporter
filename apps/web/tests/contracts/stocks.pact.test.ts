import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { MatchersV3, PactV3 } from "@pact-foundation/pact";

import { fetchStocks } from "../../src/hooks/useStocks";

const { eachLike, like, decimal, regex, datetime } = MatchersV3;

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const pactDir = path.resolve(__dirname, "../../pacts");

describe("contracts: /positions/stocks", () => {
  const provider = new PactV3({
    consumer: "web-ui",
    provider: "positions-engine-api",
    dir: pactDir,
    logLevel: "warn",
    pactFileWriteMode: "overwrite",
  });

  it("generates a pact for fetching stock positions", async () => {
    provider.addInteraction({
      state: "stock positions exist",
      uponReceiving: "a request for stock positions",
      withRequest: {
        method: "GET",
        path: "/positions/stocks",
        headers: {
          accept: "application/json",
        },
      },
      willRespondWith: {
        status: 200,
        headers: {
          "Content-Type": regex("application/json;?.*", "application/json; charset=utf-8"),
        },
        body: like({
          data: eachLike({
            symbol: like("AAPL"),
            quantity: decimal(10.5),
            average_price: decimal(150.12),
            mark_price: decimal(151.42),
            mark_source: regex("MID|LAST|PREV", "MID"),
            mark_time: datetime("yyyy-MM-dd'T'HH:mm:ss.SSSxxx", "2024-08-21T14:05:00.000Z"),
            day_pnl_amount: decimal(125.98),
            day_pnl_percent: decimal(1.23),
            total_pnl_amount: decimal(512.78),
            total_pnl_percent: decimal(5.12),
            currency: like("USD"),
            exposure: decimal(1500.43),
          }, 1),
          as_of: datetime("yyyy-MM-dd'T'HH:mm:ss.SSSxxx", "2024-08-21T15:00:00.000Z"),
        }),
      },
    });

    await provider.executeTest(async (mockServer) => {
      const rows = await fetchStocks(mockServer.url);
      expect(Array.isArray(rows)).toBe(true);
      expect(rows.length).toBeGreaterThan(0);
      expect(rows[0]).toMatchObject({
        symbol: "AAPL",
        currency: "USD",
      });
    });
  });
});
