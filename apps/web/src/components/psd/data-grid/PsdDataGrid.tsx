/**
 * PSD Data Grid
 *
 * Virtualized data grid using TanStack Table + TanStack Virtual.
 * Provides:
 * - Virtual scrolling for large datasets
 * - Keyboard navigation (arrows, Enter, Escape)
 * - Row expansion support
 * - Terminal-first design system styling
 * - Cell flash animation for data updates
 */

import type { ReactNode, KeyboardEvent as ReactKeyboardEvent } from "react";
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { RowData, Row, ExpandedState } from "@tanstack/react-table";
import {
    useReactTable,
    getCoreRowModel,
    getFilteredRowModel,
    getExpandedRowModel,
    getSortedRowModel,
    flexRender,
} from "@tanstack/react-table";
import { useVirtualizer } from "@tanstack/react-virtual";
import clsx from "clsx";

import type { PsdDataGridProps, VirtualConfig, RowIdFn } from "./types";
import { mergeVirtualConfig, shouldVirtualize } from "./virtualConfig";
import { handleRowKeyDown } from "./keyboard";
import { useGridSelection } from "./useGridSelection";
import { useContextMenu } from "./useContextMenu";
import { GridContextMenu } from "./GridContextMenu";
import { psdFilterFns } from "./filters";

/**
 * Default row ID generator using index
 */
function defaultGetRowId<TData>(row: TData, index: number): string {
    // Try to use common ID fields
    const r = row as Record<string, unknown>;
    if (typeof r.id === "string") return r.id;
    if (typeof r.symbol === "string") return r.symbol;
    return String(index);
}

/**
 * Grid loading skeleton
 */
function GridSkeleton({ columns }: { columns: number }): JSX.Element {
    const rows = Array.from({ length: 8 }, (_, i) => i);
    return (
        <div className="animate-pulse">
            {rows.map((i) => (
                <div
                    key={i}
                    className="flex h-11 items-center border-b border-slate-800/60"
                >
                    {Array.from({ length: columns }, (_, j) => (
                        <div
                            key={j}
                            className="flex-1 px-3"
                            style={{ flex: j === 0 ? 2 : 1 }}
                        >
                            <div className="h-4 rounded bg-slate-800" />
                        </div>
                    ))}
                </div>
            ))}
        </div>
    );
}

/**
 * Empty state component
 */
function EmptyState({ message }: { message: string }): JSX.Element {
    return (
        <div className="flex h-48 items-center justify-center text-slate-500">
            {message}
        </div>
    );
}

/**
 * Error state component
 */
function ErrorState({ error }: { error: Error }): JSX.Element {
    return (
        <div className="flex h-48 flex-col items-center justify-center gap-2 text-rose-400">
            <span className="text-sm font-medium">Failed to load data</span>
            <span className="text-xs text-slate-500">{error.message}</span>
        </div>
    );
}

/**
 * Main PSD Data Grid component
 */
export function PsdDataGrid<TData extends RowData>({
    data,
    columns,
    getRowId = defaultGetRowId as RowIdFn<TData>,
    rowStyle,
    virtualConfig: partialVirtualConfig,
    isLoading = false,
    error = null,
    emptyMessage = "No data available",
    height = "400px",
    ariaLabel,
    className,
    onRowClick,
    onRowDoubleClick,
    onRowActivate,
    onExpandedChange,
    expandedRowIds,
    renderExpandedRow,
    enableExpansion = false,
    pinnedColumns,
    selectedRowIds,
    onSelectedRowIdsChange,
    enableSelection = false,
    columnFilters = [],
    onColumnFiltersChange,
    isDataStable = true,
}: PsdDataGridProps<TData>): JSX.Element {
    // Refs
    const containerRef = useRef<HTMLDivElement>(null);
    const rowRefs = useRef<Map<number, HTMLTableRowElement>>(new Map());

    // Keyboard nav state
    const [focusedRowIndex, setFocusedRowIndex] = useState<number | null>(null);
    const focusedRowIdRef = useRef<string | null>(null);

    // Expansion state (controlled or uncontrolled)
    const [internalExpanded, setInternalExpanded] = useState<ExpandedState>({});
    const expanded = useMemo(() => {
        if (expandedRowIds) {
            return Object.fromEntries(Array.from(expandedRowIds).map((id) => [id, true]));
        }
        return internalExpanded;
    }, [expandedRowIds, internalExpanded]);

    const handleExpandedChange = useCallback(
        (updater: ExpandedState | ((old: ExpandedState) => ExpandedState)) => {
            const newExpanded = typeof updater === "function" ? updater(expanded) : updater;
            if (onExpandedChange) {
                const ids = new Set(
                    Object.entries(newExpanded)
                        .filter(([, v]) => v)
                        .map(([k]) => k),
                );
                onExpandedChange(ids);
            } else {
                setInternalExpanded(newExpanded);
            }
        },
        [expanded, onExpandedChange],
    );

    // Virtualization config
    const virtualConfig = useMemo(
        () => mergeVirtualConfig(partialVirtualConfig),
        [partialVirtualConfig],
    );

    // TanStack Table instance
    const table = useReactTable({
        data,
        columns,
        getRowId: (row, index) => getRowId(row, index),
        filterFns: psdFilterFns,
        getCoreRowModel: getCoreRowModel(),
        getFilteredRowModel: getFilteredRowModel(),
        getSortedRowModel: getSortedRowModel(),
        getExpandedRowModel: enableExpansion ? getExpandedRowModel() : undefined,
        state: {
            expanded: enableExpansion ? expanded : undefined,
            columnFilters,
        },
        onExpandedChange: enableExpansion ? handleExpandedChange : undefined,
        onColumnFiltersChange,
    });

    const { rows } = table.getRowModel();
    const headerGroups = table.getHeaderGroups();
    const useVirtual = shouldVirtualize(rows.length, virtualConfig);

    // Ordered row IDs for range selection
    const orderedRowIds = useMemo(() => rows.map((r) => r.id), [rows]);
    const visibleRowIds = useMemo(() => new Set(rows.map((r) => r.id)), [rows]);
    const filtersKey = useMemo(() => {
        if (!columnFilters || columnFilters.length === 0) {
            return "";
        }
        const normalized = columnFilters
            .map((filter) => ({ id: filter.id, value: filter.value }))
            .sort((a, b) => a.id.localeCompare(b.id));
        return JSON.stringify(normalized);
    }, [columnFilters]);
    const prevFiltersKeyRef = useRef(filtersKey);

    // Selection hook
    const selection = useGridSelection({
        selectedRowIds,
        onSelectedRowIdsChange,
        orderedRowIds,
    });

    // Focus row by index
    const focusRowByIndex = useCallback(
        (index: number) => {
            setFocusedRowIndex(index);
            const row = rows[index];
            if (row) {
                focusedRowIdRef.current = row.id;
            }
            const rowEl = rowRefs.current.get(index);
            if (rowEl) {
                rowEl.focus({ preventScroll: true });
                rowEl.scrollIntoView({ block: "nearest", behavior: "auto" });
            }
        },
        [rows]
    );

    // Prune selection/focus when filters change (only when data is stable)
    useEffect(() => {
        const previousFiltersKey = prevFiltersKeyRef.current;
        const filtersChanged = previousFiltersKey !== filtersKey;
        if (filtersChanged) {
            prevFiltersKeyRef.current = filtersKey;
        }

        if (!filtersChanged && !isDataStable) {
            return;
        }

        if (enableSelection) {
            selection.pruneSelection(visibleRowIds);
            const nextActiveId = rows.length > 0 ? rows[0].id : null;
            selection.pruneAnchor(visibleRowIds, focusedRowIdRef.current ?? nextActiveId);
        }

        if (rows.length === 0) {
            if (focusedRowIndex !== null) {
                setFocusedRowIndex(null);
            }
            focusedRowIdRef.current = null;
            return;
        }

        const focusedId = focusedRowIdRef.current;
        if (!focusedId || !visibleRowIds.has(focusedId)) {
            focusRowByIndex(0);
            return;
        }

        const nextIndex = rows.findIndex((row) => row.id === focusedId);
        if (nextIndex !== -1 && nextIndex !== focusedRowIndex) {
            setFocusedRowIndex(nextIndex);
        }
    }, [
        enableSelection,
        isDataStable,
        selection,
        visibleRowIds,
        rows,
        focusedRowIndex,
        focusRowByIndex,
        filtersKey,
    ]);

    // Context menu hook
    const contextMenu = useContextMenu();

    // Row ID → symbol map for context menu actions
    const rowSymbolMap = useMemo(() => {
        const map = new Map<string, string>();
        for (const row of rows) {
            const data = row.original as Record<string, unknown>;
            const symbol = typeof data.symbol === "string" ? data.symbol : row.id;
            map.set(row.id, symbol);
        }
        return map;
    }, [rows]);

    // Virtualizer
    const virtualizer = useVirtualizer({
        count: rows.length,
        getScrollElement: () => containerRef.current,
        estimateSize: () => virtualConfig.estimatedRowHeight,
        overscan: virtualConfig.overscan,
        enabled: useVirtual,
    });

    const virtualRows = useVirtual ? virtualizer.getVirtualItems() : null;
    const totalSize = useVirtual ? virtualizer.getTotalSize() : 0;

    // Handle row toggle expand
    const handleToggleExpand = useCallback(
        (rowId: string) => {
            if (!enableExpansion) return;
            table.getRow(rowId)?.toggleExpanded();
        },
        [enableExpansion, table],
    );

    // Render a single row
    const renderRow = useCallback(
        (row: Row<TData>, virtualIndex: number, isVirtual: boolean) => {
            const rowIndex = isVirtual ? virtualIndex : row.index;
            const isFocused = focusedRowIndex === rowIndex;
            const isExpanded = enableExpansion && row.getIsExpanded();

            const rowClassName = rowStyle?.getRowClassName?.(row) ?? "";
            const rowStyleObj = rowStyle?.getRowStyle?.(row) ?? {};

            // Selection state
            const isSelected = enableSelection && selection.isSelected(row.id);

            return (
                <tr
                    key={row.id}
                    ref={(el) => {
                        if (el) rowRefs.current.set(rowIndex, el);
                    }}
                    tabIndex={isFocused ? 0 : -1}
                    role="row"
                    aria-rowindex={rowIndex + 2}
                    aria-selected={enableSelection ? isSelected : isFocused}
                    aria-expanded={enableExpansion ? isExpanded : undefined}
                    data-rowid={row.id}
                    className={clsx(
                        "border-b border-slate-800/60 psd-transition psd-grid-row",
                        "hover:bg-slate-800/40",
                        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-sky-500/60",
                        isFocused && "bg-slate-800/60",
                        isSelected && "psd-grid-row--selected",
                        rowClassName,
                    )}
                    style={rowStyleObj}
                    onClick={(e) => {
                        if (enableSelection) {
                            selection.handleRowClick(row.id, e);
                        }
                        focusRowByIndex(rowIndex);
                        onRowClick?.(row);
                    }}
                    onDoubleClick={() => onRowDoubleClick?.(row)}
                    onKeyDown={(e) => {
                        if (enableSelection) {
                            selection.handleKeyboardSelect(row.id, e);
                        }
                        handleRowKeyDown(e, {
                            row,
                            rowIndex,
                            totalRows: rows.length,
                            focusRowByIndex,
                            onActivate: onRowActivate,
                            onToggleExpand: handleToggleExpand,
                            enableExpansion,
                        });
                    }}
                    onContextMenu={(e) => {
                        e.preventDefault();
                        const { clientX, clientY } = e;
                        // Selection-aware targeting
                        const targetIds = enableSelection && selection.isSelected(row.id)
                            ? Array.from(selection.selectedIds)
                            : [row.id];
                        contextMenu.open(targetIds, { x: clientX, y: clientY });
                    }}
                >
                    {row.getVisibleCells().map((cell) => (
                        <td
                            key={cell.id}
                            className="text-sm psd-grid-cell"
                            data-rowid={row.id}
                            data-colid={cell.column.id}
                            style={{
                                width: cell.column.getSize(),
                            }}
                        >
                            {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </td>
                    ))}
                </tr>
            );
        },
        [
            focusedRowIndex,
            enableExpansion,
            enableSelection,
            selection,
            rowStyle,
            onRowClick,
            onRowDoubleClick,
            onRowActivate,
            focusRowByIndex,
            handleToggleExpand,
            rows.length,
        ],
    );

    // Render expanded row content
    const renderExpandedContent = useCallback(
        (row: Row<TData>) => {
            if (!enableExpansion || !row.getIsExpanded() || !renderExpandedRow) {
                return null;
            }
            return (
                <tr key={`${row.id}-expanded`} className="bg-slate-900/50">
                    <td colSpan={columns.length} className="p-0">
                        <div className="px-4 py-3">{renderExpandedRow(row)}</div>
                    </td>
                </tr>
            );
        },
        [enableExpansion, renderExpandedRow, columns.length],
    );

    // Handle loading/error/empty states
    if (isLoading) {
        return (
            <div
                className={clsx(
                    "overflow-hidden rounded-lg border border-slate-800/60 bg-slate-900",
                    className,
                )}
                style={{ height }}
                aria-label={ariaLabel}
                aria-busy="true"
            >
                <GridSkeleton columns={columns.length} />
            </div>
        );
    }

    if (error) {
        return (
            <div
                className={clsx(
                    "overflow-hidden rounded-lg border border-slate-800/60 bg-slate-900",
                    className,
                )}
                style={{ height }}
                aria-label={ariaLabel}
            >
                <ErrorState error={error} />
            </div>
        );
    }

    if (rows.length === 0) {
        return (
            <div
                className={clsx(
                    "overflow-hidden rounded-lg border border-slate-800/60 bg-slate-900",
                    className,
                )}
                style={{ height }}
                aria-label={ariaLabel}
            >
                <EmptyState message={emptyMessage} />
            </div>
        );
    }

    return (
        <>
            <div
                ref={containerRef}
                className={clsx(
                    "overflow-auto rounded-lg border border-slate-800/60 bg-slate-900 psd-data-surface",
                    className,
                )}
                style={{ height }}
                role="grid"
                aria-label={ariaLabel}
                aria-rowcount={rows.length + 1}
                aria-colcount={columns.length}
            >
                <table className="w-full border-collapse">
                    {/* Header */}
                    <thead className="sticky top-0 z-10 bg-slate-950/95 backdrop-blur-sm">
                        {headerGroups.map((headerGroup) => (
                            <tr key={headerGroup.id} role="row" aria-rowindex={1}>
                                {headerGroup.headers.map((header) => {
                                    const meta = header.column.columnDef.meta;
                                    return (
                                        <th
                                            key={header.id}
                                            className={clsx(
                                                "border-b border-slate-700 px-3 py-3 text-left text-xs font-medium uppercase tracking-wider text-slate-500",
                                                meta?.align === "right" && "text-right",
                                                meta?.align === "center" && "text-center",
                                                meta?.sortable && "cursor-pointer select-none hover:text-slate-300",
                                            )}
                                            style={{
                                                width: header.getSize(),
                                                minWidth: meta?.minWidth,
                                                maxWidth: meta?.maxWidth,
                                            }}
                                            title={meta?.headerTooltip}
                                            onClick={
                                                meta?.sortable
                                                    ? header.column.getToggleSortingHandler()
                                                    : undefined
                                            }
                                            role="columnheader"
                                            aria-sort={
                                                header.column.getIsSorted()
                                                    ? header.column.getIsSorted() === "asc"
                                                        ? "ascending"
                                                        : "descending"
                                                    : undefined
                                            }
                                        >
                                            {flexRender(
                                                header.column.columnDef.header,
                                                header.getContext(),
                                            )}
                                            {header.column.getIsSorted() && (
                                                <span className="ml-1">
                                                    {header.column.getIsSorted() === "asc" ? "↑" : "↓"}
                                                </span>
                                            )}
                                        </th>
                                    );
                                })}
                            </tr>
                        ))}
                    </thead>

                    {/* Body */}
                    <tbody>
                        {useVirtual && virtualRows ? (
                            <>
                                {/* Virtual spacer top */}
                                {virtualRows.length > 0 && virtualRows[0].start > 0 && (
                                    <tr>
                                        <td
                                            colSpan={columns.length}
                                            style={{ height: virtualRows[0].start }}
                                        />
                                    </tr>
                                )}

                                {/* Virtual rows */}
                                {virtualRows.map((virtualRow) => {
                                    const row = rows[virtualRow.index];
                                    return (
                                        <Fragment key={row.id}>
                                            {renderRow(row, virtualRow.index, true)}
                                            {renderExpandedContent(row)}
                                        </Fragment>
                                    );
                                })}

                                {/* Virtual spacer bottom */}
                                {virtualRows.length > 0 && (
                                    <tr>
                                        <td
                                            colSpan={columns.length}
                                            style={{
                                                height:
                                                    totalSize -
                                                    virtualRows[virtualRows.length - 1].end,
                                            }}
                                        />
                                    </tr>
                                )}
                            </>
                        ) : (
                            // Non-virtual rows
                            rows.map((row, index) => (
                                <Fragment key={row.id}>
                                    {renderRow(row, index, false)}
                                    {renderExpandedContent(row)}
                                </Fragment>
                            ))
                        )}
                    </tbody>
                </table>
            </div>

            {/* Context Menu */}
            <GridContextMenu
                isOpen={contextMenu.state.isOpen}
                position={contextMenu.state.position}
                targetRowIds={contextMenu.state.targetRowIds}
                rowSymbolMap={rowSymbolMap}
                onClose={contextMenu.close}
                onCopySymbols={(symbols) => {
                    // Copy newline-separated symbols to clipboard
                    const text = symbols.join("\n");
                    navigator.clipboard?.writeText(text);
                }}
            />
        </>
    );
}

export default PsdDataGrid;
