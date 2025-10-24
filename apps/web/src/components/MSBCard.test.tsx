import { render, screen } from "@testing-library/react";
import { describe, expect, test, vi, beforeEach } from "vitest";

import MSBCard from "./MSBCard";
import type { MsbReading } from "../lib/types";
import { useMsbCurrent } from "../hooks/useMsbCurrent";

vi.mock("../hooks/useMsbCurrent", () => ({
  useMsbCurrent: vi.fn(),
}));

const mockedUseMsbCurrent = vi.mocked(useMsbCurrent);

const sampleReading: MsbReading = {
  date: "2024-02-01",
  hy: 3.8,
  vx1: 18.2,
  vx2: 19.4,
  z_hy: 0.62,
  term_ratio: 0.94,
  cal_spread_pct: 0.041,
  cal_spread_abs: 0.75,
  saturated: false,
  hy_score: 16,
  vix_score: 18,
  msb: 32,
  color: "orange",
  triggers: ["RULE_B_HY_SHOCK", "RULE_C_MSB_60x3D"],
  winsor_clipped_n: 1,
  cooldown_until: null,
};

beforeEach(() => {
  mockedUseMsbCurrent.mockReturnValue({
    data: sampleReading,
    isLoading: false,
    error: null,
  } as never);
});

describe("MSBCard", () => {
  test("renders stress label, legend, and triggers", () => {
    render(<MSBCard />);

    const region = screen.getByRole("region", { name: /Market Stress Barometer/i });
    expect(region).toBeInTheDocument();

    const stressLabel = screen.getByText(/Stress: 32 — Orange/i);
    expect(stressLabel).toHaveAttribute("aria-live", "polite");

    expect(screen.getByText(/Legend/i)).toBeInTheDocument();
    expect(screen.getByText("Green")).toBeInTheDocument();
    expect(screen.getByText("Yellow")).toBeInTheDocument();
    expect(screen.getByText("Orange")).toBeInTheDocument();
    expect(screen.getByText("Red")).toBeInTheDocument();

    expect(screen.getByText("RULE_B_HY_SHOCK")).toBeInTheDocument();
    expect(screen.getByText("RULE_C_MSB_60x3D")).toBeInTheDocument();
  });
});
