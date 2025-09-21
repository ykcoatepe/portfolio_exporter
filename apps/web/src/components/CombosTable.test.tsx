import { act, screen, waitFor, waitForElementToBeRemoved, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { CombosTable } from "./CombosTable";
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
    expect(legChip).toHaveAttribute("title", "SPX20241018C00460000");
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
