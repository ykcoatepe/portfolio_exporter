/**
 * PSD Data Grid Keyboard Navigation
 *
 * Provides arrow key navigation, Enter to activate, and Escape to blur.
 */

import type { KeyboardEvent as ReactKeyboardEvent } from "react";
import type { Row, Table } from "@tanstack/react-table";

export interface KeyboardNavConfig<TData> {
    /** Currently focused row index */
    focusedIndex: number | null;
    /** Set focused row index */
    setFocusedIndex: (index: number | null) => void;
    /** Total row count */
    rowCount: number;
    /** Row ref map for focusing DOM elements */
    rowRefs: Map<number, HTMLElement>;
    /** Callback when Enter is pressed on a row */
    onActivate?: (row: Row<TData>) => void;
    /** Callback when row expansion is toggled */
    onToggleExpand?: (rowId: string) => void;
    /** Table instance for row access */
    table: Table<TData>;
    /** Whether expansion is enabled */
    enableExpansion?: boolean;
}

/**
 * Handle keyboard navigation for the grid
 */
export function handleGridKeyDown<TData>(
    event: ReactKeyboardEvent<HTMLElement>,
    config: KeyboardNavConfig<TData>,
): void {
    const {
        focusedIndex,
        setFocusedIndex,
        rowCount,
        rowRefs,
        onActivate,
        onToggleExpand,
        table,
        enableExpansion,
    } = config;

    if (rowCount === 0) return;

    const currentIndex = focusedIndex ?? -1;
    let nextIndex: number | null = null;
    let handled = false;

    switch (event.key) {
        case "ArrowDown":
            nextIndex = Math.min(currentIndex + 1, rowCount - 1);
            handled = true;
            break;

        case "ArrowUp":
            nextIndex = Math.max(currentIndex - 1, 0);
            handled = true;
            break;

        case "Home":
            nextIndex = 0;
            handled = true;
            break;

        case "End":
            nextIndex = rowCount - 1;
            handled = true;
            break;

        case "PageDown":
            // Move 10 rows at a time
            nextIndex = Math.min(currentIndex + 10, rowCount - 1);
            handled = true;
            break;

        case "PageUp":
            // Move 10 rows at a time
            nextIndex = Math.max(currentIndex - 10, 0);
            handled = true;
            break;

        case "Enter":
        case " ":
            if (currentIndex >= 0) {
                const rows = table.getRowModel().rows;
                const row = rows[currentIndex];
                if (row) {
                    // If expansion is enabled and it's Space or Enter, toggle expand
                    if (enableExpansion && onToggleExpand && event.key === " ") {
                        event.preventDefault();
                        onToggleExpand(row.id);
                        handled = true;
                    } else if (onActivate && event.key === "Enter") {
                        event.preventDefault();
                        onActivate(row);
                        handled = true;
                    }
                }
            }
            break;

        case "Escape":
            setFocusedIndex(null);
            // Blur the grid
            (event.target as HTMLElement).blur?.();
            handled = true;
            break;

        default:
            break;
    }

    if (nextIndex !== null && nextIndex !== currentIndex) {
        event.preventDefault();
        setFocusedIndex(nextIndex);

        // Focus the row element
        const rowEl = rowRefs.get(nextIndex);
        if (rowEl) {
            rowEl.focus({ preventScroll: true });
            // Scroll into view if needed
            rowEl.scrollIntoView({ block: "nearest", behavior: "auto" });
        }
    }

    if (handled) {
        event.stopPropagation();
    }
}

/**
 * Handle row-level keyboard events
 */
export function handleRowKeyDown<TData>(
    event: ReactKeyboardEvent<HTMLTableRowElement>,
    options: {
        row: Row<TData>;
        rowIndex: number;
        totalRows: number;
        focusRowByIndex: (index: number) => void;
        onActivate?: (row: Row<TData>) => void;
        onToggleExpand?: (rowId: string) => void;
        enableExpansion?: boolean;
    },
): void {
    const {
        row,
        rowIndex,
        totalRows,
        focusRowByIndex,
        onActivate,
        onToggleExpand,
        enableExpansion,
    } = options;

    let nextIndex: number | null = null;
    let handled = false;

    switch (event.key) {
        case "ArrowDown":
            nextIndex = Math.min(rowIndex + 1, totalRows - 1);
            handled = true;
            break;

        case "ArrowUp":
            nextIndex = Math.max(rowIndex - 1, 0);
            handled = true;
            break;

        case "Home":
            nextIndex = 0;
            handled = true;
            break;

        case "End":
            nextIndex = totalRows - 1;
            handled = true;
            break;

        case "Enter":
            if (onActivate) {
                event.preventDefault();
                onActivate(row);
                handled = true;
            }
            break;

        case " ":
            if (enableExpansion && onToggleExpand) {
                event.preventDefault();
                onToggleExpand(row.id);
                handled = true;
            }
            break;

        case "ArrowRight":
            // Expand row if collapsed
            if (enableExpansion && onToggleExpand && !row.getIsExpanded()) {
                event.preventDefault();
                onToggleExpand(row.id);
                handled = true;
            }
            break;

        case "ArrowLeft":
            // Collapse row if expanded
            if (enableExpansion && onToggleExpand && row.getIsExpanded()) {
                event.preventDefault();
                onToggleExpand(row.id);
                handled = true;
            }
            break;

        default:
            break;
    }

    if (nextIndex !== null && nextIndex !== rowIndex) {
        event.preventDefault();
        focusRowByIndex(nextIndex);
        handled = true;
    }

    if (handled) {
        event.stopPropagation();
    }
}

export default {
    handleGridKeyDown,
    handleRowKeyDown,
};
