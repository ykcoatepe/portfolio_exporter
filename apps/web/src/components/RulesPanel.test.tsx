import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { QueryClient } from "@tanstack/react-query";
import { describe, expect, test, afterEach, beforeEach } from "vitest";

import { RulesPanel } from "./RulesPanel";
import { buildRulesSummaryResponse, resetCatalogState } from "../mocks/handlers";
import { server } from "../mocks/server";
import { renderWithClient } from "../test/queryClient";

let activeClient: QueryClient | null = null;

beforeEach(() => {
  resetCatalogState();
  activeClient = null;
});

afterEach(() => {
  activeClient?.clear();
  activeClient = null;
});

describe("RulesPanel", () => {
  test("renders counters, top breaches, and fundamentals tiles", async () => {
    const { client } = renderWithClient(<RulesPanel />);
    activeClient = client;

    const listItems = await screen.findAllByRole("listitem", { name: /breach/i });
    expect(listItems).toHaveLength(5);

    const countersSection = await screen.findByRole("region", { name: /rules summary/i });
    expect(countersSection).toHaveTextContent(/Rules Catalog/i);
    expect(countersSection).toHaveTextContent(/5/);
    const criticalBadges = within(countersSection).getAllByText(/Critical/i);
    expect(criticalBadges.length).toBeGreaterThan(0);

    expect(await screen.findByText(/portfolio var limit/i)).toBeInTheDocument();
    expect(await screen.findByText(/tsla delta exposure/i)).toBeInTheDocument();

    expect(await screen.findByText(/Rules v12/i)).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /Reload/i })).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /Validate & Publish/i })).toBeInTheDocument();

    const tiles = await screen.findAllByRole("group", { name: /fundamentals for/i });
    expect(tiles).toHaveLength(5);
    expect(tiles[0]).toHaveTextContent(/Market Cap/i);
    expect(tiles[0]).toHaveTextContent(/Dividend Yield/i);
  });

  test("supports keyboard navigation across the breaches list", async () => {
    const user = userEvent.setup();
    const { client } = renderWithClient(<RulesPanel />);
    activeClient = client;

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

  test("validates and publishes catalog updates", async () => {
    const user = userEvent.setup();
    const { client } = renderWithClient(<RulesPanel />);
    activeClient = client;

    await screen.findByText(/Rules v12/i);

    const validateAndPublishButton = await screen.findByRole("button", { name: /Validate & Publish/i });
    await act(async () => {
      await user.click(validateAndPublishButton);
    });

    const textarea = await screen.findByLabelText(/Catalog YAML/i);
    await user.clear(textarea);
    await act(async () => {
      fireEvent.change(textarea, { target: { value: "rules: []" } });
    });

    const validateButton = await screen.findByRole("button", { name: /^Validate$/i });
    await act(async () => {
      await user.click(validateButton);
    });

    await screen.findByText(/Validation passed/i);
    expect(await screen.findByText(/Catalog diff/i)).toBeInTheDocument();

    const publishButton = await screen.findByRole("button", { name: /^Publish$/i });
    expect(publishButton).not.toBeDisabled();

    await act(async () => {
      await user.click(publishButton);
    });

    await waitFor(() => {
      expect(screen.queryByLabelText(/Catalog YAML/i)).not.toBeInTheDocument();
    });

    await screen.findByText(/Rules v13/i);
  });

  test("renders empty state when no breaches are present", async () => {
    server.use(
      http.get("*/rules/summary", () =>
        HttpResponse.json(
          buildRulesSummaryResponse({
            top: [],
            breaches: { total: 0, critical: 0, warning: 0, info: 0 },
            focus_symbols: [],
          }),
        ),
      ),
    );

    const { client } = renderWithClient(<RulesPanel />);
    activeClient = client;

    await screen.findByText(/no active breaches/i);
    expect(await screen.findByText(/select a rule breach/i)).toBeInTheDocument();
  });

  test("surfaces error state and retries on demand", async () => {
    const user = userEvent.setup();
    server.use(
      http.get("*/rules/summary", () => HttpResponse.json({ error: "boom" }, { status: 500 })),
    );

    const { client } = renderWithClient(<RulesPanel />);
    activeClient = client;

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
