import type { ColumnDef } from "@tanstack/react-table";
import { render, screen } from "@testing-library/react";
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
  },
  {
    id: "quantity",
    accessorKey: "quantity",
    header: "Qty",
  },
];

const rows: StockRow[] = [
  { id: "row:a", symbol: "AAPL", quantity: 10 },
  { id: "row:b", symbol: "TSLA", quantity: 20 },
  { id: "row:c", symbol: "NVDA", quantity: 30 },
];

describe("PsdDataGrid", () => {
  test("renders grid with data", () => {
    render(
      <PsdDataGrid
        data={rows}
        columns={columns}
        getRowId={(row) => row.id}
        ariaLabel="Test Grid"
        height="200px"
      />
    );

    expect(screen.getByRole("grid", { name: /test grid/i })).toBeInTheDocument();
    expect(screen.getByText("AAPL")).toBeInTheDocument();
    expect(screen.getByText("TSLA")).toBeInTheDocument();
    expect(screen.getByText("NVDA")).toBeInTheDocument();
  });

  test("shows selection state visually", () => {
    const selectedIds = new Set(["row:a"]);

    render(
      <PsdDataGrid
        data={rows}
        columns={columns}
        getRowId={(row) => row.id}
        ariaLabel="Test Grid"
        enableSelection={true}
        selectedRowIds={selectedIds}
        height="200px"
      />
    );

    // Find data rows (rows with data-rowid attribute)
    const dataRows = screen.getAllByRole("row").filter(r => r.getAttribute("data-rowid"));
    expect(dataRows).toHaveLength(3);

    // First row (AAPL) should be selected
    const aaplRow = dataRows.find(r => r.getAttribute("data-rowid") === "row:a");
    expect(aaplRow).toHaveAttribute("aria-selected", "true");

    // Other rows should not be selected
    const tslaRow = dataRows.find(r => r.getAttribute("data-rowid") === "row:b");
    expect(tslaRow).toHaveAttribute("aria-selected", "false");
  });
});
