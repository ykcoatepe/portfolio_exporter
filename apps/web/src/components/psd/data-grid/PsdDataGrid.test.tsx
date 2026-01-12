import { useState } from "react";
import type { ColumnDef, ColumnFiltersState } from "@tanstack/react-table";
import { render, screen, waitFor, act } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test, vi } from "vitest";

import { PsdDataGrid } from "./PsdDataGrid";

type StockRow = {
  id: string;
  symbol: string;
  quantity: number;
};

const columns: ColumnDef<StockRow>[] = [
  {
    id: "symbol",
    accessorKey: "symbol",
    header: "Symbol",
    filterFn: "psdString",
  },
  {
    id: "quantity",
    accessorKey: "quantity",
    header: "Qty",
    filterFn: "psdNumber",
  },
];

const rows: StockRow[] = [
  { id: "row:a", symbol: "AAPL", quantity: 10 },
  { id: "row:b", symbol: "TSLA", quantity: 20 },
  { id: "row:c", symbol: "NVDA", quantity: 30 },
];

function TestGrid(): JSX.Element {
  const [selectedIds, setSelectedIds] = useState<Set<string>>(
    new Set(["row:a", "row:b"]),
  );
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([]);

  return (
    <div>
      <button
        type="button"
        onClick={() => setColumnFilters([{ id: "symbol", value: "AAPL" }])}
      >
        Apply Filter
      </button>
      <PsdDataGrid
        data={rows}
        columns={columns}
        getRowId={(row) => row.id}
        ariaLabel="Test Grid"
        enableSelection={true}
        selectedRowIds={selectedIds}
        onSelectedRowIdsChange={setSelectedIds}
        columnFilters={columnFilters}
        onColumnFiltersChange={setColumnFilters}
        isDataStable={true}
        height="200px"
      />
      <div data-testid="selected-count">{selectedIds.size}</div>
    </div>
  );
}

describe("PsdDataGrid selection pruning", () => {
  test("prunes selection to visible rows after filtering", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });

    render(<TestGrid />);

    // Verify initial state
    expect(screen.getByTestId("selected-count")).toHaveTextContent("2");

    // Verify grid renders
    expect(screen.getByRole("grid", { name: /test grid/i })).toBeInTheDocument();
    expect(screen.getAllByRole("row").length).toBeGreaterThan(1); // header + data rows

    // Click on first data row to establish focus
    const allRows = screen.getAllByRole("row");
    const firstDataRow = allRows.find((r) => r.getAttribute("data-rowid") === "row:a");
    expect(firstDataRow).toBeTruthy();

    await act(async () => {
      await user.click(firstDataRow!);
      vi.advanceTimersByTime(100);
    });

    // Apply filter
    await act(async () => {
      await user.click(screen.getByRole("button", { name: /apply filter/i }));
      vi.advanceTimersByTime(100);
    });

    // Selection should be pruned to only visible rows (AAPL)
    await waitFor(
      () => expect(screen.getByTestId("selected-count")).toHaveTextContent("1"),
      { timeout: 1000 },
    );

    const selectedRows = screen.getAllByRole("row").filter((row) =>
      row.getAttribute("aria-selected") === "true",
    );
    expect(selectedRows).toHaveLength(1);
    expect(selectedRows[0]).toHaveTextContent("AAPL");

    vi.useRealTimers();
  });
});
