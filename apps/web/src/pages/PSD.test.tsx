import { screen, waitFor, within } from "@testing-library/react";
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
    const nowMs = Date.parse("2024-01-01T12:00:00Z");
    const dateNowSpy = vi.spyOn(Date, "now").mockReturnValue(nowMs);

    const statsFixture = buildStatsResponse({
      net_liq: 1_245_320.54,
      var_95: 58_320.12,
      margin_pct: 0.45,
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
                symbol: "TSLA 20240119C00250000",
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
                symbol: "TSLA 20240119C00260000",
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
            symbol: "MSFT 20240216P00290000",
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
      http.get("*/stats/current", () => HttpResponse.json(statsFixture)),
      http.get("*/stats", () => HttpResponse.json(statsFixture)),
      http.get("*/state", () => HttpResponse.json(snapshotFixture)),
    );

    renderWithClient(<PSDPage />);

    const statsRegion = await screen.findByRole("region", { name: /portfolio stats/i });

    const valueFor = (label: string) => {
      const term = within(statsRegion).getByText(label, { selector: "dt" });
      const definition = term.parentElement?.querySelector(
        "dd[data-testid='stat-value']",
      ) as HTMLElement | null;
      expect(definition).not.toBeNull();
      return definition!.textContent?.trim();
    };

    await waitFor(() => {
      expect(valueFor("Day P&L")).toBe("$355.00");
      expect(valueFor("Unrealized P&L")).toBe("$255.00");
      expect(valueFor("ΣΔ")).toBe("+15.10");
      expect(valueFor("ΣΘ / day")).toBe("-0.03");
      expect(valueFor("Net Liq")).toBe("$1,245,320.54");
      const varValue = valueFor("VaR 95%");
      expect(varValue).toBe("$58,320.12");
      expect(valueFor("Margin %")).toBe("45.00%");
      expect(valueFor("Updated")).toBe("now");
    });

    dateNowSpy.mockRestore();

    const expectAlignClass = (element: HTMLElement | null, align: "left" | "right") => {
      expect(element).not.toBeNull();
      const className = align === "right" ? "text-right" : "text-left";
      expect(element as HTMLElement).toHaveClass(className);
    };

    const stocksSection = await screen.findByRole("region", { name: /Single Stocks/i });
    const stocksGrid = within(stocksSection).getByRole("grid", { name: /Single Stocks/i });
    expect(stocksGrid).toBeInTheDocument();
    expect(within(stocksSection).getByText("TSLA")).toBeInTheDocument();
    expect(within(stocksSection).getByText("$75.00")).toBeInTheDocument();

    expectAlignClass(within(stocksGrid).getByRole("columnheader", { name: "Symbol" }), "left");
    expectAlignClass(within(stocksGrid).getByRole("columnheader", { name: "Qty" }), "right");
    expectAlignClass(within(stocksGrid).getByRole("columnheader", { name: "Mark" }), "right");
    expectAlignClass(within(stocksGrid).getByRole("columnheader", { name: "Source" }), "left");

    const stockRowHeader = within(stocksGrid).getByRole("rowheader", { name: /TSLA/i });
    expectAlignClass(stockRowHeader, "left");
    expectAlignClass(within(stocksGrid).getByText("+15").closest("td"), "right");
    expectAlignClass(within(stocksGrid).getByText("$215.00").closest("td"), "right");
    expectAlignClass(within(stocksGrid).getByText("LAST").closest("td"), "left");
    expectAlignClass(within(stocksGrid).getByText("00:12").closest("td"), "right");

    const combosSection = await screen.findByRole("region", { name: /Options — Combos/i });
    const comboToggle = within(combosSection).getByRole("button", { name: /TSLA CALL SPREAD/i });
    expect(comboToggle).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(comboToggle);

    const osiPattern = /\d{6,8}[CP]\d{8}/;
    const legsGrid = await within(combosSection).findByRole("grid", { name: /TSLA CALL SPREAD legs/i });
    expect(within(legsGrid).getAllByRole("row").length).toBeGreaterThan(1);
    const comboRowHeader = within(legsGrid).getAllByRole("rowheader")[0];
    const comboLabelSpan = comboRowHeader.querySelector("span");
    expect(comboLabelSpan).not.toBeNull();
    expect(comboRowHeader.textContent).toMatch(/TSLA 250C/i);
    expect(comboRowHeader.textContent).not.toMatch(osiPattern);
    expect(comboLabelSpan?.getAttribute("title")).toMatch(osiPattern);

    expectAlignClass(within(legsGrid).getByRole("columnheader", { name: "Symbol" }), "left");
    expectAlignClass(within(legsGrid).getByRole("columnheader", { name: "Qty" }), "right");
    expectAlignClass(within(legsGrid).getByRole("columnheader", { name: "Source" }), "left");

    expectAlignClass(comboRowHeader, "left");
    expectAlignClass(within(legsGrid).getByText("+1").closest("td"), "right");
    expectAlignClass(within(legsGrid).getAllByText("MID")[0].closest("td"), "left");

    const singlesSection = await screen.findByRole("region", { name: /Options — Singles/i });
    const singlesGrid = within(singlesSection).getByRole("grid", { name: /Options — Singles/i });
    const singleRowHeader = within(singlesGrid).getAllByRole("rowheader")[0];
    const singleLabelSpan = singleRowHeader.querySelector("span");
    expect(singleLabelSpan).not.toBeNull();
    expect(singleRowHeader.textContent).toMatch(/MSFT 290P/i);
    expect(singleRowHeader.textContent).not.toMatch(osiPattern);
    expect(singleLabelSpan?.getAttribute("title")).toMatch(osiPattern);

    expectAlignClass(within(singlesGrid).getByRole("columnheader", { name: "Symbol" }), "left");
    expectAlignClass(within(singlesGrid).getByRole("columnheader", { name: "Qty" }), "right");
    expectAlignClass(within(singlesGrid).getByRole("columnheader", { name: "Source" }), "left");

    expectAlignClass(singleRowHeader, "left");
    expectAlignClass(within(singlesGrid).getByText("-1").closest("td"), "right");
    expectAlignClass(within(singlesGrid).getByText("MID").closest("td"), "left");
  });

  test("tabs through ribbon into fallback stocks table", async () => {
    const statsFixture = buildStatsResponse();
    const fallbackSnapshot = buildPsdSnapshot();
    // Remove positions_view so the page renders legacy tables.
    delete (fallbackSnapshot as Record<string, unknown>).positions_view;

    server.use(
      http.get("*/stats/current", () => HttpResponse.json(statsFixture)),
      http.get("*/stats", () => HttpResponse.json(statsFixture)),
      http.get("*/state", () => HttpResponse.json(fallbackSnapshot)),
    );

    const user = userEvent.setup();

    renderWithClient(<PSDPage />);

    const statsRegion = await screen.findByRole("region", { name: /portfolio stats/i });
    await screen.findByRole("region", { name: /MSB hedge actions/i });
    const exportCsvLink = await screen.findByText(/export msb \(csv\)/i, {
      selector: "a",
    });
    const exportParquetLink = await screen.findByText(/export msb \(parquet\)/i, {
      selector: "a",
    });

    statsRegion.focus();
    expect(statsRegion).toHaveFocus();

    await user.tab();
    const msb7dToggle = await screen.findByRole("button", { name: "7D" });
    expect(msb7dToggle).toHaveFocus();

    await user.tab();
    const msb1yToggle = await screen.findByRole("button", { name: "1Y" });
    expect(msb1yToggle).toHaveFocus();

    await user.tab();
    expect(exportCsvLink).toHaveFocus();

    await user.tab();
    expect(exportParquetLink).toHaveFocus();

    await user.tab();
    const filter = await screen.findByRole("searchbox", { name: /filter symbols/i });
    expect(filter).toHaveFocus();

    await user.tab();
    const sortButton = await screen.findByRole("button", { name: /day p&l/i });
    expect(sortButton).toHaveFocus();

    await user.tab();
    const stocksGrid = await screen.findByRole("grid", { name: /single stocks positions/i });
    const rows = within(stocksGrid).getAllByRole("row");
    expect(rows.length).toBeGreaterThan(1);
    const clearFilters = within(rows[1]).getByRole("button", { name: /clear filters/i });
    expect(clearFilters).toHaveFocus();
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

    renderWithClient(<PSDPage />);

    const comboToggle = await screen.findByRole("button", { name: /TSLA CALL SPREAD/i });
    const user = userEvent.setup();

    comboToggle.focus();
    await user.keyboard("{Enter}");

    expect(await screen.findByRole("grid", { name: /TSLA CALL SPREAD legs/i })).toBeInTheDocument();
  });
});
