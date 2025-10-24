import { render, screen } from "@testing-library/react";
import { beforeAll, beforeEach, describe, expect, test, vi } from "vitest";

import MSBMiniCharts from "./MSBMiniCharts";
import type { MsbReading } from "../lib/types";
import { useMsbHistory } from "../hooks/useMsbHistory";

vi.mock("../hooks/useMsbHistory", () => ({
  useMsbHistory: vi.fn(),
}));

const mockedUseMsbHistory = vi.mocked(useMsbHistory);

class ResizeObserverMock {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

beforeAll(() => {
  if (!globalThis.ResizeObserver) {
    globalThis.ResizeObserver = ResizeObserverMock as unknown as typeof ResizeObserver;
  }
});

const makeHistory = (): MsbReading[] =>
  Array.from({ length: 14 }).map((_, index) => ({
    date: `2024-01-${(index + 1).toString().padStart(2, "0")}`,
    hy: 3 + index * 0.1,
    vx1: 16 + index * 0.05,
    vx2: 17 + index * 0.04,
    z_hy: 0.5,
    term_ratio: 0.9 + index * 0.01,
    cal_spread_pct: 0.03 + index * 0.001,
    cal_spread_abs: 0.6 + index * 0.02,
    saturated: false,
    hy_score: 10 + index,
    vix_score: 12 + index,
    msb: 20 + index,
    color: index > 8 ? "orange" : "yellow",
    triggers: [],
    winsor_clipped_n: 0,
    cooldown_until: null,
  }));

beforeEach(() => {
  mockedUseMsbHistory.mockReturnValue({
    data: makeHistory(),
    isLoading: false,
    error: null,
  } as never);
});

describe("MSBMiniCharts", () => {
  test("shows toggles and sparkline figures", () => {
    render(<MSBMiniCharts />);

    expect(screen.getByRole("button", { name: "7D" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "1Y" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("img", { name: /HY-OAS sparkline/i })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /VX1 (?:over|\/) VX2 ratio sparkline/i })).toBeInTheDocument();
  });
});
