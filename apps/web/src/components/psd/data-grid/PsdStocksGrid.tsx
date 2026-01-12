/**
 * PSD Stocks Grid
 *
 * Read-only virtualized grid for single stocks positions.
 * Uses PsdDataGrid with stock-specific columns and row identity.
 */

import type { ColumnFiltersState, SortingState, OnChangeFn } from "@tanstack/react-table";
import type { StockRow } from "./mappers";
import { PsdDataGrid } from "./PsdDataGrid";
import { stockColumns } from "./columns";

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
    /** Controlled sorting state */
    sorting?: SortingState;
    /** Sorting change handler */
    onSortingChange?: OnChangeFn<SortingState>;
    /** Whether data is stable (no transient refetch empty state) */
    isDataStable?: boolean;
    /** Selected row IDs (controlled) */
    selectedRowIds?: Set<string>;
    /** Callback when selection changes */
    onSelectedRowIdsChange?: (ids: Set<string>) => void;
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
    sorting,
    onSortingChange,
    isDataStable,
    selectedRowIds,
    onSelectedRowIdsChange,
}: PsdStocksGridProps): JSX.Element {
    return (
        <PsdDataGrid
            data={data}
            columns={stockColumns}
            getRowId={getStockRowId}
            ariaLabel="Single Stocks"
            height={height}
            className={className}
            emptyMessage="No stock positions"
            enableSelection={true}
            columnFilters={columnFilters}
            onColumnFiltersChange={onColumnFiltersChange}
            sorting={sorting}
            onSortingChange={onSortingChange}
            isDataStable={isDataStable}
            selectedRowIds={selectedRowIds}
            onSelectedRowIdsChange={onSelectedRowIdsChange}
        />
    );
}

export default PsdStocksGrid;
