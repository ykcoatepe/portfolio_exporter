/**
 * PSD Option Legs Grid
 *
 * Read-only virtualized grid for single option legs positions.
 * Uses PsdDataGrid with PSD option-leg columns and row identity.
 */

import type { SortingState, OnChangeFn } from "@tanstack/react-table";
import type { OptionLegRow } from "./mappers";
import { PsdDataGrid } from "./PsdDataGrid";
import { psdOptionLegColumns } from "./columns";

interface PsdOptionLegsGridProps {
    /** Option leg row data */
    data: OptionLegRow[];
    /** Optional height (CSS value) */
    height?: string | number;
    /** Optional className */
    className?: string;
    /** Controlled sorting state */
    sorting?: SortingState;
    /** Sorting change handler */
    onSortingChange?: OnChangeFn<SortingState>;
    /** Whether data is stable (no transient refetch empty state) */
    isDataStable?: boolean;
}

/**
 * Stable row ID using id field (formatted as "leg:{conId ?? symbol}")
 */
function getOptionLegRowId(row: OptionLegRow): string {
    return row.id;
}

export function PsdOptionLegsGrid({
    data,
    height = "350px",
    className,
    sorting,
    onSortingChange,
    isDataStable,
}: PsdOptionLegsGridProps): JSX.Element {
    return (
        <PsdDataGrid
            data={data}
            columns={psdOptionLegColumns}
            getRowId={getOptionLegRowId}
            ariaLabel="Options — Singles"
            height={height}
            className={className}
            emptyMessage="No option legs"
            enableSelection={false}
            sorting={sorting}
            onSortingChange={onSortingChange}
            isDataStable={isDataStable}
        />
    );
}

export default PsdOptionLegsGrid;
