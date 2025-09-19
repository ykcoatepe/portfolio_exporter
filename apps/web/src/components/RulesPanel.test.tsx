import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, test } from "vitest";

import { RulesPanel } from "./RulesPanel";
import { buildRulesSummaryResponse } from "../mocks/handlers";
import { server } from "../mocks/server";
import { renderWithClient } from "../test/queryClient";

describe("RulesPanel", () => {
  test("renders counters, top breaches, and fundamentals tiles", async () => {
    renderWithClient(<RulesPanel />);

    const listItems = await screen.findAllByRole("listitem", { name: /breach/i });
    expect(listItems).toHaveLength(5);

    const countersHeader = screen.getByText(/rules/i).closest("header");
    expect(countersHeader).not.toBeNull();
    if (countersHeader) {
      expect(countersHeader.textContent).toMatch(/5/);
      expect(countersHeader.textContent).toMatch(/Critical/);
    }

    expect(screen.getByText(/portfolio var limit/i)).toBeInTheDocument();
    expect(screen.getByText(/tsla delta exposure/i)).toBeInTheDocument();

    const tiles = await screen.findAllByRole("group", { name: /fundamentals for/i });
    expect(tiles).toHaveLength(5);
    expect(tiles[0]).toHaveTextContent(/Market Cap/i);
    expect(tiles[0]).toHaveTextContent(/Dividend Yield/i);
  });

  test("supports keyboard navigation across the breaches list", async () => {
    const user = userEvent.setup();
    renderWithClient(<RulesPanel />);

    const listItems = await screen.findAllByRole("listitem", { name: /breach/i });
    expect(listItems.length).toBeGreaterThan(1);

    await act(async () => {
      await user.click(listItems[0]);
    });
    await waitFor(() => expect(listItems[0]).toHaveFocus());

    await act(async () => {
      await user.keyboard("{ArrowDown}");
    });
    await waitFor(() => expect(listItems[1]).toHaveFocus());

    await act(async () => {
      await user.keyboard("{End}");
    });
    await waitFor(() => expect(listItems[listItems.length - 1]).toHaveFocus());

    await act(async () => {
      await user.keyboard("{Home}");
    });
    await waitFor(() => expect(listItems[0]).toHaveFocus());
  });

  test("renders empty state when no breaches are present", async () => {
    server.use(
      http.get("*/rules/summary", () =>
        HttpResponse.json(
          buildRulesSummaryResponse({
            top: [],
            counters: { total: 0, critical: 0, warning: 0, info: 0 },
            focus_symbols: [],
          }),
        ),
      ),
    );

    renderWithClient(<RulesPanel />);

    await screen.findByText(/no active breaches/i);
    expect(screen.getByText(/select a rule breach/i)).toBeInTheDocument();
  });

  test("surfaces error state and retries on demand", async () => {
    const user = userEvent.setup();
    server.use(
      http.get("*/rules/summary", () => HttpResponse.json({ error: "boom" }, { status: 500 })),
    );

    renderWithClient(<RulesPanel />);

    const retryButton = await screen.findByRole("button", { name: /retry/i });
    expect(retryButton).toBeInTheDocument();

    server.use(
      http.get("*/rules/summary", () => HttpResponse.json(buildRulesSummaryResponse())),
    );

    await act(async () => {
      await user.click(retryButton);
    });

    await waitFor(() => {
      expect(screen.getByText(/top breaches/i)).toBeInTheDocument();
    });
  });
});
