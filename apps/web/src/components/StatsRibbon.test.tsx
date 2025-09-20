import { screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, test, vi } from "vitest";

import StatsRibbon from "./StatsRibbon";
import { buildPsdSnapshot, buildStatsResponse } from "../mocks/handlers";
import { server } from "../mocks/server";
import { renderWithClient } from "../test/queryClient";

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
            updated_at: "2024-02-01T11:59:00Z",
          }),
        ),
      ),
      http.get("*/state", () => HttpResponse.json(buildPsdSnapshot({ ts: snapshotSeconds }))),
    );

    renderWithClient(<StatsRibbon />);

    expect(await screen.findByText(/7 minutes ago/i)).toBeInTheDocument();

    dateNowSpy.mockRestore();
  });

  test("renders placeholders for optional stats fields when data is absent", async () => {
    const snapshot = buildPsdSnapshot({
      ts: Date.parse("2024-03-01T15:00:00Z"),
    });

    server.use(
      http.get("*/stats", () =>
        HttpResponse.json(
          buildStatsResponse({
            net_liq: null,
            var95_1d_pct: null,
            margin_used_pct: null,
            updated_at: null,
          }),
        ),
      ),
      http.get("*/state", () => HttpResponse.json(snapshot)),
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
});
