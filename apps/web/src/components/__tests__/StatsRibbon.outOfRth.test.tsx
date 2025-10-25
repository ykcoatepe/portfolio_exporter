import { screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, test } from "vitest";

import StatsRibbon from "../StatsRibbon";
import { buildPsdSnapshot, buildStatsResponse } from "../../mocks/handlers";
import { server } from "../../mocks/server";
import { renderWithClient } from "../../test/queryClient";

const buildSession = () => ({
  exchange: "XNYS",
  tz: "America/New_York",
  state: "ETH",
  as_of: new Date(Date.now() - 60_000).toISOString(),
  rth_open: null,
  rth_close: null,
  source: "stats",
  note: null,
});

describe("StatsRibbon out of RTH", () => {
  test("shows stale data without hiding metrics", async () => {
    const updatedAt = new Date(Date.now() - 2 * 3_600_000).toISOString();
    const statsPayload = buildStatsResponse({
      day_pnl: 1_234.56,
      unrealized_pnl: 6_789.1,
      sigma_total: 24.2,
      sigma_per_day: -1.5,
      net_liq: 987_654.32,
      var_95: 45_678.9,
      margin_pct: 0.52,
      updated_at: updatedAt,
      staleness_sec: 7_200,
      session: buildSession(),
      session_info: null,
    });
    expect(statsPayload.session?.state).toBe("ETH");

    const snapshotFixture = buildPsdSnapshot();
    const view = snapshotFixture.positions_view;
    if (view) {
      for (const stock of view.single_stocks ?? []) {
        stock.stale_s = 7_200;
      }
      for (const combo of view.option_combos ?? []) {
        combo.pnl_intraday = combo.pnl_intraday ?? 0;
        for (const leg of combo.legs ?? []) {
          leg.stale_s = 7_200;
        }
      }
      for (const leg of view.single_options ?? []) {
        leg.stale_s = 7_200;
      }
    }

    server.use(
      http.get("*/stats/current", () => HttpResponse.json(statsPayload)),
      http.get("*/stats", () => HttpResponse.json(statsPayload)),
      http.get("*/state", () => HttpResponse.json(snapshotFixture)),
      http.get("*/session", () => HttpResponse.json(buildSession())),
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
      expect(valueFor("Day P&L")).not.toBe("—");
      expect(valueFor("Unrealized P&L")).not.toBe("—");
      expect(valueFor("ΣΔ")).not.toBe("—");
      expect(valueFor("ΣΘ / day")).not.toBe("—");
      expect(valueFor("Net Liq")).not.toBe("—");
    });

    const staleChip = await screen.findByTestId("stale-chip");
    expect(staleChip).toHaveTextContent("STALE 2:00:00");
    const sessionBadge = await screen.findByText(/SESSION:/i);
    expect(sessionBadge).toHaveTextContent("SESSION: ETH");
  });
});
