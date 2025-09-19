import { screen, waitFor, waitForElementToBeRemoved, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { CombosTable } from "./CombosTable";
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

describe("CombosTable", () => {
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

  test("renders combos and expands legs on toggle", async () => {
    renderWithClient(<CombosTable />);

    await waitForElementToBeRemoved(() => screen.queryAllByTestId("skeleton-row"));
    const ironCondorRowHeader = await screen.findByRole("rowheader", {
      name: /iron condor/i,
    });
    expect(ironCondorRowHeader).toBeInTheDocument();

    const expandButton = within(ironCondorRowHeader.parentElement as HTMLElement).getByRole(
      "button",
      { name: /expand iron condor/i },
    );

    await userEvent.click(expandButton);

    expect(await screen.findByText("4600.00")).toBeInTheDocument();
    expect(screen.getByText("1.05", { exact: false })).toBeInTheDocument();

    // Mark badge rendered
    expect(screen.getAllByText("MID")[0]).toBeInTheDocument();

    // Collapse again
    await userEvent.click(expandButton);
    expect(screen.queryByText("4600.00")).not.toBeInTheDocument();
  });

  test("supports keyboard navigation across combo rows", async () => {
    renderWithClient(<CombosTable />);

    await waitForElementToBeRemoved(() => screen.queryAllByTestId("skeleton-row"));
    const grid = await screen.findByRole("grid", {
      name: /options combos positions/i,
    });

    const body = screen.getByTestId("rows-body");
    const dataRows = within(body).getAllByRole("row", { name: /combo row/i });

    expect(dataRows.length).toBeGreaterThan(1);

    dataRows[0].focus();
    expect(document.activeElement).toHaveAttribute("data-row-index", "0");

    await userEvent.keyboard("{ArrowDown}");
    await waitFor(() =>
      expect(document.activeElement).toHaveAttribute("data-row-index", "1"),
    );

    await userEvent.keyboard("{ArrowUp}");
    await waitFor(() =>
      expect(document.activeElement).toHaveAttribute("data-row-index", "0"),
    );

    await userEvent.keyboard("{ArrowRight}");
    expect(await screen.findByText("4600.00")).toBeInTheDocument();

    await userEvent.keyboard("{ArrowLeft}");
    expect(screen.queryByText("4600.00")).not.toBeInTheDocument();
  });
});
