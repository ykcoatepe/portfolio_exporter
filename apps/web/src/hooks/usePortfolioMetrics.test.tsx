import { render, waitFor } from "@testing-library/react";
import { useEffect } from "react";
import { afterEach, describe, expect, test, vi } from "vitest";

import type { PortfolioMetrics } from "./usePortfolioMetrics";
import { usePortfolioMetrics } from "./usePortfolioMetrics";
import { usePsdSnapshot } from "./usePsdSnapshot";
import type { PSDSnapshot } from "../lib/types";

vi.mock("./usePsdSnapshot", () => ({
  usePsdSnapshot: vi.fn(),
}));

const mockedUsePsdSnapshot = vi.mocked(usePsdSnapshot);

afterEach(() => {
  vi.clearAllMocks();
});

function MetricsHarness({ onValue }: { onValue: (value: PortfolioMetrics) => void }): null {
  const metrics = usePortfolioMetrics();
  useEffect(() => {
    onValue(metrics);
  }, [metrics, onValue]);
  return null;
}

describe("usePortfolioMetrics", () => {
  test("aggregates numeric totals while keeping legs with null P&L in the view", async () => {
    const snapshot: PSDSnapshot = {
      ts: 1_700_000_000_000,
      session: "RTH",
      positions_view: {
        single_stocks: [
          {
            secType: "STK",
            symbol: "AAPL",
            qty: 10,
            avg_cost: 120,
            multiplier: 1,
            mark: 130,
            price_source: "last",
            mark_source: "LAST",
            stale_s: 12,
            day_pnl: 12,
            day_pnl_percent: 0.5,
            pnl_intraday: 12,
            greeks: { delta: 1.2, theta: -0.4 },
            previous_close: 128,
          },
        ],
        option_combos: [
          {
            combo_id: "combo-1",
            name: "Test Combo",
            legs: [
              {
                secType: "OPT",
                symbol: "AAPL  250118C00150000",
                qty: 1,
                avg_cost: 2,
                multiplier: 100,
                mark: 2.5,
                price_source: "last",
                mark_source: "LAST",
                stale_s: 8,
                day_pnl: 5,
                day_pnl_percent: 0.1,
                pnl_intraday: 5,
                greeks: { delta: 0.3, theta: -0.1 },
              },
            ],
            pnl_intraday: 5,
            greeks_agg: { delta: 0.3, theta: -0.1 },
          },
        ],
        single_options: [
          {
            secType: "OPT",
            symbol: "AAPL  250118P00150000",
            qty: 1,
            avg_cost: Number.NaN,
            multiplier: 100,
            mark: 1.5,
            price_source: "last",
            mark_source: "LAST",
            stale_s: 30,
            pnl_intraday: Number.NaN,
            greeks: { delta: 0.2, theta: -0.15 },
            previous_close: 1.4,
          },
        ],
      },
    };

    const handleUpdate = vi.fn();
    mockedUsePsdSnapshot.mockReturnValue({ data: snapshot } as never);

    render(<MetricsHarness onValue={handleUpdate} />);

    await waitFor(() => {
      expect(handleUpdate).toHaveBeenCalled();
    });

    const latest = handleUpdate.mock.calls.at(-1)?.[0];
    expect(latest).toBeDefined();
    if (!latest) {
      return;
    }

    expect(latest.totalPnl).toBeCloseTo(150);
    expect(latest.dayPnl).toBeCloseTo(17);
    expect(latest.sumDelta).toBeCloseTo(1.7);
    expect(latest.sumTheta).toBeCloseTo(-0.65);
    expect(latest.stalenessSeconds).toBe(30);
    expect(latest.updatedAt).toBe(1_700_000_000_000);
  });
});
