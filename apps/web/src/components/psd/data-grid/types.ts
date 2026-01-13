/**
 * PSD Data Grid Types
 *
 * Type definitions for the virtualized data grid components.
 */

import type {
    RowData,
    Row,
    ColumnDef,
    Table,
    ColumnFiltersState,
    SortingState,
    OnChangeFn,
    FilterFn,
} from "@tanstack/react-table";

// Register custom filter functions with TanStack Table's type system
declare module "@tanstack/react-table" {
    interface FilterFns {
        psdString: FilterFn<unknown>;
        psdNumber: FilterFn<unknown>;
    }
}

/**
 * Extend TanStack Table's ColumnMeta with grid-specific properties
 */
export interface PsdColumnMeta {
    /** Column alignment: left, center, right */
    align?: "left" | "center" | "right";
    /** Whether column is numeric (affects formatting and alignment) */
    numeric?: boolean;
    /** Fixed column width in pixels */
    width?: number;
    /** Minimum column width in pixels */
    minWidth?: number;
    /** Maximum column width in pixels */
    maxWidth?: number;
    /** Whether column should be sortable */
    sortable?: boolean;
    /** Custom header tooltip */
    headerTooltip?: string;
    /** Cell value tone function (returns Tailwind color class) */
    valueTone?: (value: unknown) => string | undefined;
}

/**
 * Configuration for row coloring/styling
 */
export interface RowStyleConfig<TData> {
    /** Get row background color class */
    getRowClassName?: (row: Row<TData>) => string;
    /** Get row style object */
    getRowStyle?: (row: Row<TData>) => React.CSSProperties;
    /** Check if row should flash (for data updates) */
    shouldFlash?: (row: Row<TData>, prevData: TData | undefined) => boolean;
}

/**
 * Stable row ID generator function
 */
export type RowIdFn<TData> = (row: TData, index: number) => string;

/**
 * Grid virtualization configuration
 */
export interface VirtualConfig {
    /** Estimated row height in pixels */
    estimatedRowHeight: number;
    /** Overscan count (rows to render outside viewport) */
    overscan: number;
    /** Enable/disable virtualization */
    enabled: boolean;
}

/**
 * Keyboard navigation state
 */
export interface KeyboardNavState {
    /** Currently focused row index */
    focusedRowIndex: number | null;
    /** Currently focused column index */
    focusedColumnIndex: number | null;
    /** Whether grid has focus */
    hasFocus: boolean;
}

/**
 * Props for the main PsdDataGrid component
 */
export interface PsdDataGridProps<TData extends RowData> {
    /** Table data */
    data: TData[];
    /** Column definitions */
    columns: ColumnDef<TData, unknown>[];
    /** Stable row ID generator */
    getRowId: RowIdFn<TData>;
    /** Optional row styling configuration */
    rowStyle?: RowStyleConfig<TData>;
    /** Virtualization config */
    virtualConfig?: Partial<VirtualConfig>;
    /** Loading state */
    isLoading?: boolean;
    /** Error state */
    error?: Error | null;
    /** Empty state message */
    emptyMessage?: string;
    /** Grid height (CSS value) */
    height?: string | number;
    /** ARIA label for the grid */
    ariaLabel: string;
    /** Optional className */
    className?: string;
    /** Called when a row is clicked */
    onRowClick?: (row: Row<TData>) => void;
    /** Called when a row is double-clicked */
    onRowDoubleClick?: (row: Row<TData>) => void;
    /** Called when Enter is pressed on a focused row */
    onRowActivate?: (row: Row<TData>) => void;
    /** Called when row expansion changes */
    onExpandedChange?: (expandedRowIds: Set<string>) => void;
    /** Expanded row IDs (controlled) */
    expandedRowIds?: Set<string>;
    /** Render function for expanded row content */
    renderExpandedRow?: (row: Row<TData>) => React.ReactNode;
    /** Whether rows can be expanded */
    enableExpansion?: boolean;
    /** Controlled table instance (for advanced use cases) */
    table?: Table<TData>;
    /** Column pinning configuration */
    pinnedColumns?: {
        left?: string[];
        right?: string[];
    };
    /** Selected row IDs (controlled) */
    selectedRowIds?: Set<string>;
    /** Callback when selection changes */
    onSelectedRowIdsChange?: (ids: Set<string>) => void;
    /** Enable row selection */
    enableSelection?: boolean;
    /** Controlled column filters */
    columnFilters?: ColumnFiltersState;
    /** Column filter change handler */
    onColumnFiltersChange?: OnChangeFn<ColumnFiltersState>;
    /** Controlled sorting state */
    sorting?: SortingState;
    /** Sorting change handler */
    onSortingChange?: OnChangeFn<SortingState>;
    /** Indicates data is stable (no transient refetch empty states) */
    isDataStable?: boolean;
}

/**
 * Expand TanStack's Row type to add helper methods
 */
declare module "@tanstack/react-table" {
    interface ColumnMeta<TData extends RowData, TValue> extends PsdColumnMeta { }
}

export default {};
