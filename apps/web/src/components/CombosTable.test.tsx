import { act, screen, waitFor, waitForElementToBeRemoved, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { CombosTable, COLUMN_COUNT } from "./CombosTable";
import { useOptionCombos } from "../hooks/useOptions";
import { buildOptionsResponse } from "../mocks/handlers";
import { server } from "../mocks/server";
import type { MarkSource } from "../lib/types";
import { renderWithClient } from "../test/queryClient";

const QTY_TOOLTIP = "+ = long (debit), − = short (credit); magnitude = contracts";

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

function GroupMarkProbe() {
  const { groups, isLoading } = useOptionCombos();
  if (isLoading) {
    return <span data-testid="group-mark-loading">loading</span>;
  }
  return (
    <div>
      {groups.map((group) => (
        <span key={group.id} data-testid="group-mark">
          {group.markSource}
        </span>
      ))}
    </div>
  );
}

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

  test("renders header and rows with matching column counts", async () => {
    renderWithClient(<CombosTable />);

    await waitForElementToBeRemoved(() => screen.queryAllByTestId("skeleton-row"));

    const headers = screen.getAllByRole("columnheader");
    expect(headers).toHaveLength(COLUMN_COUNT);

    const firstRow = screen.getAllByRole("row", { name: /combo row/i })[0];
    const headerCell = within(firstRow).getByRole("rowheader");
    const gridCells = within(firstRow).getAllByRole("gridcell");
    expect([headerCell, ...gridCells]).toHaveLength(COLUMN_COUNT);
  });

  test("renders credit, playbook, status, progress, mark, and staleness in the expected columns", async () => {
    const payload = mockOptions();
    const group = payload.combo_groups?.[0];
    if (!group) {
      throw new Error("expected combo group in payload");
    }
    group.group_net_price = 2.5;
    group.group_qty = -2;
    group.tp_band_pct = [0.4, 0.6];
    group.tp_hit = true;
    group.tp_done = false;
    group.sl_hit = false;
    group.progress_pct = 0.45;
    delete group.progress_pct_of_goal;
    delete group.progress;
    group.group_mark = 1.91;
    group.group_mark_price = 1.91;
    group.group_pnl_unrealized = 275.5;
    group.mark_source = "MID";
    group.stale_seconds = 90;

    const combo = payload.combos?.find((item) => item.combo_group_id === group.combo_group_id);
    if (combo) {
      combo.tp_band_pct = [0.4, 0.6];
      combo.tp_hit = true;
      combo.tp_done = false;
      combo.sl_hit = false;
      combo.progress_pct = 0.45;
      delete combo.progress_pct_of_goal;
      delete combo.progress_pct_of_max;
      delete combo.progress;
      combo.mark_price = 1.91;
      combo.mark_source = "MID";
    }

    server.use(
      http.get("*/positions/options", () => HttpResponse.json(payload)),
    );

    renderWithClient(<CombosTable />);

    await waitForElementToBeRemoved(() => screen.queryAllByTestId("skeleton-row"));

    const rowElement = screen.getAllByRole("row", { name: /combo row/i })[0];
    const headerCell = within(rowElement).getByRole("rowheader");
    const gridCells = within(rowElement).getAllByRole("gridcell");
    const cells = [headerCell, ...gridCells];
    expect(cells).toHaveLength(COLUMN_COUNT);

    expect(cells[3]).toHaveTextContent("-2");
    expect(cells[4]).toHaveTextContent(/Credit/i);
    expect(cells[4]).toHaveTextContent("$2.50");
    expect(cells[5]).toHaveTextContent("40–60%");
    expect(cells[6]).toHaveTextContent("TP HIT");
    expect(within(cells[7]).getByRole("progressbar")).toBeInTheDocument();
    expect(within(cells[7]).getByText("45%")).toBeInTheDocument();
    expect(within(cells[8]).getByText("$1.91")).toBeInTheDocument();
    expect(within(cells[8]).getByText("MID")).toBeInTheDocument();
    expect(within(cells[9]).getByText("$275.50")).toBeInTheDocument();
    expect(cells[10]).toHaveTextContent("01:30");
  });

  test("shows em dash when progressPct is null", async () => {
    const payload = mockOptions();
    const group = payload.combo_groups?.[0];
    if (!group) {
      throw new Error("expected combo group in payload");
    }
    group.progress_pct = null;
    delete group.progress_pct_of_goal;
    delete group.progress;

    const combo = payload.combos?.find((item) => item.combo_group_id === group.combo_group_id);
    if (combo) {
      combo.progress_pct = null;
      delete combo.progress_pct_of_goal;
      delete combo.progress_pct_of_max;
      delete combo.progress;
    }

    server.use(
      http.get("*/positions/options", () => HttpResponse.json(payload)),
    );

    renderWithClient(<CombosTable />);

    await waitForElementToBeRemoved(() => screen.queryAllByTestId("skeleton-row"));

    const rowHeader = await screen.findByRole("rowheader", {
      name: /SPX 4250\/4300P \+ 4600\/4650C/i,
    });
    const row = rowHeader.closest("tr");
    if (!row) {
      throw new Error("expected row element");
    }
    const cells = within(row).getAllByRole("gridcell");
    const progressCell = cells.find((cell) => within(cell).queryByText("—"));
    if (!progressCell) {
      throw new Error("expected progress cell to contain em dash");
    }
    expect(within(progressCell).queryByRole("progressbar")).not.toBeInTheDocument();
    expect(within(progressCell).getByText("—")).toBeInTheDocument();
  });

  test("expanded detail row spans all columns", async () => {
    const user = userEvent.setup();
    renderWithClient(<CombosTable />);

    await waitForElementToBeRemoved(() => screen.queryAllByTestId("skeleton-row"));

    const firstRow = screen.getAllByRole("row", { name: /combo row/i })[0];
    const expandButton = within(firstRow).getByRole("button", { name: /expand group/i });

    await act(async () => {
      await user.click(expandButton);
    });

    const detailRow = await screen.findByRole("row", { name: /combo detail row/i });
    const detailCell = within(detailRow).getByRole("gridcell");
    expect(detailCell).toHaveAttribute("colspan", String(COLUMN_COUNT));
  });

  test("renders grouped combos with friendly labels and expands details", async () => {
    const user = userEvent.setup();
    renderWithClient(<CombosTable />);

    await waitForElementToBeRemoved(() => screen.queryAllByTestId("skeleton-row"));

    const groupRowHeader = await screen.findByRole("rowheader", {
      name: /SPX 4250\/4300P \+ 4600\/4650C • 32d • Credit 2\.21/i,
    });
    expect(groupRowHeader).toBeInTheDocument();
    expect(groupRowHeader.textContent).not.toMatch(/\d{6,8}[CP]\d{8}/);

    const expandButton = within(groupRowHeader.parentElement as HTMLElement).getByRole("button", {
      name: /expand group/i,
    });

    await act(async () => {
      await user.click(expandButton);
    });

    const detailRow = await screen.findByRole("row", { name: /combo detail row/i });
    const combosSection = within(detailRow).getByText(/^Combos$/i);
    expect(combosSection).toBeInTheDocument();
    expect(within(detailRow).getByText(/Credit 2\.21 • Qty -10/i)).toBeInTheDocument();

    const legChip = within(detailRow).getByText(/SPX 4600C • Oct 18 '24/i);
    expect(legChip).toBeInTheDocument();
    expect(legChip).toHaveAttribute("title", "SPX  20241018C00460000");
  });

  test("toggle reveals raw combos view", async () => {
    const user = userEvent.setup();
    renderWithClient(<CombosTable />);

    await waitForElementToBeRemoved(() => screen.queryAllByTestId("skeleton-row"));

    const toggle = screen.getByRole("checkbox", { name: /show raw combos/i });
    await act(async () => {
      await user.click(toggle);
    });

    const rawRowHeader = await screen.findByRole("rowheader", {
      name: /AAPL 195C CAL • Sep→Nov • Debit 4\.40/i,
    });
    expect(rawRowHeader).toBeInTheDocument();

    const expandButton = within(rawRowHeader.parentElement as HTMLElement).getByRole("button", {
      name: /expand combo/i,
    });

    await act(async () => {
      await user.click(expandButton);
    });

    expect(await screen.findByText(/AAPL 195C • Nov 15 '24/)).toBeInTheDocument();
  });

  test("supports keyboard navigation across rows", async () => {
    const user = userEvent.setup();
    renderWithClient(<CombosTable />);

    await waitForElementToBeRemoved(() => screen.queryAllByTestId("skeleton-row"));

    const body = screen.getByTestId("rows-body");
    const dataRows = within(body).getAllByRole("row", { name: /combo row/i });

    await act(async () => {
      await user.click(dataRows[0]);
    });

    await waitFor(() => expect(document.activeElement).toHaveAttribute("data-row-index", "0"));

    await act(async () => {
      await user.keyboard("{ArrowDown}");
    });
    await waitFor(() => expect(document.activeElement).toHaveAttribute("data-row-index", "1"));

    await act(async () => {
      await user.keyboard("{Home}");
    });
    await waitFor(() => expect(document.activeElement).toHaveAttribute("data-row-index", "0"));
  });

  test("filter chips narrow combos by playbook predicates", async () => {
    const user = userEvent.setup();
    renderWithClient(<CombosTable />);

    await waitForElementToBeRemoved(() => screen.queryAllByTestId("skeleton-row"));

    const getRowHeaders = () =>
      screen
        .getAllByRole("row", { name: /combo row/i })
        .map((row) => within(row).getByRole("rowheader").textContent ?? "");

    const getGridCells = () =>
      screen.getAllByRole("row", { name: /combo row/i }).map((row) => ({
        row,
        cells: within(row).getAllByRole("gridcell"),
      }));

    const clickChip = async (label: string) => {
      const chip = screen.getByRole("button", { name: label });
      await user.click(chip);
    };

    const clickReset = async () => {
      const reset = screen.getByRole("button", { name: /reset/i });
      await user.click(reset);
    };

    const initialHeaders = getRowHeaders();
    expect(initialHeaders.length).toBeGreaterThanOrEqual(6);

    await clickChip("TP Hit");
    await waitFor(() => expect(getRowHeaders()).toHaveLength(1));
    expect(getRowHeaders()[0]).toMatch(/SPX .*Credit 2\.21/);
    await clickReset();

    await clickChip("TP Done");
    await waitFor(() => expect(getRowHeaders()).toHaveLength(1));
    expect(getRowHeaders()[0]).toMatch(/MSFT .*Debit 1\.85/);
    await clickReset();

    await clickChip("Stop");
    await waitFor(() => expect(getRowHeaders()).toHaveLength(1));
    expect(getRowHeaders()[0]).toMatch(/ES .*Credit 1\.15/);
    await clickReset();

    await clickChip("Near TP");
    await waitFor(() => expect(getRowHeaders()).toHaveLength(2));
    const nearHeaders = getRowHeaders();
    expect(nearHeaders.some((text) => /IWM .*Credit 0\.76/.test(text))).toBe(true);
    expect(nearHeaders.some((text) => /RUT .*Debit 2\.40/.test(text))).toBe(true);
    await clickReset();

    await clickChip("Credit");
    await waitFor(() => expect(getRowHeaders()).toHaveLength(3));
    const creditCells = getGridCells();
    creditCells.forEach(({ cells }) => {
      expect(cells[3].textContent ?? "").toMatch(/Credit/i);
    });
    await clickReset();

    await clickChip("Debit");
    await waitFor(() => expect(getRowHeaders()).toHaveLength(3));
    const debitCells = getGridCells();
    debitCells.forEach(({ cells }) => {
      expect(cells[3].textContent ?? "").toMatch(/Debit/i);
    });
    await clickReset();

    await clickChip("DTE < 14d");
    await waitFor(() => expect(getRowHeaders()).toHaveLength(2));
    const shortDteCells = getGridCells();
    shortDteCells.forEach(({ cells }) => {
      const value = Number.parseInt((cells[1].textContent ?? "0").replace(/d$/, ""), 10);
      expect(Number.isNaN(value)).toBe(false);
      expect(value).toBeLessThan(14);
    });
    await clickReset();

    await waitFor(() => expect(getRowHeaders()).toHaveLength(initialHeaders.length));
  });

  test("shows dashes instead of $0.00 when mark or P&L are missing", async () => {
    const payload = mockOptions();
    const group = payload.combo_groups?.[0];
    if (!group) {
      throw new Error("expected combo group in payload");
    }
    group.group_mark = null;
    group.group_mark_price = null;
    group.mark_price = null;
    group.mark = null;
    group.group_pnl_unrealized = null;
    group.mark_source = "MISSING";

    server.use(
      http.get("*/positions/options", () => HttpResponse.json(payload)),
    );

    renderWithClient(<CombosTable />);

    await waitForElementToBeRemoved(() => screen.queryAllByTestId("skeleton-row"));

    const rowElement = screen.getAllByRole("row", { name: /combo row/i })[0];
    const headerCell = within(rowElement).getByRole("rowheader");
    const gridCells = within(rowElement).getAllByRole("gridcell");
    const cells = [headerCell, ...gridCells];

    expect(cells[8]).toHaveTextContent("—");
    expect((cells[8].textContent ?? "")).not.toContain("$0.00");
    expect(cells[9]).toHaveTextContent("—");
    expect((cells[9].textContent ?? "")).not.toContain("$0.00");
  });

  test("fallback grouping preserves highest priority mark source", async () => {
    const base = buildOptionsResponse({ combo_groups: [] });
    const condor = base.combos[0];
    const condorLegs = base.legs.filter((leg) => leg.combo_id === condor.id);

    const cloneCombo = (id: string, markSource: MarkSource) => {
      const clonedLegs = condorLegs.map((leg) => ({
        ...leg,
        id: `${leg.id}-${id}`,
        combo_id: id,
        combo_group_id: null,
      }));
      return {
        ...condor,
        id,
        combo_id: id,
        combo_group_id: null,
        mark_source: markSource,
        mark_time: base.as_of ?? new Date().toISOString(),
        legs: clonedLegs,
      };
    };

    const midCombo = cloneCombo("combo-iron-condor-mid", "MID");
    const prevCombo = cloneCombo("combo-iron-condor-prev", "PREV");

    const payload = {
      ...base,
      combos: [midCombo, prevCombo],
      legs: [...midCombo.legs, ...prevCombo.legs],
      combo_groups: [],
    };

    server.use(
      http.get("*/positions/options", () => HttpResponse.json(payload)),
    );

    renderWithClient(<GroupMarkProbe />);

    const marks = await screen.findAllByTestId("group-mark");
    expect(marks).toHaveLength(1);
    expect(marks[0]).toHaveTextContent("MID");
  });
});
