/**
 * PSD Stocks Grid
 *
 * Read-only virtualized grid for single stocks positions.
 * Uses PsdDataGrid with stock-specific columns and row identity.
 */

import type { ColumnDef, ColumnFiltersState, OnChangeFn } from "@tanstack/react-table";
import type { StockRow } from "./mappers";
import { PsdDataGrid } from "./PsdDataGrid";

// Define grid-specific columns inline to avoid type conflicts with lib/types StockRow
const gridStockColumns: ColumnDef<StockRow>[] = [
    {
        id: "symbol",
        accessorKey: "symbol",
        header: "Symbol",
        size: 100,
        filterFn: "psdString",
        meta: { align: "left", sortable: true },
    },
    {
        id: "quantity",
        accessorKey: "quantity",
        header: "Qty",
        size: 80,
        sortingFn: "basic",
        sortUndefined: "last",
        filterFn: "psdNumber",
        meta: { align: "right", numeric: true, sortable: true },
    },
    {
        id: "markPrice",
        accessorKey: "markPrice",
        header: "Mark",
        size: 90,
        sortingFn: "basic",
        sortUndefined: "last",
        filterFn: "psdNumber",
        meta: { align: "right", numeric: true, sortable: true },
    },
    {
        id: "dayPnlAmount",
        accessorKey: "dayPnlAmount",
        header: "Day P&L",
        size: 100,
        sortingFn: "basic",
        sortUndefined: "last",
        filterFn: "psdNumber",
        meta: { align: "right", numeric: true, sortable: true },
    },
    {
        id: "priceSource",
        accessorKey: "priceSource",
        header: "Source",
        size: 80,
        meta: { align: "left" },
    },
];

interface PsdStocksGridProps {
    /** Stock row data */
    data: StockRow[];
    /** Optional height (CSS value) */
    height?: string | number;
    /** Optional className */
    className?: string;
    /** Controlled column filters */
    columnFilters?: ColumnFiltersState;
    /** Column filter change handler */
    onColumnFiltersChange?: OnChangeFn<ColumnFiltersState>;
    /** Whether data is stable (no transient refetch empty state) */
    isDataStable?: boolean;
}

/**
 * Stable row ID using id field (formatted as "stock:{conId ?? symbol}")
 */
function getStockRowId(row: StockRow): string {
    return row.id;
}

export function PsdStocksGrid({
    data,
    height = "400px",
    className,
    columnFilters,
    onColumnFiltersChange,
    isDataStable,
}: PsdStocksGridProps): JSX.Element {
    return (
        <PsdDataGrid
            data={data}
            columns={gridStockColumns}
            getRowId={getStockRowId}
            ariaLabel="Single Stocks"
            height={height}
            className={className}
            emptyMessage="No stock positions"
            enableSelection={true}
            columnFilters={columnFilters}
            onColumnFiltersChange={onColumnFiltersChange}
            isDataStable={isDataStable}
        />
    );
}

export default PsdStocksGrid;
