import { describe, expect, it } from "vitest";

import {
  buildFriendlyLegDisplay,
  deriveGroupKey,
  formatComboLabel,
  formatLegLabel,
  parseOsi,
} from "./labels";
import type { OptionComboLegApi } from "./types";

const baseLeg: Omit<OptionComboLegApi, "right" | "strike" | "expiry"> = {
  id: "leg-1",
  combo_id: "combo-1",
  combo_group_id: null,
  symbol: "SPY 20251018P00395000",
  underlying: "SPY",
  mark_price: null,
  mark_source: "MID",
  mark_time: null,
  quantity: -1,
  delta: null,
  gamma: null,
  theta: null,
  vega: null,
  iv: null,
  day_pnl_amount: null,
  day_pnl_percent: null,
  total_pnl_amount: null,
  total_pnl_percent: null,
};

const makeLeg = (overrides: Partial<OptionComboLegApi>): OptionComboLegApi => ({
  ...baseLeg,
  strike: 100,
  expiry: "2025-10-18",
  right: "C",
  ...overrides,
});

describe("labels helpers", () => {
  it("parses OSI symbols into friendly components", () => {
    const parsed = parseOsi("BKSY 251017C00022500");
    expect(parsed).toEqual({ ul: "BKSY", expiryISO: "2025-10-17", side: "C", strike: 22.5 });
    const compact = parseOsi("BKSY251017C00022500");
    expect(compact).toEqual(parsed);
    const spx = parseOsi("SPX 20241018C00460000");
    expect(spx).toEqual({ ul: "SPX", expiryISO: "2024-10-18", side: "C", strike: 460 });
    expect(parseOsi("INVALID")).toBeNull();
  });

  it("parses padded OSI roots with double spaces", () => {
    const parsed = parseOsi("SPX  20241018P00410000");
    expect(parsed).toEqual({ ul: "SPX", expiryISO: "2024-10-18", side: "P", strike: 410 });
  });

  it("builds friendly labels with OSI tooltips", () => {
    const compact = buildFriendlyLegDisplay({ symbol: "AAPL251017C00150000" });
    expect(compact.label).toBe("AAPL 150C • Oct 17 '25");
    expect(compact.tooltip).toBe("AAPL251017C00150000");

    const spaced = buildFriendlyLegDisplay({ symbol: "AAPL  251017P00150000" });
    expect(spaced.label).toBe("AAPL 150P • Oct 17 '25");
    expect(spaced.tooltip).toBe("AAPL  251017P00150000");
  });

  it.each([
    ["double-spaced OSI root", "BKSY  251017C00022500", "BKSY 22.5C • Oct 17 '25"],
    ["compact OSI symbol", "BKSY20251017P00016000", "BKSY 16P • Oct 17 '25"],
  ])("omits OSI digits from labelText while preserving original tooltip for %s", (_title, symbol, expectedLabel) => {
    const { label: labelText, tooltip: labelTooltip } = buildFriendlyLegDisplay({ symbol });
    expect(labelText).toBe(expectedLabel);
    expect(labelText).not.toMatch(/\d{6,8}[CP]\d{8}/);
    expect(labelTooltip).toBe(symbol);
    expect(labelTooltip).toMatch(/^[A-Z]{1,6}\s{0,5}\d{6,8}[CP]\d{8}$/);
  });

  it("formats leg labels with normalized right codes", () => {
    expect(formatLegLabel({ ul: "sp y", strike: 395, side: "put", expiryISO: "2025-10-18" })).toBe(
      "SP Y 395P • Oct 18 '25",
    );
    expect(
      formatLegLabel({ ul: "MSFT", strike: 320.5, side: "CALL", expiryISO: "2024-09-20" }),
    ).toBe("MSFT 320.5C • Sep 20 '24");
  });

  it("formats parsed OSI symbols into compact labels", () => {
    const parsed = parseOsi("BKSY251017C00022500");
    expect(parsed).not.toBeNull();
    if (!parsed) {
      return;
    }
    expect(formatLegLabel(parsed)).toBe("BKSY 22.5C • Oct 17 '25");
  });

  it("derives stable group keys regardless of right spelling", () => {
    const key = deriveGroupKey([
      { right: "CALL", strike: 445, expiry: "2025-10-18" },
      { right: "put", strike: 395, expiry: "2025-10-18" },
    ]);
    expect(key).toBe("C:445@2025-10-18|P:395@2025-10-18");
  });

  it("produces vertical combo labels", () => {
    const legs: OptionComboLegApi[] = [
      makeLeg({ id: "short", right: "CALL", strike: 320, quantity: -1 }),
      makeLeg({ id: "long", right: "CALL", strike: 315, quantity: 1 }),
    ];
    expect(formatComboLabel("Vertical", legs, 28, 0.5, "MSFT")).toBe(
      "MSFT 315/320C • 28d • Credit 0.50",
    );
  });

  it("produces iron condor labels", () => {
    const legs: OptionComboLegApi[] = [
      makeLeg({ id: "put-short", right: "PUT", strike: 395, quantity: -1 }),
      makeLeg({ id: "put-long", right: "PUT", strike: 400, quantity: 1 }),
      makeLeg({ id: "call-short", right: "CALL", strike: 440, quantity: -1 }),
      makeLeg({ id: "call-long", right: "CALL", strike: 445, quantity: 1 }),
    ];
    expect(formatComboLabel("IRON_CONDOR", legs, 28, 1.2, "SPY")).toBe(
      "SPY 395/400P + 440/445C • 28d • Credit 1.20",
    );
  });

  it("produces calendar labels with month span", () => {
    const legs: OptionComboLegApi[] = [
      makeLeg({ id: "near", right: "CALL", strike: 180, expiry: "2024-10-18", quantity: -1 }),
      makeLeg({ id: "far", right: "CALL", strike: 180, expiry: "2024-12-20", quantity: 1 }),
    ];
    expect(formatComboLabel("calendar", legs, 60, -0.65, "AAPL")).toBe(
      "AAPL 180C CAL • Oct→Dec • Debit 0.65",
    );
  });

  it("produces straddle and strangle labels", () => {
    const straddleLegs: OptionComboLegApi[] = [
      makeLeg({ id: "call", right: "C", strike: 240, quantity: 1, expiry: "2024-03-08" }),
      makeLeg({ id: "put", right: "P", strike: 240, quantity: 1, expiry: "2024-03-08" }),
    ];
    expect(formatComboLabel("straddle", straddleLegs, 7, -10.6, "TSLA")).toBe(
      "TSLA 240C+P • 7d",
    );

    const strangleLegs: OptionComboLegApi[] = [
      makeLeg({ id: "put", right: "PUT", strike: 135, quantity: -1, expiry: "2024-05-17" }),
      makeLeg({ id: "call", right: "CALL", strike: 160, quantity: -1, expiry: "2024-05-17" }),
    ];
    expect(formatComboLabel("strangle", strangleLegs, 14, 0.8, "AMZN")).toBe(
      "AMZN 135P/160C • 14d",
    );
  });
});
