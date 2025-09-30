import { act, fireEvent, screen, waitFor, waitForElementToBeRemoved, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { OptionLegsTable } from "./OptionLegsTable";
import { buildOptionsResponse } from "../mocks/handlers";
import { server } from "../mocks/server";
import { renderWithClient } from "../test/queryClient";

const mockOptions = () => {
  const payload = buildOptionsResponse();

  payload.legs.forEach((leg) => {
    leg.label = leg.symbol ?? leg.label;
    if (leg.display) {
      leg.display.leg_label = leg.symbol ?? leg.display.leg_label;
    }
  });

  payload.combos?.forEach((combo) => {
    const rawLabel = (combo.legs ?? [])
      .map((leg) => leg.symbol ?? "")
      .filter(Boolean)
      .join(" • ");
    if (rawLabel) {
      combo.label = rawLabel;
      if (combo.display) {
        combo.display.combo_label = rawLabel;
      }
    }
  });

  payload.combo_groups?.forEach((group) => {
    const rawGroupLabel = group.legs
      .map((leg) => leg.symbol ?? "")
      .filter(Boolean)
      .join(" + ");
    if (rawGroupLabel) {
      group.label = rawGroupLabel;
      if (group.display) {
        group.display.combo_label = rawGroupLabel;
      }
    }
    group.legs.forEach((leg) => {
      leg.label = leg.symbol ?? leg.label;
      if (leg.display) {
        leg.display.leg_label = leg.symbol ?? leg.display.leg_label;
      }
    });
  });

  server.use(
    http.get("*/positions/options", () => HttpResponse.json(payload)),
  );
  return payload;
};

describe("OptionLegsTable", () => {
  beforeEach(() => {
    vi.useRealTimers();
    vi.setSystemTime(new Date("2024-01-01T12:00:00Z"));
    mockOptions();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.setSystemTime(new Date());
    vi.restoreAllMocks();
  });

  test("renders friendly leg labels with OSI tooltip", async () => {
    renderWithClient(<OptionLegsTable />);

    await waitForElementToBeRemoved(() => screen.queryAllByTestId("skeleton-row"));
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

    await waitForElementToBeRemoved(() => screen.queryAllByTestId("skeleton-row"));
    const grid = await screen.findByRole("grid", { name: /single option legs/i });
    const body = screen.getByTestId("rows-body");
    const initialRows = within(body).getAllByRole("row", { name: /leg row/i });
    expect(initialRows.length).toBeGreaterThan(1);

    const orphanToggle = screen.getByLabelText(/only orphan legs/i);
    await act(async () => {
      await user.click(orphanToggle);
    });

    await waitFor(() => {
      const rowsAfterOrphan = within(body).getAllByRole("row", { name: /leg row/i });
      expect(rowsAfterOrphan).toHaveLength(2);
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
      expect(rowsAfterMsft).toHaveLength(1);
    });

    await act(async () => {
      await user.click(allButton);
    });
    await waitFor(() => {
      const rowsReset = within(body).getAllByRole("row", { name: /leg row/i });
      expect(rowsReset.length).toBeGreaterThan(1);
    });
  });

  test("applies delta range filter", async () => {
    const user = userEvent.setup();
    renderWithClient(<OptionLegsTable />);

    await waitForElementToBeRemoved(() => screen.queryAllByTestId("skeleton-row"));
    const grid = await screen.findByRole("grid", { name: /single option legs/i });
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
    expect(filteredRows).toHaveLength(2);

    // Reset delta range
    const resetButton = screen.getByRole("button", { name: /reset Δ/i });
    await act(async () => {
      await user.click(resetButton);
    });
    await waitFor(() => {
      const rowsAfterReset = within(body).getAllByRole("row", { name: /leg row/i });
      expect(rowsAfterReset.length).toBeGreaterThan(filteredRows.length);
    });
  });

  test("displays legs with derived marks even when totals are null", async () => {
    const payload = mockOptions();
    const targetLeg = payload.legs[0];
    targetLeg.symbol = "NULLPNL  250118C00150000";
    targetLeg.label = "Null PnL Mark";
    targetLeg.display = {
      ...targetLeg.display,
      leg_label: "Null PnL Mark",
      short_ul: "NPNL",
      expiry_short: "JAN25",
    };
    targetLeg.mark_price = null;
    targetLeg.mark_time = null;
    targetLeg.mark = 1.23;
    targetLeg.last = 1.23;
    targetLeg.last_ts = "2024-01-01T11:59:30Z";
    targetLeg.previous_close = 1.1;
    targetLeg.total_pnl_amount = null;
    targetLeg.total_pnl_percent = null;
    targetLeg.day_pnl_amount = null;
    targetLeg.day_pnl_percent = null;

    renderWithClient(<OptionLegsTable />);

    await waitForElementToBeRemoved(() => screen.queryAllByTestId("skeleton-row"));
    const body = screen.getByTestId("rows-body");
    const rows = within(body).getAllByRole("row", { name: /leg row/i });
    const targetRow = rows.find((row) =>
      within(row).queryByText(/Null PnL Mark/i),
    );
    expect(targetRow).toBeDefined();
    if (!targetRow) {
      return;
    }

    expect(within(targetRow).getByText(/\$1\.23/)).toBeInTheDocument();
    expect(within(targetRow).getByText("00:30")).toBeInTheDocument();
    const placeholders = within(targetRow).getAllByText("—");
    expect(placeholders.length).toBeGreaterThan(0);
  });
});
