import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";

import PowerlawPanel from "./PowerlawPanel";
import type { PowerlawSnapshot } from "../lib/types";
import { usePowerlawSignalsHelp } from "../hooks/usePowerlawSignalsHelp";

vi.mock("../hooks/usePowerlawSignalsHelp", () => ({
  usePowerlawSignalsHelp: vi.fn(),
}));

const mockedUsePowerlawSignalsHelp = vi.mocked(usePowerlawSignalsHelp);

beforeEach(() => {
  mockedUsePowerlawSignalsHelp.mockReturnValue({
    data: {
      title: "Powerlaw Signals Guide",
      subtitle: "How to read PLKE and risk state",
      sections: [{ title: "Overview", bullets: ["Sample bullet."] }],
      terms: [],
      footnotes: [],
    },
    isLoading: false,
    error: null,
  } as never);
});

describe("PowerlawPanel", () => {
  test("renders stale snapshot details", () => {
    const snapshot: PowerlawSnapshot = {
      as_of: "2025-01-03",
      stale: true,
      stale_reason: "behind_trading_day",
      refresh: { status: "failed" },
      data_quality: "WARN",
      plke: 56.4,
      plke_band_alpha: "Heating",
      risk_state: "ON",
      vol_bucket: "LOW",
      vutil_used: 0.08,
      vutil_source: "budget",
      vix_spot: 13.6,
      vvix_spot: 84.2,
      vx_backwardation: false,
      equity_weights: { SPY: 0.4, QQQ: 0.35 },
      hedge_notional: { SPX_put_spread: 0.003 },
      small_cap: { theta_pct_nav: 0.0024, can_open_new_trades: true, plke_band: "Heating" },
    };

    render(<PowerlawPanel powerlaw={snapshot} />);

    expect(screen.getByText("Powerlaw Signals")).toBeInTheDocument();
    expect(screen.getByText("STALE")).toBeInTheDocument();
    expect(screen.getByText("DATA: WARN")).toBeInTheDocument();
    expect(screen.getByText(/refresh failed/i)).toBeInTheDocument();
    expect(screen.getByText("PLKE")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /refresh powerlaw/i })).toBeInTheDocument();
  });

  test("renders placeholder when powerlaw is missing", () => {
    render(<PowerlawPanel powerlaw={null} />);
    expect(screen.getByText("Powerlaw Signals")).toBeInTheDocument();
    expect(screen.getByText(/not available/i)).toBeInTheDocument();
  });
});
