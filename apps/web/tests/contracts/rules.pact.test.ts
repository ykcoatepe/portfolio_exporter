import path from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { MatchersV3, PactV3 } from "@pact-foundation/pact";

import { fetchRulesSummary } from "../../src/hooks/useRules";

const { atLeastLike, datetime, eachLike, like, regex } = MatchersV3;

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
          "Content-Type": "application/json; charset=utf-8",
        },
        body: like({
          as_of: datetime("yyyy-MM-dd'T'HH:mm:ssxxx", "2024-10-18T14:10:00Z"),
          breaches: like({
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
              severity: regex("CRITICAL|WARNING|INFO", "CRITICAL"),
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
      expect(response.breaches.total).toBeGreaterThan(0);
      expect(Array.isArray(response.top)).toBe(true);
      expect(response.top.every((entry) => Boolean(entry.rule))).toBe(true);
      expect(response.top.every((entry) => ["CRITICAL", "WARNING", "INFO"].includes(entry.severity))).toBe(
        true,
      );
    });
  });

  it("generates a pact for fetching the rules catalog", async () => {
    provider.addInteraction({
      state: "rules catalog exists",
      uponReceiving: "a request for the rules catalog",
      withRequest: {
        method: "GET",
        path: "/rules/catalog",
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
          version: like(12),
          updated_at: datetime("yyyy-MM-dd'T'HH:mm:ssxxx", "2024-10-18T14:00:00Z"),
          updated_by: like("ops-admin"),
          rules: eachLike(
            {
              rule_id: like("combo__annualized_premium_high"),
              name: like("Annualized premium >=30% within a week"),
              severity: like("CRITICAL"),
              scope: like("COMBO"),
              expr: like("annualized_premium_pct >= 30"),
            },
            1,
          ),
        }),
      },
    });

    await provider.executeTest(async (mockServer) => {
      const response = await fetch(`${mockServer.url}/rules/catalog`, {
        headers: { accept: "application/json" },
      });
      expect(response.status).toBe(200);
      const body = await response.json();
      expect(typeof body.version).toBe("number");
      expect(Array.isArray(body.rules)).toBe(true);
    });
  });

  it("generates a pact for validating catalog YAML", async () => {
    provider.addInteraction({
      state: "catalog validation succeeds",
      uponReceiving: "a request to validate catalog text",
      withRequest: {
        method: "POST",
        path: "/rules/validate",
        headers: {
          accept: "application/json",
          "Content-Type": "application/json",
        },
        body: like({ catalog_text: "rules: []" }),
      },
      willRespondWith: {
        status: 200,
        headers: {
          "Content-Type": "application/json; charset=utf-8",
        },
        body: like({
          ok: like(true),
          counters: like({ total: like(5), critical: like(2), warning: like(2), info: like(1) }),
          top: eachLike(
            {
              id: like("preview-portfolio-var"),
              rule: like("Portfolio VaR Limit"),
              severity: regex("CRITICAL|WARNING|INFO", "CRITICAL"),
              subject: like("Aggregate VaR"),
              symbol: like("SPX"),
              occurred_at: datetime("yyyy-MM-dd'T'HH:mm:ssxxx", "2024-10-18T14:05:00Z"),
              description: like("Portfolio limit would remain triggered."),
            },
            1,
          ),
          errors: like([]),
        }),
      },
    });

    await provider.executeTest(async (mockServer) => {
      const response = await fetch(`${mockServer.url}/rules/validate`, {
        method: "POST",
        headers: {
          accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ catalog_text: "rules: []" }),
      });
      expect(response.status).toBe(200);
      const body = await response.json();
      expect(body.ok).toBe(true);
      expect(Array.isArray(body.errors)).toBe(true);
    });
  });

  it("generates a pact for previewing catalog changes", async () => {
    provider.addInteraction({
      state: "catalog preview succeeds",
      uponReceiving: "a request to preview catalog changes",
      withRequest: {
        method: "POST",
        path: "/rules/preview",
        headers: {
          accept: "application/json",
          "Content-Type": "application/json",
        },
        body: like({ catalog_text: "rules: []" }),
      },
      willRespondWith: {
        status: 200,
        headers: {
          "Content-Type": "application/json; charset=utf-8",
        },
        body: like({
          ok: like(true),
          counters: like({ total: like(5), critical: like(2), warning: like(2), info: like(1) }),
          top: eachLike(
            {
              id: like("preview-portfolio-var"),
              rule: like("Portfolio VaR Limit"),
              severity: regex("CRITICAL|WARNING|INFO", "CRITICAL"),
              subject: like("Aggregate VaR"),
              symbol: like("SPX"),
              occurred_at: datetime("yyyy-MM-dd'T'HH:mm:ssxxx", "2024-10-18T14:05:00Z"),
              description: like("Portfolio limit would remain triggered."),
            },
            1,
          ),
          errors: like([]),
          diff: like({
            added: atLeastLike(
              {
                rule_id: like("combo__risk_budget"),
                severity: like("WARNING"),
              },
              0,
              1,
            ),
            changed: atLeastLike(
              {
                rule_id: like("port__theta_negative"),
                changes: like({ severity: like({ old: "INFO", new: "WARNING" }) }),
              },
              0,
              1,
            ),
            removed: atLeastLike(
              {
                rule_id: like("combo__old_rule"),
              },
              0,
              1,
            ),
          }),
        }),
      },
    });

    await provider.executeTest(async (mockServer) => {
      const response = await fetch(`${mockServer.url}/rules/preview`, {
        method: "POST",
        headers: {
          accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ catalog_text: "rules: []" }),
      });
      expect(response.status).toBe(200);
      const body = await response.json();
      expect(body.ok).toBe(true);
      expect(body.diff).toBeTruthy();
    });
  });

  it("generates a pact for publishing catalog changes", async () => {
    provider.addInteraction({
      state: "catalog publication succeeds",
      uponReceiving: "a request to publish catalog changes",
      withRequest: {
        method: "POST",
        path: "/rules/publish",
        headers: {
          accept: "application/json",
          "Content-Type": "application/json",
        },
        body: like({ catalog_text: "rules: []", author: like("ops-bot") }),
      },
      willRespondWith: {
        status: 200,
        headers: {
          "Content-Type": "application/json; charset=utf-8",
        },
        body: like({
          version: like(13),
          updated_at: datetime("yyyy-MM-dd'T'HH:mm:ssxxx", "2024-10-18T14:15:00Z"),
          updated_by: like("ops-bot"),
        }),
      },
    });

    await provider.executeTest(async (mockServer) => {
      const response = await fetch(`${mockServer.url}/rules/publish`, {
        method: "POST",
        headers: {
          accept: "application/json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ catalog_text: "rules: []", author: "ops-bot" }),
      });
      expect(response.status).toBe(200);
      const body = await response.json();
      expect(typeof body.version).toBe("number");
    });
  });

  it("generates a pact for reloading the catalog", async () => {
    provider.addInteraction({
      state: "catalog reload succeeds",
      uponReceiving: "a request to reload the catalog",
      withRequest: {
        method: "POST",
        path: "/rules/reload",
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
          version: like(12),
          updated_at: datetime("yyyy-MM-dd'T'HH:mm:ssxxx", "2024-10-18T14:00:00Z"),
          updated_by: like("ops-admin"),
          rules: eachLike(like({ rule_id: like("combo__annualized_premium_high") }), 1),
        }),
      },
    });

    await provider.executeTest(async (mockServer) => {
      const response = await fetch(`${mockServer.url}/rules/reload`, {
        method: "POST",
        headers: { accept: "application/json" },
      });
      expect(response.status).toBe(200);
    });
  });
});
