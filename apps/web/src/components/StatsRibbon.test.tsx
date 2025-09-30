import { act, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, test, vi } from "vitest";

import StatsRibbon from "./StatsRibbon";
import { buildPsdSnapshot, buildStatsResponse } from "../mocks/handlers";
import { server } from "../mocks/server";
import { renderWithClient } from "../test/queryClient";
import type { MarketSessionApiResponse } from "../lib/types";

const buildSessionPayload = (
  state: "RTH" | "ETH" | "CLOSED",
  overrides: Partial<MarketSessionApiResponse> = {},
): MarketSessionApiResponse => ({
  exchange: overrides.exchange ?? "XNYS",
  tz: overrides.tz ?? "America/New_York",
  state,
  as_of: overrides.as_of ?? "2024-02-01T12:00:00-05:00",
  rth_open: overrides.rth_open ?? "2024-02-01T09:30:00-05:00",
  rth_close: overrides.rth_close ?? "2024-02-01T16:00:00-05:00",
  source: overrides.source ?? "fallback",
  note: overrides.note ?? null,
});

describe("StatsRibbon", () => {
  test("normalizes PSD snapshot epoch seconds before computing recency", async () => {
    const snapshotSeconds = Math.floor(Date.parse("2024-02-01T12:00:00Z") / 1000);
    const nowMs = Date.parse("2024-02-01T12:07:00Z");
    const dateNowSpy = vi.spyOn(Date, "now").mockReturnValue(nowMs);

    server.use(
      http.get("*/stats", () =>
        HttpResponse.json(
          buildStatsResponse({
            net_liq: 1_000_000,
            var95_1d_pct: 50_000,
            margin_used_pct: 0.2,
            updated_at: null,
            session: buildSessionPayload("RTH", { as_of: "2024-02-01T11:55:00Z" }),
            session_info: buildSessionPayload("RTH", { as_of: "2024-02-01T11:55:00Z" }),
            meta: { latest_ts: null },
          }),
        ),
      ),
      http.get("*/state", () => HttpResponse.json(buildPsdSnapshot({ ts: snapshotSeconds }))),
      http.get("*/session", () =>
        HttpResponse.json(buildSessionPayload("RTH", { as_of: "2024-02-01T12:05:00Z" })),
      ),
    );

    renderWithClient(<StatsRibbon />);

    expect(await screen.findByText(/7 minutes ago/i)).toBeInTheDocument();

    dateNowSpy.mockRestore();
  });

  test("renders placeholders for optional stats fields when data is absent", async () => {
    const snapshot = buildPsdSnapshot({
      ts: null,
    });

    server.use(
      http.get("*/stats", () =>
        HttpResponse.json(
          buildStatsResponse({
            net_liq: null,
            var95_1d_pct: null,
            margin_used_pct: null,
            margin_pct: null,
            updated_at: null,
            session: null,
            session_info: null,
            meta: { latest_ts: null },
          }),
        ),
      ),
      http.get("*/state", () => HttpResponse.json(snapshot)),
      http.get("*/session", () => HttpResponse.json(buildSessionPayload("RTH"))),
    );

    renderWithClient(<StatsRibbon />);

    const statsRegion = await screen.findByRole("region", { name: /portfolio stats/i });

    const valueFor = (label: string) => {
      const term = within(statsRegion).getByText(label, { selector: "dt" });
      const definition = term.parentElement?.querySelector(
        "dd[data-testid='stat-value']",
      ) as HTMLElement | null;
      expect(definition).not.toBeNull();
      return definition!.textContent?.trim();
    };

    expect(valueFor("Net Liq")).toBe("—");
    expect(valueFor("VaR 95%")).toBe("—");
    expect(valueFor("Margin %")).toBe("—");
    expect(valueFor("Updated")).toBe("—");
  });

  test("updates card when latestTs changes", async () => {
    const nowMs = Date.parse("2024-02-01T12:05:00Z");
    const dateNowSpy = vi.spyOn(Date, "now").mockReturnValue(nowMs);
    let calls = 0;

    server.use(
      http.get("*/stats", () => {
        calls += 1;
        const latest = calls === 1 ? "2024-02-01T12:00:00Z" : "2024-02-01T12:04:00Z";
        return HttpResponse.json(
          buildStatsResponse({
            meta: { latest_ts: latest },
            updated_at: latest,
            session: buildSessionPayload("RTH", { as_of: latest }),
            session_info: buildSessionPayload("RTH", { as_of: latest }),
          }),
        );
      }),
      http.get("*/state", () => HttpResponse.json(buildPsdSnapshot())),
      http.get("*/session", () => HttpResponse.json(buildSessionPayload("RTH"))),
    );

    const { client } = renderWithClient(<StatsRibbon />);

    const getUpdatedValue = () => {
      const statsRegion = screen.getByRole("region", { name: /portfolio stats/i });
      const updatedTerm = within(statsRegion).getByText("Updated", { selector: "dt" });
      const valueNode = updatedTerm.parentElement?.querySelector(
        "dd[data-testid='stat-value']",
      ) as HTMLElement | null;
      expect(valueNode).not.toBeNull();
      return valueNode!.textContent?.trim();
    };

    await waitFor(() => expect(getUpdatedValue()).toBe("5 minutes ago"));

    await act(async () => {
      await client.invalidateQueries({ queryKey: ["portfolio", "stats"] });
    });

    await waitFor(() => expect(getUpdatedValue()).toBe("1 minute ago"));

    dateNowSpy.mockRestore();
  });

  test("prefers stats session when available", async () => {
    const now = Date.parse("2024-04-01T13:05:00Z");
    const dateNowSpy = vi.spyOn(Date, "now").mockReturnValue(now);

    server.use(
      http.get("*/stats", () =>
        HttpResponse.json(
          buildStatsResponse({
            session: buildSessionPayload("RTH", {
              as_of: "2024-04-01T13:00:00Z",
              source: "stats",
            }),
          }),
        ),
      ),
      http.get("*/state", () => HttpResponse.json(buildPsdSnapshot())),
      http.get("*/session", () =>
        HttpResponse.json(
          buildSessionPayload("ETH", {
            as_of: "2024-04-01T06:55:00Z",
            source: "endpoint",
          }),
        ),
      ),
    );

    renderWithClient(<StatsRibbon />);

    const sessionLabelNode = await screen.findByText(/SESSION: RTH/i);
    const sessionContainer = sessionLabelNode.parentElement as HTMLElement;
    expect(sessionContainer).not.toBeNull();
    expect(within(sessionContainer).getByText(/updated/i)).toBeInTheDocument();

    dateNowSpy.mockRestore();
  });

  test("falls back to session endpoint when stats session is missing", async () => {
    const now = Date.parse("2024-04-01T13:05:00Z");
    const dateNowSpy = vi.spyOn(Date, "now").mockReturnValue(now);

    server.use(
      http.get("*/stats", () =>
        HttpResponse.json(
          buildStatsResponse({
            session: null,
          }),
        ),
      ),
      http.get("*/state", () => HttpResponse.json(buildPsdSnapshot())),
      http.get("*/session", () =>
        HttpResponse.json(
          buildSessionPayload("ETH", {
            as_of: "2024-04-01T06:55:00Z",
            source: "endpoint",
          }),
        ),
      ),
    );

    renderWithClient(<StatsRibbon />);

    const sessionLabelNode = await screen.findByText(/SESSION: ETH/i);
    const sessionContainer = sessionLabelNode.parentElement as HTMLElement;
    expect(sessionContainer).not.toBeNull();
    expect(within(sessionContainer).getByText(/updated/i)).toBeInTheDocument();

    dateNowSpy.mockRestore();
  });

  test("falls back to em dash when session endpoint fails", async () => {
    server.use(
      http.get("*/stats", () => HttpResponse.json(buildStatsResponse({ session: null }))),
      http.get("*/state", () => HttpResponse.json(buildPsdSnapshot())),
      http.get("*/session", () => HttpResponse.json(null, { status: 503 })),
    );

    renderWithClient(<StatsRibbon />);

    const statsRegion = await screen.findByRole("region", { name: /portfolio stats/i });
    expect(within(statsRegion).getByText(/SESSION: —/i)).toBeInTheDocument();
    expect(within(statsRegion).getByText(/Day P&L/i)).toBeInTheDocument();
  });

  test("shows stats data source when available", async () => {
    server.use(
      http.get("*/stats", () =>
        HttpResponse.json(
          buildStatsResponse({
            data_source: "internal",
          }),
        ),
      ),
      http.get("*/state", () => HttpResponse.json(buildPsdSnapshot())),
      http.get("*/session", () => HttpResponse.json(buildSessionPayload("RTH"))),
    );

    renderWithClient(<StatsRibbon />);

    const chip = await screen.findByTestId("data-source-chip");
    expect(chip).toHaveTextContent(/DATA • internal/i);
  });

  test("shows em dash when stats omit data source", async () => {
    server.use(
      http.get("*/stats", () => {
        const response = buildStatsResponse();
        delete (response as { data_source?: string | null }).data_source;
        delete (response as { dataSource?: string | null }).dataSource;
        return HttpResponse.json(response);
      }),
      http.get("*/state", () => HttpResponse.json(buildPsdSnapshot())),
      http.get("*/session", () => HttpResponse.json(buildSessionPayload("RTH"))),
    );

    renderWithClient(<StatsRibbon />);

    const chip = await screen.findByTestId("data-source-chip");
    expect(chip).toHaveTextContent(/DATA • —/i);
  });

  test("shows em dash when stats request fails", async () => {
    server.use(
      http.get("*/stats", () => HttpResponse.json({ message: "boom" }, { status: 500 })),
      http.get("*/state", () => HttpResponse.json(buildPsdSnapshot())),
      http.get("*/session", () => HttpResponse.json(buildSessionPayload("RTH"))),
    );

    renderWithClient(<StatsRibbon />);

    const chip = await screen.findByTestId("data-source-chip");
    expect(chip).toHaveTextContent(/DATA • —/i);
  });
});
