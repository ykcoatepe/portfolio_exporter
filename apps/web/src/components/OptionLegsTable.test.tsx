import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import seed from "../fixtures/optionLegs.seed.json";
import { isOptionLegsSeed, type OptionLegsSeed } from "../lib/optionLegs.types";
import { renderWithClient } from "../test/queryClient";
import { OptionLegsTable } from "./OptionLegsTable";

const mockUseOptionLegs = vi.fn();

vi.mock("../hooks/useOptions", () => ({
  useOptionLegs: () => mockUseOptionLegs(),
}));

const deepClone = <T,>(value: T): T => JSON.parse(JSON.stringify(value));

const SEED_DATA: OptionLegsSeed = (() => {
  if (isOptionLegsSeed(seed)) {
    return seed;
  }
  throw new Error("Invalid option legs seed fixture");
})();

const ORPHAN_COUNT = SEED_DATA.legs.filter((leg) => leg.isOrphan).length;
const MSFT_ORPHAN_COUNT = SEED_DATA.legs.filter(
  (leg) => leg.isOrphan && leg.shortUnderlying === "MSFT",
).length;
const DELTA_RANGE_COUNT = SEED_DATA.legs.filter(
  (leg) => leg.delta >= 0.1 && leg.delta <= 0.4,
).length;

const createMockResult = () => ({
  data: deepClone(SEED_DATA.legs),
  isLoading: false,
  isFetching: false,
  error: null,
  refetch: vi.fn(),
  underlyings: [...SEED_DATA.underlyings],
  expiries: [...SEED_DATA.expiries],
});

describe("OptionLegsTable", () => {
  beforeEach(() => {
    mockUseOptionLegs.mockReturnValue(createMockResult());
  });

  afterEach(() => {
    mockUseOptionLegs.mockReset();
  });

  test("renders friendly leg labels with OSI tooltip", async () => {
    renderWithClient(<OptionLegsTable />);

    const body = screen.getByTestId("rows-body");
    const firstRow = within(body).getAllByRole("row", { name: /leg row/i })[0];
    const rowHeader = within(firstRow).getByRole("rowheader");
    const labelSpan = rowHeader.querySelector("span");
    expect(labelSpan).not.toBeNull();
    if (!labelSpan) {
      return;
    }
    expect(labelSpan.textContent).not.toMatch(/\d{6,8}[CP]\d{8}/);
    const title = labelSpan.getAttribute("title");
    expect(title).not.toBeNull();
    if (!title) {
      return;
    }
    expect(title).toMatch(/^[A-Z]{1,6}\s{0,5}\d{6,8}[CP]\d{8}$/);
  });

  test("filters to orphan legs and toggles underlyings", async () => {
    const user = userEvent.setup();
    renderWithClient(<OptionLegsTable />);

    await screen.findByRole("grid", { name: /single option legs/i });
    const body = screen.getByTestId("rows-body");
    const initialRows = within(body).getAllByRole("row", { name: /leg row/i });
    expect(initialRows).toHaveLength(SEED_DATA.legs.length);

    const orphanToggle = screen.getByLabelText(/only orphan legs/i);
    await act(async () => {
      await user.click(orphanToggle);
    });

    await waitFor(() => {
      const rowsAfterOrphan = within(body).getAllByRole("row", { name: /leg row/i });
      expect(rowsAfterOrphan).toHaveLength(ORPHAN_COUNT);
    });

    // Toggle underlying chip
    const underlyingsSection = screen.getByText(/underlyings/i).closest("div");
    if (!underlyingsSection) {
      throw new Error("Underlyings section not found");
    }
    const allButton = within(underlyingsSection).getByRole("button", { name: /^all$/i });
    const msftButton = within(underlyingsSection).getByRole("button", { name: /^msft$/i });

    await act(async () => {
      await user.click(msftButton);
    });
    await waitFor(() => {
      const rowsAfterMsft = within(body).getAllByRole("row", { name: /leg row/i });
      expect(rowsAfterMsft).toHaveLength(MSFT_ORPHAN_COUNT);
    });

    await act(async () => {
      await user.click(allButton);
    });
    await waitFor(() => {
      const rowsReset = within(body).getAllByRole("row", { name: /leg row/i });
      expect(rowsReset).toHaveLength(ORPHAN_COUNT);
    });
  });

  test("applies delta range filter", async () => {
    const user = userEvent.setup();
    renderWithClient(<OptionLegsTable />);

    await screen.findByRole("grid", { name: /single option legs/i });
    const body = screen.getByTestId("rows-body");
    const deltaMinInput = screen.getByLabelText(/Δ Min/i, { selector: "input" });
    const deltaMaxInput = screen.getByLabelText(/Δ Max/i, { selector: "input" });

    await act(async () => {
      fireEvent.change(deltaMinInput, { target: { value: "0.1" } });
      fireEvent.change(deltaMaxInput, { target: { value: "0.4" } });
    });

    await waitFor(() => {
      expect(screen.queryByText("-0.18")).not.toBeInTheDocument();
    });
    const filteredRows = within(body).getAllByRole("row", { name: /leg row/i });
    expect(filteredRows).toHaveLength(DELTA_RANGE_COUNT);
    expect(screen.queryByText("-0.18")).not.toBeInTheDocument();
    expect(screen.queryByText("-0.55")).not.toBeInTheDocument();

    // Reset delta range
    const resetButton = screen.getByRole("button", { name: /reset Δ/i });
    await act(async () => {
      await user.click(resetButton);
    });
    await waitFor(() => {
      const rowsAfterReset = within(body).getAllByRole("row", { name: /leg row/i });
      expect(rowsAfterReset).toHaveLength(SEED_DATA.legs.length);
    });
  });

  test("displays legs with derived marks even when totals are null", async () => {
    mockUseOptionLegs.mockReturnValueOnce(createMockResult());
    renderWithClient(<OptionLegsTable />);

    const body = screen.getByTestId("rows-body");
    const rows = within(body).getAllByRole("row", { name: /leg row/i });
    const targetRow = rows.find((row) =>
      within(row).queryByText(/AAPL 165C Jun 21 '24/i),
    );
    expect(targetRow).toBeDefined();
    if (!targetRow) {
      return;
    }

    expect(within(targetRow).getByText(/\$1\.23/)).toBeInTheDocument();
    const placeholders = within(targetRow).getAllByText("—");
    expect(placeholders.length).toBeGreaterThan(0);
  });
});
