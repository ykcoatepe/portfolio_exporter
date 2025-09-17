import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, afterEach, describe, expect, test, vi } from "vitest";

import { StocksTable } from "./StocksTable";
import { server } from "../mocks/server";
import type { StocksApiResponse } from "../lib/types";

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

const mockStocks = (payload: StocksApiResponse) => {
  server.use(http.get("*/positions/stocks", () => HttpResponse.json(payload)));
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
    mockStocks({
      data: [
        {
          symbol: "MSFT",
          quantity: 42,
          average_price: 274.5,
          mark_price: 290.1,
          mark_source: "LAST",
          mark_time: "2024-01-01T11:58:00Z",
          day_pnl_amount: 420,
          day_pnl_percent: 0.018,
          total_pnl_amount: 1230,
          total_pnl_percent: 0.046,
          currency: "USD",
        },
        {
          symbol: "AAPL",
          quantity: 100,
          average_price: 182.25,
          mark_price: 190.5,
          mark_source: "MID",
          mark_time: "2024-01-01T11:59:00Z",
          day_pnl_amount: 815,
          day_pnl_percent: 0.027,
          total_pnl_amount: 2450,
          total_pnl_percent: 0.062,
          currency: "USD",
        },
      ],
      as_of: "2024-01-01T12:00:00Z",
    });

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
    mockStocks({
      data: [
        {
          symbol: "SHOP",
          quantity: 32,
          average_price: 68,
          mark_price: 70.2,
          mark_source: "MID",
          mark_time: "2024-01-01T11:58:00Z",
          day_pnl_amount: 110,
          day_pnl_percent: 0.019,
          total_pnl_amount: 240,
          total_pnl_percent: 0.048,
          currency: "USD",
        },
      ],
    });

    const { client } = renderWithClient(<StocksTable />);

    const grid = await screen.findByRole("grid", { name: /single stocks positions/i });
    expect(grid).toBeInTheDocument();

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
    mockStocks({
      data: [
        {
          symbol: "TSLA",
          quantity: 25,
          average_price: 210.0,
          mark_price: 198.5,
          mark_source: "PREV",
          mark_time: "2024-01-01T11:54:45Z",
          day_pnl_amount: -85,
          day_pnl_percent: -0.012,
          total_pnl_amount: -285,
          total_pnl_percent: -0.057,
          currency: "USD",
        },
      ],
    });

    const { client } = renderWithClient(<StocksTable />);

    const stalenessCell = await screen.findByText("05:15");
    expect(stalenessCell).toBeInTheDocument();
    expect(stalenessCell.className).toContain("text-amber");

  });

  test("supports keyboard navigation and row expansion", async () => {
    mockStocks({
      data: [
        {
          symbol: "NVDA",
          quantity: 30,
          average_price: 440.0,
          mark_price: 456.5,
          mark_source: "MID",
          mark_time: "2024-01-01T11:59:30Z",
          day_pnl_amount: 620,
          day_pnl_percent: 0.034,
          total_pnl_amount: 1800,
          total_pnl_percent: 0.072,
          currency: "USD",
        },
        {
          symbol: "AMZN",
          quantity: 55,
          average_price: 128.4,
          mark_price: 130.1,
          mark_source: "LAST",
          mark_time: "2024-01-01T11:58:45Z",
          day_pnl_amount: 180,
          day_pnl_percent: 0.016,
          total_pnl_amount: 320,
          total_pnl_percent: 0.041,
          currency: "USD",
        },
      ],
    });

    const { client } = renderWithClient(<StocksTable />);
    const user = userEvent.setup();

    await screen.findByText("NVDA");

    await user.tab(); // focus filter
    await user.tab(); // focus sort toggle
    await user.tab(); // focus first row

    const dataRows = within(screen.getByRole("grid", { name: /single stocks positions/i })).getAllByRole("row").slice(1, 3);
    const [firstRow, secondRow] = dataRows;
    expect(document.activeElement).toBe(firstRow);
    expect(document.activeElement).toMatchInlineSnapshot(`
      <tr
        aria-expanded="false"
        class="border-b border-slate-900/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950 hover:bg-slate-900/40"
        tabindex="0"
      >
        <td
          class="px-4 py-3 font-semibold tracking-wide text-slate-100"
        >
          <div
            class="flex items-center gap-2"
          >
            <span>
              NVDA
            </span>
            <span
              aria-hidden="true"
              class="inline-flex h-5 w-5 items-center justify-center rounded-full border border-slate-800/70 text-[0.6rem] text-slate-500"
            >
              +
            </span>
          </div>
        </td>
        <td
          class="px-4 py-3 text-right font-mono text-sm text-slate-200"
        >
          30
        </td>
        <td
          class="px-4 py-3 text-right font-mono text-sm text-slate-200"
        >
          $440.00
        </td>
        <td
          class="px-4 py-3 text-right font-mono text-sm"
        >
          <div
            class="flex items-center justify-end gap-3"
          >
            <span>
              $456.50
            </span>
            <span
              class="inline-flex min-w-[2.75rem] items-center justify-center rounded-full px-2 py-0.5 text-xs font-medium uppercase tracking-wide bg-sky-500/10 text-sky-300 border border-sky-500/30"
              title="Mark source: MID"
            >
              MID
            </span>
          </div>
        </td>
        <td
          class="px-4 py-3 text-right"
        >
          <div
            class="flex flex-col items-end gap-1"
          >
            <span
              class="font-mono text-sm text-emerald-300"
            >
              +$620.00
            </span>
            <span
              class="text-xs text-emerald-300"
            >
              +3.40%
            </span>
          </div>
        </td>
        <td
          class="px-4 py-3 text-right"
        >
          <div
            class="flex flex-col items-end gap-1"
          >
            <span
              class="font-mono text-sm text-emerald-300"
            >
              +$1,800.00
            </span>
            <span
              class="text-xs text-emerald-300"
            >
              +7.20%
            </span>
          </div>
        </td>
        <td
          class="px-4 py-3 text-right font-mono text-sm"
        >
          <span
            class="text-emerald-300"
          >
            00:30
          </span>
        </td>
      </tr>
    `);

    await user.keyboard("{ArrowDown}");
    expect(document.activeElement).toBe(secondRow);

    await user.keyboard("{Enter}");
    expect(document.activeElement).toBe(secondRow);
    await screen.findByRole("heading", { level: 4, name: "Fundamentals" });

    await user.keyboard("{Space}");
    await waitFor(() =>
      expect(screen.queryByRole("heading", { level: 4, name: "Fundamentals" })).toBeNull(),
    );

  });

  test("toggles day P&L sort direction via header control", async () => {
    mockStocks({
      data: [
        {
          symbol: "NVDA",
          quantity: 30,
          average_price: 440.0,
          mark_price: 456.5,
          mark_source: "MID",
          mark_time: "2024-01-01T11:59:30Z",
          day_pnl_amount: 620,
          day_pnl_percent: 0.034,
          total_pnl_amount: 1800,
          total_pnl_percent: 0.072,
          currency: "USD",
        },
        {
          symbol: "AMZN",
          quantity: 55,
          average_price: 128.4,
          mark_price: 130.1,
          mark_source: "LAST",
          mark_time: "2024-01-01T11:58:45Z",
          day_pnl_amount: 180,
          day_pnl_percent: 0.016,
          total_pnl_amount: 320,
          total_pnl_percent: 0.041,
          currency: "USD",
        },
      ],
    });

    const { client } = renderWithClient(<StocksTable />);
    const user = userEvent.setup();

    const header = await screen.findByRole("columnheader", { name: /day p&l/i });
    expect(header).toHaveAttribute("aria-sort", "descending");

    let toggleButton = within(header).getByRole("button", { name: /day p&l/i });
    await user.click(toggleButton);

    await waitFor(() => expect(header).toHaveAttribute("aria-sort", "ascending"));
    let dataRows = within(screen.getByRole("grid", { name: /single stocks positions/i })).getAllByRole("row").slice(1, 3);
    expect(dataRows[0]).toHaveTextContent("AMZN");

    toggleButton = within(header).getByRole("button", { name: /day p&l/i });
    expect(toggleButton).toBe(document.activeElement);
    await user.keyboard("{Enter}"); // trigger via keyboard while button focused
    await waitFor(() => expect(header).toHaveAttribute("aria-sort", "descending"));
    dataRows = within(screen.getByRole("grid", { name: /single stocks positions/i })).getAllByRole("row").slice(1, 3);
    expect(dataRows[0]).toHaveTextContent("NVDA");

  });

  test("focuses the filter input when / is pressed globally", async () => {
    mockStocks({
      data: [
        {
          symbol: "AMD",
          quantity: 80,
          average_price: 102,
          mark_price: 104.5,
          mark_source: "MID",
          mark_time: "2024-01-01T11:57:00Z",
          day_pnl_amount: 120,
          day_pnl_percent: 0.015,
          total_pnl_amount: 310,
          total_pnl_percent: 0.031,
          currency: "USD",
        },
      ],
    });

    const { client } = renderWithClient(<StocksTable />);
    const user = userEvent.setup();

    await screen.findByText("AMD");
    expect(screen.getByLabelText("Filter symbols")).not.toBe(document.activeElement);

    await user.keyboard("/");
    await waitFor(() => expect(screen.getByLabelText("Filter symbols")).toBe(document.activeElement));

  });
});
