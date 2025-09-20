import { act, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import PSDPage from "./PSD";
import { buildPsdSnapshot, buildStatsResponse } from "../mocks/handlers";
import { server } from "../mocks/server";
import { renderWithClient } from "../test/queryClient";

describe("PSD page", () => {
  beforeEach(() => {
    vi.useRealTimers();
    vi.setSystemTime(new Date("2024-01-01T12:00:00Z"));
  });

  afterEach(() => {
    vi.setSystemTime(new Date());
    vi.useRealTimers();
  });

  test("renders positions view sections and ribbon metrics", async () => {
    const statsFixture = buildStatsResponse({
      net_liq: 1_245_320.54,
      var95_1d_pct: 58_320.12,
      margin_used_pct: 0.45,
      updated_at: "2024-01-01T12:00:00Z",
    });

    const snapshotFixture = buildPsdSnapshot({
      ts: Date.parse("2024-01-01T12:00:00Z"),
      positions_view: {
        single_stocks: [
          {
            secType: "STK",
            symbol: "TSLA",
            qty: 15,
            avg_cost: 210,
            multiplier: 1,
            mark: 215,
            price_source: "last",
            stale_s: 12,
            pnl_intraday: 75,
            greeks: { delta: 15 },
            conId: 8001,
          },
        ],
        option_combos: [
          {
            combo_id: "combo-tsla-call",
            name: "TSLA CALL SPREAD",
            underlier: "TSLA",
            pnl_intraday: 250,
            greeks_agg: { delta: 0.3, gamma: 0.05, theta: -0.02 },
            legs: [
              {
                secType: "OPT",
                symbol: "TSLA",
                qty: 1,
                avg_cost: 4,
                multiplier: 100,
                mark: 5,
                price_source: "mid",
                stale_s: 50,
                pnl_intraday: 100,
                greeks: { delta: 0.4, gamma: 0.02, theta: -0.01 },
                right: "CALL",
                strike: 250,
                expiry: "20240119",
                conId: 8101,
              },
              {
                secType: "OPT",
                symbol: "TSLA",
                qty: -1,
                avg_cost: 1,
                multiplier: 100,
                mark: 0.5,
                price_source: "mid",
                stale_s: 52,
                pnl_intraday: 150,
                greeks: { delta: -0.1, gamma: -0.01, theta: -0.01 },
                right: "CALL",
                strike: 260,
                expiry: "20240119",
                conId: 8102,
              },
            ],
          },
        ],
        single_options: [
          {
            secType: "OPT",
            symbol: "MSFT",
            qty: -1,
            avg_cost: 1.5,
            multiplier: 100,
            mark: 1.2,
            price_source: "mid",
            stale_s: 45,
            pnl_intraday: 30,
            greeks: { delta: -0.2, theta: -0.01 },
            right: "PUT",
            strike: 290,
            expiry: "20240216",
            conId: 8201,
          },
        ],
      },
    });

    server.use(
      http.get("*/stats", () => HttpResponse.json(statsFixture)),
      http.get("*/state", () => HttpResponse.json(snapshotFixture)),
    );

    await act(async () => {
      renderWithClient(<PSDPage />);
    });

    const statsRegion = await screen.findByRole("region", { name: /portfolio stats/i });

    const valueFor = (label: string) => {
      const term = within(statsRegion).getByText(label, { selector: "dt" });
      const definition = term.parentElement?.querySelector(
        "dd[data-testid='stat-value']",
      ) as HTMLElement | null;
      expect(definition).not.toBeNull();
      return definition!.textContent?.trim();
    };

    expect(valueFor("Day P&L")).toBe("$355.00");
    expect(valueFor("Unrealized P&L")).toBe("$255.00");
    expect(valueFor("ΣΔ")).toBe("+15.10");
    expect(valueFor("ΣΘ / day")).toBe("-0.03");
    expect(valueFor("Net Liq")).toBe("$1,245,320.54");
    const varValue = valueFor("VaR 95%");
    expect(varValue).toBe("$58,320.12");
    expect(valueFor("Margin %")).toBe("45.00%");
    expect(valueFor("Updated")).toBe("now");

    const stocksSection = await screen.findByRole("region", { name: /Single Stocks/i });
    expect(within(stocksSection).getByRole("grid", { name: /Single Stocks/i })).toBeInTheDocument();
    expect(within(stocksSection).getByText("TSLA")).toBeInTheDocument();
    expect(within(stocksSection).getByText("$75.00")).toBeInTheDocument();

    const combosSection = await screen.findByRole("region", { name: /Options — Combos/i });
    const comboToggle = within(combosSection).getByRole("button", { name: /TSLA CALL SPREAD/i });
    expect(comboToggle).toBeInTheDocument();

    const user = userEvent.setup();
    await act(async () => {
      await user.click(comboToggle);
    });

    const legsGrid = await within(combosSection).findByRole("grid", { name: /TSLA CALL SPREAD legs/i });
    expect(within(legsGrid).getAllByRole("row").length).toBeGreaterThan(1);

    const singlesSection = await screen.findByRole("region", { name: /Options — Singles/i });
    expect(within(singlesSection).getByRole("grid", { name: /Options — Singles/i })).toBeInTheDocument();
    expect(within(singlesSection).getByText("MSFT")).toBeInTheDocument();
  });

  test("tabs through ribbon into fallback stocks table", async () => {
    const statsFixture = buildStatsResponse();
    const fallbackSnapshot = buildPsdSnapshot();
    // Remove positions_view so the page renders legacy tables.
    delete (fallbackSnapshot as Record<string, unknown>).positions_view;

    server.use(
      http.get("*/stats", () => HttpResponse.json(statsFixture)),
      http.get("*/state", () => HttpResponse.json(fallbackSnapshot)),
    );

    const user = userEvent.setup();

    await act(async () => {
      renderWithClient(<PSDPage />);
    });

    const statsRegion = await screen.findByRole("region", { name: /portfolio stats/i });
    statsRegion.focus();
    expect(statsRegion).toHaveFocus();

    await act(async () => {
      await user.tab();
    });
    const filter = await screen.findByRole("searchbox", { name: /filter symbols/i });
    expect(filter).toHaveFocus();

    await act(async () => {
      await user.tab();
    });
    const sortButton = await screen.findByRole("button", { name: /day p&l/i });
    expect(sortButton).toHaveFocus();

    await act(async () => {
      await user.tab();
    });
    const stocksGrid = await screen.findByRole("grid", { name: /single stocks positions/i });
    const rows = within(stocksGrid).getAllByRole("row");
    expect(rows.length).toBeGreaterThan(1);
    expect(rows[1]).toHaveFocus();
  });

  test("expands combo legs with keyboard control", async () => {
    const snapshotFixture = buildPsdSnapshot({
      positions_view: {
        single_stocks: [],
        option_combos: [
          {
            combo_id: "combo-tsla-call",
            name: "TSLA CALL SPREAD",
            underlier: "TSLA",
            pnl_intraday: 250,
            greeks_agg: { delta: 0.3 },
            legs: [
              {
                secType: "OPT",
                symbol: "TSLA",
                qty: 1,
                avg_cost: 4,
                multiplier: 100,
                mark: 5,
                price_source: "mid",
                stale_s: 30,
                pnl_intraday: 100,
                greeks: { delta: 0.4 },
                right: "CALL",
                strike: 250,
                expiry: "20240119",
                conId: 9101,
              },
              {
                secType: "OPT",
                symbol: "TSLA",
                qty: -1,
                avg_cost: 2,
                multiplier: 100,
                mark: 1.5,
                price_source: "mid",
                stale_s: 32,
                pnl_intraday: 150,
                greeks: { delta: -0.1 },
                right: "CALL",
                strike: 260,
                expiry: "20240119",
                conId: 9102,
              },
            ],
          },
        ],
        single_options: [],
      },
    });

    server.use(http.get("*/state", () => HttpResponse.json(snapshotFixture)));

    await act(async () => {
      renderWithClient(<PSDPage />);
    });

    const comboToggle = await screen.findByRole("button", { name: /TSLA CALL SPREAD/i });
    const user = userEvent.setup();

    comboToggle.focus();
    await act(async () => {
      await user.keyboard("{Enter}");
    });

    expect(await screen.findByRole("grid", { name: /TSLA CALL SPREAD legs/i })).toBeInTheDocument();
  });
});
