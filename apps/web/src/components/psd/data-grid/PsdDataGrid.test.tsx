import { useState } from "react";
import type { ColumnDef, ColumnFiltersState } from "@tanstack/react-table";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, test } from "vitest";

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
    const user = userEvent.setup();
    render(<TestGrid />);

    expect(screen.getByTestId("selected-count")).toHaveTextContent("2");

    for (let i = 0; i < 3; i += 1) {
      const activeRole = document.activeElement?.getAttribute("role");
      if (
        activeRole === "grid" ||
        activeRole === "gridcell" ||
        activeRole === "row"
      ) {
        break;
      }
      await user.tab();
    }

    await waitFor(() =>
      expect(document.activeElement?.getAttribute("data-rowid")).toBe("row:a"),
    );
    await user.keyboard("{ArrowDown}");

    await user.click(screen.getByRole("button", { name: /apply filter/i }));

    await waitFor(() =>
      expect(screen.getByTestId("selected-count")).toHaveTextContent("1"),
    );

    const selectedRows = screen.getAllByRole("row").filter((row) =>
      row.getAttribute("aria-selected") === "true",
    );
    expect(selectedRows).toHaveLength(1);
    expect(selectedRows[0]).toHaveTextContent("AAPL");

    await waitFor(() =>
      expect(document.activeElement?.getAttribute("data-rowid")).toBe("row:a"),
    );
  });
});
