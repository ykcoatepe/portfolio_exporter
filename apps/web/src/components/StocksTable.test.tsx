import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, afterEach, describe, expect, test, vi } from "vitest";

import { StocksTable } from "./StocksTable";
import { server } from "../mocks/server";
import type { MarkSource } from "../lib/types";

const createQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
        refetchOnWindowFocus: false,
        refetchInterval: false,
        gcTime: 0,
      },
    },
  });

const renderWithClient = (ui: ReactNode) => {
  const client = createQueryClient();
  const result = render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>,
  );
  return { ...result, client };
};

type StockSnapshotInput = {
  symbol: string;
  quantity: number;
  averageCost: number;
  markPrice: number;
  markSource: MarkSource;
  markTime: string;
  dayPnlAmount: number;
  totalPnlAmount: number;
  previousClose: number;
  staleSeconds: number;
};

const buildStockEntry = ({
  symbol,
  quantity,
  averageCost,
  markPrice,
  markSource,
  markTime,
  dayPnlAmount,
  totalPnlAmount,
  previousClose,
  staleSeconds,
}: StockSnapshotInput) => ({
  secType: "STK" as const,
  symbol,
  qty: quantity,
  avg_cost: averageCost,
  multiplier: 1,
  mark: markPrice,
  mark_source: markSource,
  price_source: markSource.toLowerCase(),
  stale_s: staleSeconds,
  pnl_intraday: dayPnlAmount,
  pnl_unrealized: totalPnlAmount,
  previous_close: previousClose,
  updated_at: markTime,
});

const mockStocks = (entries: StockSnapshotInput[]) => {
  const snapshot = {
    ts: Date.parse("2024-01-01T12:00:00Z"),
    session: "RTH",
    positions_view: {
      single_stocks: entries.map(buildStockEntry),
      option_combos: [],
      single_options: [],
    },
  };
  server.use(http.get("*/state", () => HttpResponse.json(snapshot)));
  return snapshot;
};

describe("StocksTable", () => {
  beforeEach(() => {
    vi.useRealTimers();
    vi.setSystemTime(new Date("2024-01-01T12:00:00Z"));
  });

  afterEach(() => {
    vi.setSystemTime(new Date());
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  test("renders fetched stocks sorted by day P&L with mark badge", async () => {
    mockStocks([
      {
        symbol: "MSFT",
        quantity: 42,
        averageCost: 260.8142857142857,
        markPrice: 290.1,
        markSource: "LAST",
        markTime: "2024-01-01T11:58:00Z",
        dayPnlAmount: 420,
        totalPnlAmount: 1230,
        previousClose: 280.1,
        staleSeconds: 120,
      },
      {
        symbol: "AAPL",
        quantity: 100,
        averageCost: 166,
        markPrice: 190.5,
        markSource: "MID",
        markTime: "2024-01-01T11:59:00Z",
        dayPnlAmount: 815,
        totalPnlAmount: 2450,
        previousClose: 182.35,
        staleSeconds: 60,
      },
    ]);

    const { client } = renderWithClient(<StocksTable />);

    await screen.findByText("AAPL");
    const grid = screen.getByRole("grid", { name: /single stocks positions/i });
    const rows = within(grid).getAllByRole("row");
    expect(rows).toHaveLength(3); // header + 2 data rows

    const firstDataRow = rows[1];
    expect(firstDataRow).toHaveTextContent("AAPL");
    expect(within(firstDataRow).getByText("MID")).toBeInTheDocument();
    expect(firstDataRow).toHaveTextContent("$815.00");

  });

  test("exposes grid semantics and default aria-sort state", async () => {
    mockStocks([
      {
        symbol: "SHOP",
        quantity: 32,
        averageCost: 61.7,
        markPrice: 70.2,
        markSource: "MID",
        markTime: "2024-01-01T11:58:00Z",
        dayPnlAmount: 110,
        totalPnlAmount: 240,
        previousClose: 66.7625,
        staleSeconds: 90,
      },
    ]);

    const { client } = renderWithClient(<StocksTable />);

    const grid = await screen.findByRole("grid", { name: /single stocks positions/i });
    expect(grid).toBeInTheDocument();
    await within(grid).findByRole("rowheader", { name: "SHOP" });
    expect(grid).toHaveAttribute("aria-rowcount", "2");
    expect(grid).toHaveAttribute("aria-colcount", "7");
    expect(grid).not.toHaveAttribute("aria-busy");

    const rows = within(grid).getAllByRole("row");
    expect(rows).toHaveLength(2);
    const dataRow = rows[1];
    expect(within(dataRow).getByRole("rowheader")).toHaveTextContent("SHOP");
    expect(within(dataRow).getAllByRole("gridcell")).toHaveLength(6);

    const headers = within(grid).getAllByRole("columnheader");
    expect(headers).not.toHaveLength(0);
    const dayPnlHeader = headers.find((header) => header.textContent?.includes("Day P"));
    expect(dayPnlHeader).toBeDefined();
    if (!dayPnlHeader) {
      throw new Error("Day P&L header not found");
    }
    expect(dayPnlHeader).toHaveAttribute("aria-sort", "descending");

  });

  test("formats staleness as mm:ss and applies threshold styling", async () => {
    mockStocks([
      {
        symbol: "TSLA",
        quantity: 25,
        averageCost: 209.9,
        markPrice: 198.5,
        markSource: "PREV",
        markTime: "2024-01-01T11:54:45Z",
        dayPnlAmount: -85,
        totalPnlAmount: -285,
        previousClose: 201.9,
        staleSeconds: 315,
      },
    ]);

    const { client } = renderWithClient(<StocksTable />);

    const stalenessCell = await screen.findByText("05:15");
    expect(stalenessCell).toBeInTheDocument();
    expect(stalenessCell.className).toContain("text-amber");

  });

  test("supports keyboard navigation and row expansion", async () => {
    mockStocks([
      {
        symbol: "NVDA",
        quantity: 30,
        averageCost: 396.5,
        markPrice: 456.5,
        markSource: "MID",
        markTime: "2024-01-01T11:59:30Z",
        dayPnlAmount: 620,
        totalPnlAmount: 1800,
        previousClose: 435.8333333333333,
        staleSeconds: 30,
      },
      {
        symbol: "AMZN",
        quantity: 55,
        averageCost: 124.291,
        markPrice: 130.1,
        markSource: "LAST",
        markTime: "2024-01-01T11:58:45Z",
        dayPnlAmount: 180,
        totalPnlAmount: 320,
        previousClose: 126.83636363636364,
        staleSeconds: 75,
      },
    ]);

    const { client } = renderWithClient(<StocksTable />);
    const user = userEvent.setup();

    await screen.findByText("NVDA");

    await act(async () => {
      await user.tab(); // focus filter
    });
    await act(async () => {
      await user.tab(); // focus sort toggle
    });
    await act(async () => {
      await user.tab(); // focus first row
    });

    const dataRows = within(screen.getByRole("grid", { name: /single stocks positions/i }))
      .getAllByRole("row")
      .slice(1, 3);
    const [firstRow, secondRow] = dataRows;

    expect(document.activeElement).toBe(firstRow);
    expect(firstRow).toHaveAttribute("tabindex", "0");
    expect(firstRow).toHaveAttribute("aria-selected", "true");
    expect(within(firstRow).getByRole("rowheader")).toHaveTextContent("NVDA");
    expect(within(firstRow).getAllByRole("gridcell")).toHaveLength(6);
    expect(secondRow).toHaveAttribute("tabindex", "-1");

    await act(async () => {
      await user.keyboard("{ArrowDown}");
    });
    await waitFor(() => expect(document.activeElement).toBe(secondRow));
    await waitFor(() => expect(secondRow).toHaveAttribute("aria-selected", "true"));
    expect(firstRow).toHaveAttribute("aria-selected", "false");
    expect(firstRow).toHaveAttribute("tabindex", "-1");

    await act(async () => {
      await user.keyboard("{Enter}");
    });
    await waitFor(() => expect(secondRow).toHaveAttribute("aria-expanded", "true"));
    await screen.findByRole("heading", { level: 4, name: "Fundamentals" });

    await act(async () => {
      await user.keyboard("{Space}");
    });
    await waitFor(() => expect(secondRow).toHaveAttribute("aria-expanded", "false"));
    await waitFor(() =>
      expect(screen.queryByRole("heading", { level: 4, name: "Fundamentals" })).toBeNull(),
    );

    await act(async () => {
      await user.keyboard("{Home}");
    });
    await waitFor(() => expect(document.activeElement).toBe(firstRow));
    expect(firstRow).toHaveAttribute("aria-selected", "true");
    expect(secondRow).toHaveAttribute("aria-selected", "false");

    await act(async () => {
      await user.keyboard("{End}");
    });
    await waitFor(() => expect(document.activeElement).toBe(secondRow));
    expect(secondRow).toHaveAttribute("aria-selected", "true");

  });

  test("toggles day P&L sort direction via header control", async () => {
    mockStocks([
      {
        symbol: "NVDA",
        quantity: 30,
        averageCost: 396.5,
        markPrice: 456.5,
        markSource: "MID",
        markTime: "2024-01-01T11:59:30Z",
        dayPnlAmount: 620,
        totalPnlAmount: 1800,
        previousClose: 435.8333333333333,
        staleSeconds: 30,
      },
      {
        symbol: "AMZN",
        quantity: 55,
        averageCost: 124.291,
        markPrice: 130.1,
        markSource: "LAST",
        markTime: "2024-01-01T11:58:45Z",
        dayPnlAmount: 180,
        totalPnlAmount: 320,
        previousClose: 126.83636363636364,
        staleSeconds: 75,
      },
    ]);

    const { client } = renderWithClient(<StocksTable />);
    const user = userEvent.setup();

    const header = await screen.findByRole("columnheader", { name: /day p&l/i });
    expect(header).toHaveAttribute("aria-sort", "descending");

    let toggleButton = within(header).getByRole("button", { name: /day p&l/i });
    await act(async () => {
      await user.click(toggleButton);
    });

    await waitFor(() => expect(header).toHaveAttribute("aria-sort", "ascending"));
    let dataRows = within(screen.getByRole("grid", { name: /single stocks positions/i })).getAllByRole("row").slice(1, 3);
    expect(dataRows[0]).toHaveTextContent("AMZN");

    toggleButton = within(header).getByRole("button", { name: /day p&l/i });
    expect(toggleButton).toBe(document.activeElement);
    await act(async () => {
      await user.keyboard("{Enter}"); // trigger via keyboard while button focused
    });
    await waitFor(() => expect(header).toHaveAttribute("aria-sort", "descending"));
    dataRows = within(screen.getByRole("grid", { name: /single stocks positions/i })).getAllByRole("row").slice(1, 3);
    expect(dataRows[0]).toHaveTextContent("NVDA");

  });

  test("focuses the filter input when / is pressed globally", async () => {
    mockStocks([
      {
        symbol: "AMD",
        quantity: 80,
        averageCost: 100.625,
        markPrice: 104.5,
        markSource: "MID",
        markTime: "2024-01-01T11:57:00Z",
        dayPnlAmount: 120,
        totalPnlAmount: 310,
        previousClose: 103.0,
        staleSeconds: 180,
      },
    ]);

    const { client } = renderWithClient(<StocksTable />);
    const user = userEvent.setup();

    await screen.findByText("AMD");
    expect(screen.getByLabelText("Filter symbols")).not.toBe(document.activeElement);

    await act(async () => {
      await user.keyboard("/");
    });
    await waitFor(() => expect(screen.getByLabelText("Filter symbols")).toBe(document.activeElement));

  });
});
