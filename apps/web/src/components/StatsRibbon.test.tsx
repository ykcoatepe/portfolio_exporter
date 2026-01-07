import { act, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, test, vi } from "vitest";

import StatsRibbon from "./StatsRibbon";
import { buildPsdSnapshot, buildStatsResponse } from "../mocks/handlers";
import { server } from "../mocks/server";
import { renderWithClient } from "../test/queryClient";
import type { MarketSessionApiResponse } from "../lib/types";
import * as metricsModule from "../hooks/usePortfolioMetrics";

const buildSessionPayload = (
  state: "RTH" | "ETH" | "CLOSED",
  overrides: Partial<MarketSessionApiResponse> = {},
): MarketSessionApiResponse => ({
  exchange: overrides.exchange ?? "XNYS",
  tz: overrides.tz ?? "America/New_York",
  state,
  as_of: overrides.as_of ?? "2024-02-01T12:00:00-05:00",
  rth_open: overrides.rth_open ?? "2024-02-01T09:30:00-05:00",
  rth_close: overrides.rth_close ?? "2024-02-01T16:00:00-05:00",
  source: overrides.source ?? "fallback",
  note: overrides.note ?? null,
});

describe("StatsRibbon", () => {
  test("renders stats metrics from backend", async () => {
    const now = Date.parse("2024-02-01T12:00:00Z");
    const dateNowSpy = vi.spyOn(Date, "now").mockReturnValue(now);

    server.use(
      http.get("*/stats/current", () =>
        HttpResponse.json(
          buildStatsResponse({
            updated_at: new Date(now).toISOString(),
            staleness_sec: 45,
            session: buildSessionPayload("RTH"),
          }),
        ),
      ),
      http.get("*/stats", () =>
        HttpResponse.json(
          buildStatsResponse({
            updated_at: new Date(now).toISOString(),
            staleness_sec: 45,
            session: buildSessionPayload("RTH"),
          }),
        ),
      ),
      http.get("*/state", () => HttpResponse.json(buildPsdSnapshot())),
      http.get("*/session", () => HttpResponse.json(buildSessionPayload("RTH"))),
    );

    renderWithClient(<StatsRibbon />);

    const statsRegion = await screen.findByRole("region", { name: /portfolio stats/i });
    const valueFor = (label: string) => {
      const term = within(statsRegion).getByText(label, { selector: "dt" });
      const valueNode = term.parentElement?.querySelector(
        "dd[data-testid='stat-value']",
      ) as HTMLElement | null;
      expect(valueNode).not.toBeNull();
      return valueNode!.textContent?.trim();
    };

    await waitFor(() => {
      expect(valueFor("Day P&L")).toBe("$355.00");
    });
    expect(valueFor("Unrealized P&L")).toBe("$255.00");
    expect(valueFor("ΣΔ")).toBe("+15.10");
    expect(valueFor("ΣΘ / day")).toBe("-0.03");
    expect(valueFor("Net Liq")).toBe("$1,245,320.54");
    expect(valueFor("VaR 95%")).toBe("$58,320.12");
    expect(valueFor("Margin %")).toBe("37.00%");

    expect(screen.queryByTestId("stale-chip")).not.toBeInTheDocument();

    dateNowSpy.mockRestore();
  });

  test("falls back to snapshot timestamp when stats updated_at is missing", async () => {
    const snapshotSeconds = Math.floor(Date.parse("2024-02-01T12:00:00Z") / 1000);
    const nowMs = Date.parse("2024-02-01T12:07:00Z");
    const dateNowSpy = vi.spyOn(Date, "now").mockReturnValue(nowMs);

    server.use(
      http.get("*/stats/current", () =>
        HttpResponse.json(
          buildStatsResponse({
            updated_at: null,
            staleness_sec: 0,
            session: buildSessionPayload("RTH", { as_of: "2024-02-01T11:55:00Z" }),
          }),
        ),
      ),
      http.get("*/stats", () =>
        HttpResponse.json(
          buildStatsResponse({
            updated_at: null,
            staleness_sec: 0,
            session: buildSessionPayload("RTH", { as_of: "2024-02-01T11:55:00Z" }),
          }),
        ),
      ),
      http.get("*/state", () => HttpResponse.json(buildPsdSnapshot({ ts: snapshotSeconds }))),
      http.get("*/session", () =>
        HttpResponse.json(buildSessionPayload("RTH", { as_of: "2024-02-01T12:05:00Z" })),
      ),
    );

    renderWithClient(<StatsRibbon />);

    expect(await screen.findByText(/7 minutes ago/i)).toBeInTheDocument();

    dateNowSpy.mockRestore();
  });

  test("renders placeholders when stats fields are null", async () => {
    const now = Date.parse("2024-02-01T12:00:00Z");
    const dateNowSpy = vi.spyOn(Date, "now").mockReturnValue(now);
    const metricsSpy = vi
      .spyOn(metricsModule, "usePortfolioMetrics")
      .mockReturnValue({
        dayPnl: null,
        totalPnl: null,
        sumDelta: null,
        sumTheta: null,
        updatedAt: null,
        stalenessSeconds: null,
      });

    const emptySnapshot = buildPsdSnapshot({
      positions_view: {
        single_stocks: [],
        option_combos: [],
        single_options: [],
      },
      positions: [],
      quotes: {},
    });

    server.use(
      http.get("*/stats/current", () =>
        HttpResponse.json(
          buildStatsResponse({
            day_pnl: null,
            unrealized_pnl: null,
            sigma_total: null,
            sigma_per_day: null,
            net_liq: null,
            var_95: null,
            margin_pct: null,
            updated_at: null,
            staleness_sec: null,
            session: null,
            session_info: null,
            totals: {
              pnl_day: null,
              unrealized: null,
              sum_delta: null,
              sum_theta: null,
              staleness_secs: null,
            },
          }),
        ),
      ),
      http.get("*/stats", () =>
        HttpResponse.json(
          buildStatsResponse({
            day_pnl: null,
            unrealized_pnl: null,
            sigma_total: null,
            sigma_per_day: null,
            net_liq: null,
            var_95: null,
            margin_pct: null,
            updated_at: null,
            staleness_sec: null,
            session: null,
            session_info: null,
            totals: {
              pnl_day: null,
              unrealized: null,
              sum_delta: null,
              sum_theta: null,
              staleness_secs: null,
            },
          }),
        ),
      ),
      http.get("*/state", () => HttpResponse.json(emptySnapshot)),
      http.get("*/session", () =>
        HttpResponse.json(
          buildSessionPayload("RTH", { as_of: new Date(now).toISOString() }),
        ),
      ),
    );

    renderWithClient(<StatsRibbon />);

    const statsRegion = await screen.findByRole("region", { name: /portfolio stats/i });
    const valueFor = (label: string) => {
      const term = within(statsRegion).getByText(label, { selector: "dt" });
      const definition = term.parentElement?.querySelector(
        "dd[data-testid='stat-value']",
      ) as HTMLElement | null;
      expect(definition).not.toBeNull();
      return definition!.textContent?.trim();
    };

    expect(valueFor("Day P&L")).toBe("—");
    expect(valueFor("Unrealized P&L")).toBe("—");
    expect(valueFor("ΣΔ")).toBe("—");
    expect(valueFor("ΣΘ / day")).toBe("—");
    expect(valueFor("Net Liq")).toBe("—");
    expect(valueFor("VaR 95%")).toBe("—");
    expect(valueFor("Margin %")).toBe("—");
    await waitFor(() => {
      expect(valueFor("Updated")).toBe("now");
    });

    dateNowSpy.mockRestore();
    metricsSpy.mockRestore();
  });

  test("shows stale chip when stats are stale", async () => {
    server.use(
      http.get("*/stats/current", () =>
        HttpResponse.json(
          buildStatsResponse({
            staleness_sec: 7200,
            updated_at: "2024-02-01T10:00:00Z",
            session: buildSessionPayload("ETH"),
          }),
        ),
      ),
      http.get("*/stats", () =>
        HttpResponse.json(
          buildStatsResponse({
            staleness_sec: 7200,
            updated_at: "2024-02-01T10:00:00Z",
            session: buildSessionPayload("ETH"),
          }),
        ),
      ),
      http.get("*/state", () => HttpResponse.json(buildPsdSnapshot())),
      http.get("*/session", () => HttpResponse.json(buildSessionPayload("ETH"))),
    );

    renderWithClient(<StatsRibbon />);

    const chip = await screen.findByTestId("stale-chip");
    expect(chip).toHaveTextContent("STALE 2:00:00");
  });

  test("falls back to session endpoint when stats session is missing", async () => {
    server.use(
      http.get("*/stats/current", () =>
        HttpResponse.json(
          buildStatsResponse({
            session: null,
            session_info: null,
          }),
        ),
      ),
      http.get("*/stats", () =>
        HttpResponse.json(
          buildStatsResponse({
            session: null,
            session_info: null,
          }),
        ),
      ),
      http.get("*/state", () => HttpResponse.json(buildPsdSnapshot())),
      http.get("*/session", () =>
        HttpResponse.json(buildSessionPayload("ETH", { as_of: "2024-04-01T06:55:00Z" })),
      ),
    );

    renderWithClient(<StatsRibbon />);

    const sessionLabelNode = await screen.findByText(/SESSION: ETH/i);
    const sessionContainer = sessionLabelNode.parentElement as HTMLElement;
    expect(sessionContainer).not.toBeNull();
    expect(within(sessionContainer).getByText(/updated/i)).toBeInTheDocument();
  });
});
