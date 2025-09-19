import {
  fireEvent,
  screen,
  waitFor,
  waitForElementToBeRemoved,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { OptionLegsTable } from "./OptionLegsTable";
import { buildOptionsResponse } from "../mocks/handlers";
import { server } from "../mocks/server";
import { renderWithClient } from "../test/queryClient";

const mockOptions = () => {
  const payload = buildOptionsResponse();
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

  test("filters to orphan legs and toggles underlyings", async () => {
    renderWithClient(<OptionLegsTable />);

    await waitForElementToBeRemoved(() => screen.queryAllByTestId("skeleton-row"));
    const grid = await screen.findByRole("grid", { name: /single option legs/i });
    const body = screen.getByTestId("rows-body");
    const initialRows = within(body).getAllByRole("row", { name: /leg row/i });
    expect(initialRows.length).toBeGreaterThan(1);

    const orphanToggle = screen.getByLabelText(/only orphan legs/i);
    await userEvent.click(orphanToggle);

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

    await userEvent.click(msftButton);
    await waitFor(() => {
      const rowsAfterMsft = within(body).getAllByRole("row", { name: /leg row/i });
      expect(rowsAfterMsft).toHaveLength(1);
    });

    await userEvent.click(allButton);
    await waitFor(() => {
      const rowsReset = within(body).getAllByRole("row", { name: /leg row/i });
      expect(rowsReset.length).toBeGreaterThan(1);
    });
  });

  test("applies delta range filter", async () => {
    renderWithClient(<OptionLegsTable />);

    await waitForElementToBeRemoved(() => screen.queryAllByTestId("skeleton-row"));
    const grid = await screen.findByRole("grid", { name: /single option legs/i });
    const body = screen.getByTestId("rows-body");
    const deltaMinInput = screen.getByLabelText(/Δ Min/i, { selector: "input" });
    const deltaMaxInput = screen.getByLabelText(/Δ Max/i, { selector: "input" });

    await userEvent.clear(deltaMinInput);
    fireEvent.change(deltaMinInput, { target: { value: "0.1" } });
    await userEvent.clear(deltaMaxInput);
    fireEvent.change(deltaMaxInput, { target: { value: "0.4" } });

    await waitFor(() => {
      expect(deltaMinInput).toHaveValue(0.1);
      expect(deltaMaxInput).toHaveValue(0.4);
    });

    await waitFor(() => {
      expect(screen.queryByText("-0.18")).not.toBeInTheDocument();
    });
    const filteredRows = within(body).getAllByRole("row", { name: /leg row/i });
    expect(filteredRows).toHaveLength(2);

    // Reset delta range
    const resetButton = screen.getByRole("button", { name: /reset Δ/i });
    await userEvent.click(resetButton);
    await waitFor(() => {
      const rowsAfterReset = within(body).getAllByRole("row", { name: /leg row/i });
      expect(rowsAfterReset.length).toBeGreaterThan(filteredRows.length);
    });
  });
});
