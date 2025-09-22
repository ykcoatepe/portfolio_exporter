import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, test, vi } from "vitest";

import StatsRibbon from "./StatsRibbon";
import { buildPsdSnapshot, buildStatsResponse } from "../mocks/handlers";
import { server } from "../mocks/server";
import { renderWithClient } from "../test/queryClient";
import type { MarketSessionApiResponse } from "../lib/types";

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
  test("normalizes PSD snapshot epoch seconds before computing recency", async () => {
    const snapshotSeconds = Math.floor(Date.parse("2024-02-01T12:00:00Z") / 1000);
    const nowMs = Date.parse("2024-02-01T12:07:00Z");
    const dateNowSpy = vi.spyOn(Date, "now").mockReturnValue(nowMs);

    server.use(
      http.get("*/stats", () =>
        HttpResponse.json(
          buildStatsResponse({
            net_liq: 1_000_000,
            var95_1d_pct: 50_000,
            margin_used_pct: 0.2,
            updated_at: "2024-02-01T11:59:00Z",
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

  test("renders placeholders for optional stats fields when data is absent", async () => {
    const snapshot = buildPsdSnapshot({
      ts: Date.parse("2024-03-01T15:00:00Z"),
    });

    server.use(
      http.get("*/stats", () =>
        HttpResponse.json(
          buildStatsResponse({
            net_liq: null,
            var95_1d_pct: null,
            margin_used_pct: null,
            updated_at: null,
            session: null,
          }),
        ),
      ),
      http.get("*/state", () => HttpResponse.json(snapshot)),
      http.get("*/session", () => HttpResponse.json(buildSessionPayload("RTH"))),
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

    expect(valueFor("Net Liq")).toBe("—");
    expect(valueFor("VaR 95%")).toBe("—");
    expect(valueFor("Margin %")).toBe("—");
    expect(valueFor("Updated")).toBe("—");
  });

  test.each([
    ["RTH", "2024-04-01T13:00:00Z"],
    ["ETH", "2024-04-01T06:00:00Z"],
    ["CLOSED", "2024-04-01T23:00:00Z"],
  ] as const)(
    "renders session state %s from the session endpoint",
    async (state, asOf) => {
      const now = Date.parse("2024-04-01T13:05:00Z");
      const dateNowSpy = vi.spyOn(Date, "now").mockReturnValue(now);

      server.use(
        http.get("*/stats", () =>
          HttpResponse.json(
            buildStatsResponse({
              session: null,
            }),
          ),
        ),
        http.get("*/state", () => HttpResponse.json(buildPsdSnapshot())),
        http.get("*/session", () =>
          HttpResponse.json(
            buildSessionPayload(state, {
              as_of: asOf,
              rth_open: "2024-04-01T09:30:00-04:00",
              rth_close: "2024-04-01T16:00:00-04:00",
            }),
          ),
        ),
      );

      renderWithClient(<StatsRibbon />);

      const sessionLabelNode = await screen.findByText(new RegExp(`SESSION: ${state}`));
      const sessionContainer = sessionLabelNode.parentElement as HTMLElement;
      expect(sessionContainer).not.toBeNull();
      expect(within(sessionContainer).getByText(/updated/i)).toBeInTheDocument();

      dateNowSpy.mockRestore();
    },
  );

  test("falls back to em dash when session endpoint fails", async () => {
    server.use(
      http.get("*/stats", () => HttpResponse.json(buildStatsResponse({ session: null }))),
      http.get("*/state", () => HttpResponse.json(buildPsdSnapshot())),
      http.get("*/session", () => HttpResponse.json(null, { status: 503 })),
    );

    renderWithClient(<StatsRibbon />);

    expect(await screen.findByText(/SESSION: —/i)).toBeInTheDocument();
  });
});
