import { describe, expect, test } from "vitest";

import {
  matchesNumberFilter,
  matchesStringFilter,
  parseNumberFilterInput,
  type PsdNumberFilterValue,
} from "./filters";

describe("psd filters", () => {
  test("matchesStringFilter trims and ignores case", () => {
    expect(matchesStringFilter("  AAPL  ", "aap")).toBe(true);
    expect(matchesStringFilter("Tesla", "TES")).toBe(true);
    expect(matchesStringFilter("Tesla", "  ")).toBe(true);
    expect(matchesStringFilter(null, "tsla")).toBe(false);
  });

  test("matchesNumberFilter handles ops and nulls", () => {
    const gte: PsdNumberFilterValue = { op: "gte", a: 10 };
    const lte: PsdNumberFilterValue = { op: "lte", a: 5 };
    const eq: PsdNumberFilterValue = { op: "eq", a: 0 };
    const between: PsdNumberFilterValue = { op: "between", a: 2, b: 4 };

    expect(matchesNumberFilter(12, gte)).toBe(true);
    expect(matchesNumberFilter(4, lte)).toBe(true);
    expect(matchesNumberFilter(0, eq)).toBe(true);
    expect(matchesNumberFilter(3, between)).toBe(true);

    expect(matchesNumberFilter(4, gte)).toBe(false);
    expect(matchesNumberFilter(6, lte)).toBe(false);
    expect(matchesNumberFilter(1, eq)).toBe(false);
    expect(matchesNumberFilter(5, between)).toBe(false);

    expect(matchesNumberFilter(null, eq)).toBe(false);
    expect(matchesNumberFilter(Number.NaN, gte)).toBe(false);
    expect(matchesNumberFilter(0, null)).toBe(true);
  });

  test("parseNumberFilterInput parses comparisons and ranges", () => {
    expect(parseNumberFilterInput(">= 12.5")).toEqual({ op: "gte", a: 12.5 });
    expect(parseNumberFilterInput("<= -3")).toEqual({ op: "lte", a: -3 });
    expect(parseNumberFilterInput("10-20")).toEqual({ op: "between", a: 10, b: 20 });
    expect(parseNumberFilterInput("7")).toEqual({ op: "eq", a: 7 });
    expect(parseNumberFilterInput("0")).toEqual({ op: "eq", a: 0 });
    expect(parseNumberFilterInput("")).toBeNull();
    expect(parseNumberFilterInput(" ")).toBeNull();
    expect(parseNumberFilterInput(">= ")).toBeNull();
    expect(parseNumberFilterInput("12-")).toBeNull();
    expect(parseNumberFilterInput("abc")).toBeNull();
  });
});
