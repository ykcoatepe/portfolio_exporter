import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { MatchersV3, PactV3 } from "@pact-foundation/pact";

import { fetchRulesSummary } from "../../src/hooks/useRules";

const { datetime, eachLike, like, regex } = MatchersV3;

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const pactDir = path.resolve(__dirname, "../../pacts");

describe("contracts: /rules/summary", () => {
  const provider = new PactV3({
    consumer: "web-ui",
    provider: "psd-rules-service",
    dir: pactDir,
    logLevel: "warn",
    pactFileWriteMode: "overwrite",
  });

  it("generates a pact for fetching the rules summary", async () => {
    provider.addInteraction({
      state: "rules summary exists",
      uponReceiving: "a request for the rules summary",
      withRequest: {
        method: "GET",
        path: "/rules/summary",
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
          as_of: datetime("yyyy-MM-dd'T'HH:mm:ssxxx", "2024-10-18T14:10:00Z"),
          counters: like({
            total: like(5),
            critical: like(2),
            warning: like(2),
            info: like(1),
          }),
          focus_symbols: eachLike(like("TSLA"), 1),
          top: eachLike(
            {
              id: like("breach-portfolio-var"),
              rule: like("Portfolio VaR Limit"),
              severity: regex("critical|warning|info", "critical"),
              subject: like("Aggregate VaR"),
              symbol: like("SPX"),
              occurred_at: datetime("yyyy-MM-dd'T'HH:mm:ssxxx", "2024-10-18T14:05:00Z"),
              description: like("Portfolio level VaR exceeded the configured limit."),
            },
            1,
          ),
        }),
      },
    });

    await provider.executeTest(async (mockServer) => {
      const response = await fetchRulesSummary(mockServer.url);
      expect(response.as_of).toBeDefined();
      expect(response.counters.total).toBeGreaterThan(0);
      expect(Array.isArray(response.top)).toBe(true);
      expect(response.top.every((entry) => Boolean(entry.rule))).toBe(true);
      expect(response.top.every((entry) => ["critical", "warning", "info"].includes(entry.severity))).toBe(
        true,
      );
    });
  });
});
