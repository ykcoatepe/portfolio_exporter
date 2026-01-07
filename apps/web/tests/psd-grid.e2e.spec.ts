/**
 * PSD Grid Smoke Test
 *
 * Tests for the virtualized stocks grid:
 * - Keyboard navigation (ArrowDown moves focus)
 * - Scroll keeps focus inside grid
 * - Refetch on window focus maintains focus position
 */

import { test, expect } from "@playwright/test";

// Mock data fixtures
const STOCK_FIXTURE_A = {
    ts: Date.now(),
    session: "RTH",
    positions_view: {
        single_stocks: [
            { secType: "STK", symbol: "AAPL", qty: 100, mark: 150.25, pnl_intraday: 125.50, stale_s: 5, conId: 1001 },
            { secType: "STK", symbol: "TSLA", qty: 50, mark: 250.00, pnl_intraday: -75.00, stale_s: 10, conId: 1002 },
            { secType: "STK", symbol: "NVDA", qty: 75, mark: 450.50, pnl_intraday: 200.00, stale_s: 3, conId: 1003 },
            { secType: "STK", symbol: "MSFT", qty: 30, mark: 380.00, pnl_intraday: 50.25, stale_s: 8, conId: 1004 },
            { secType: "STK", symbol: "GOOG", qty: 20, mark: 140.00, pnl_intraday: -25.00, stale_s: 12, conId: 1005 },
        ],
        option_combos: [],
        single_options: [],
    },
};

const STOCK_FIXTURE_B = {
    ...STOCK_FIXTURE_A,
    ts: Date.now() + 5000,
    positions_view: {
        ...STOCK_FIXTURE_A.positions_view,
        single_stocks: STOCK_FIXTURE_A.positions_view.single_stocks.map((s) => ({
            ...s,
            pnl_intraday: s.pnl_intraday + 10, // Simulate P&L update
        })),
    },
};

const STATS_FIXTURE = {
    net_liq: 500000,
    var_95: 25000,
    margin_pct: 0.35,
    updated_at: new Date().toISOString(),
};

test.describe("PSD Stocks Grid", () => {
    test.beforeEach(async ({ page }) => {
        // Mock API endpoints
        await page.route("**/stats/current", (route) =>
            route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(STATS_FIXTURE) })
        );
        await page.route("**/stats", (route) =>
            route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(STATS_FIXTURE) })
        );
    });

    test("grid displays with new mode and supports arrow key navigation", async ({ page }) => {
        let callCount = 0;
        await page.route("**/state", async (route) => {
            callCount += 1;
            await route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify(callCount === 1 ? STOCK_FIXTURE_A : STOCK_FIXTURE_B),
            });
        });

        await page.goto("/psd?grid=new");

        // Wait for grid to render
        const grid = page.locator('[role="grid"]').first();
        await expect(grid).toBeVisible({ timeout: 10_000 });

        // Click first cell to focus
        const firstRow = page.locator('[data-rowid="stock:1001"]').first();
        await expect(firstRow).toBeVisible();
        await firstRow.click();

        // Arrow down should move focus
        await page.keyboard.press("ArrowDown");

        // Verify focus moved (active element still inside grid)
        const activeInGrid = await page.evaluate(() => {
            const active = document.activeElement;
            return !!active && !!active.closest?.('[role="grid"]');
        });
        expect(activeInGrid).toBeTruthy();
    });

    test("grid keeps focus inside after PageDown scroll", async ({ page }) => {
        await page.route("**/state", (route) =>
            route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(STOCK_FIXTURE_A) })
        );

        await page.goto("/psd?grid=new");

        const grid = page.locator('[role="grid"]').first();
        await expect(grid).toBeVisible({ timeout: 10_000 });

        // Focus first row
        const firstRow = page.locator('[data-rowid="stock:1001"]').first();
        await firstRow.click();

        // PageDown
        await page.keyboard.press("PageDown");

        // Focus should still be inside grid
        const activeInGrid = await page.evaluate(() => {
            const active = document.activeElement;
            return !!active && !!active.closest?.('[role="grid"]');
        });
        expect(activeInGrid).toBeTruthy();
    });

    test("focus remains in grid after data refetch", async ({ page }) => {
        let callCount = 0;
        await page.route("**/state", async (route) => {
            callCount += 1;
            await route.fulfill({
                status: 200,
                contentType: "application/json",
                body: JSON.stringify(callCount === 1 ? STOCK_FIXTURE_A : STOCK_FIXTURE_B),
            });
        });

        await page.goto("/psd?grid=new");

        const grid = page.locator('[role="grid"]').first();
        await expect(grid).toBeVisible({ timeout: 10_000 });

        // Focus a specific row
        const targetRow = page.locator('[data-rowid="stock:1002"]').first();
        await targetRow.click();

        // Record the focused rowId before refetch
        const rowIdBefore = await page.evaluate(() => {
            const active = document.activeElement;
            return active?.getAttribute("data-rowid") ?? active?.closest("[data-rowid]")?.getAttribute("data-rowid");
        });

        // Trigger refetchOnWindowFocus by dispatching focus event
        await page.evaluate(() => window.dispatchEvent(new Event("focus")));

        // Wait a bit for refetch to complete
        await page.waitForTimeout(500);

        // Verify focus stayed inside grid
        const activeInGrid = await page.evaluate(() => {
            const active = document.activeElement;
            return !!active && !!active.closest?.('[role="grid"]');
        });
        expect(activeInGrid).toBeTruthy();
    });

    test("click selects row with aria-selected", async ({ page }) => {
        await page.route("**/state", (route) =>
            route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(STOCK_FIXTURE_A) })
        );

        await page.goto("/psd?grid=new");

        const grid = page.locator('[role="grid"]').first();
        await expect(grid).toBeVisible({ timeout: 10_000 });

        // Click a row
        const targetRow = page.locator('[data-rowid="stock:1002"]').first();
        await targetRow.click();

        // Check aria-selected
        await expect(targetRow).toHaveAttribute("aria-selected", "true");

        // Check selection styling
        const hasSelectedClass = await targetRow.evaluate((el) =>
            el.classList.contains("psd-grid-row--selected")
        );
        expect(hasSelectedClass).toBeTruthy();
    });

    test("shift+click selects contiguous range", async ({ page }) => {
        await page.route("**/state", (route) =>
            route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(STOCK_FIXTURE_A) })
        );

        await page.goto("/psd?grid=new");

        const grid = page.locator('[role="grid"]').first();
        await expect(grid).toBeVisible({ timeout: 10_000 });

        // Click first row (anchor)
        const row1 = page.locator('[data-rowid="stock:1001"]').first();
        await row1.click();

        // Shift+click third row (extend range)
        const row3 = page.locator('[data-rowid="stock:1003"]').first();
        await row3.click({ modifiers: ["Shift"] });

        // All three rows should be selected
        await expect(row1).toHaveAttribute("aria-selected", "true");
        const row2 = page.locator('[data-rowid="stock:1002"]').first();
        await expect(row2).toHaveAttribute("aria-selected", "true");
        await expect(row3).toHaveAttribute("aria-selected", "true");
    });

    test("filter input narrows rows and clears selection", async ({ page }) => {
        await page.route("**/state", (route) =>
            route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(STOCK_FIXTURE_A) })
        );

        await page.goto("/psd?grid=new");

        const grid = page.locator('[role="grid"]').first();
        await expect(grid).toBeVisible({ timeout: 10_000 });

        const targetRow = page.locator('[data-rowid="stock:1002"]').first();
        await targetRow.click();
        await expect(targetRow).toHaveAttribute("aria-selected", "true");

        const filterInput = page.getByLabel("Filter symbols");
        await filterInput.fill("AAPL");

        await expect(page.locator('[data-rowid="stock:1002"]')).toHaveCount(0);
        await expect(page.locator('[role="row"][aria-selected=\"true\"]')).toHaveCount(0);
    });

    test("filter preserves selection for visible rows and context menu targets correctly", async ({ page }) => {
        await page.route("**/state", (route) =>
            route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(STOCK_FIXTURE_A) })
        );

        await page.goto("/psd?grid=new");

        const grid = page.locator('[role="grid"]').first();
        await expect(grid).toBeVisible({ timeout: 10_000 });

        const aaplRow = page.locator('[data-rowid="stock:1001"]').first();
        await aaplRow.click();
        await expect(aaplRow).toHaveAttribute("aria-selected", "true");

        const filterInput = page.getByLabel("Filter symbols");
        await filterInput.fill("AAPL");

        await expect(page.locator('[data-rowid="stock:1001"]')).toHaveCount(1);
        await expect(aaplRow).toHaveAttribute("aria-selected", "true");

        await aaplRow.click({ button: "right" });
        const menu = page.locator('[data-testid="grid-context-menu"]');
        await expect(menu).toBeVisible();
        await expect(menu).toContainText("AAPL");
    });

    test("selection persists after scroll", async ({ page }) => {
        await page.route("**/state", (route) =>
            route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(STOCK_FIXTURE_A) })
        );

        await page.goto("/psd?grid=new");

        const grid = page.locator('[role="grid"]').first();
        await expect(grid).toBeVisible({ timeout: 10_000 });

        // Select a row
        const targetRow = page.locator('[data-rowid="stock:1002"]').first();
        await targetRow.click();
        await expect(targetRow).toHaveAttribute("aria-selected", "true");

        // Scroll (PageDown)
        await page.keyboard.press("PageDown");

        // Scroll back (PageUp)
        await page.keyboard.press("PageUp");

        // Selection should still be present
        await expect(targetRow).toHaveAttribute("aria-selected", "true");
    });

    test("right-click opens context menu", async ({ page }) => {
        await page.route("**/state", (route) =>
            route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(STOCK_FIXTURE_A) })
        );

        await page.goto("/psd?grid=new");

        const grid = page.locator('[role="grid"]').first();
        await expect(grid).toBeVisible({ timeout: 10_000 });

        // Right-click a row
        const targetRow = page.locator('[data-rowid="stock:1002"]').first();
        await targetRow.click({ button: "right" });

        // Menu should appear
        const menu = page.locator('[data-testid="grid-context-menu"]');
        await expect(menu).toBeVisible();

        // Menu should have Copy Symbol button
        const copyBtn = page.locator('[data-testid="ctx-copy-symbol"]');
        await expect(copyBtn).toBeVisible();
    });

    test("multi-select + right-click shows count in menu", async ({ page }) => {
        await page.route("**/state", (route) =>
            route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(STOCK_FIXTURE_A) })
        );

        await page.goto("/psd?grid=new");

        const grid = page.locator('[role="grid"]').first();
        await expect(grid).toBeVisible({ timeout: 10_000 });

        // Select first row
        const row1 = page.locator('[data-rowid="stock:1001"]').first();
        await row1.click();

        // Shift+click third row for range
        const row3 = page.locator('[data-rowid="stock:1003"]').first();
        await row3.click({ modifiers: ["Shift"] });

        // Right-click selected row
        await row3.click({ button: "right" });

        // Menu should show count
        const menu = page.locator('[data-testid="grid-context-menu"]');
        await expect(menu).toContainText("3 rows selected");
    });

    test("context menu closes on Escape", async ({ page }) => {
        await page.route("**/state", (route) =>
            route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(STOCK_FIXTURE_A) })
        );

        await page.goto("/psd?grid=new");

        const grid = page.locator('[role="grid"]').first();
        await expect(grid).toBeVisible({ timeout: 10_000 });

        // Right-click a row
        const targetRow = page.locator('[data-rowid="stock:1002"]').first();
        await targetRow.click({ button: "right" });

        const menu = page.locator('[data-testid="grid-context-menu"]');
        await expect(menu).toBeVisible();

        // Press Escape
        await page.keyboard.press("Escape");

        // Menu should be hidden
        await expect(menu).not.toBeVisible();
    });
});
