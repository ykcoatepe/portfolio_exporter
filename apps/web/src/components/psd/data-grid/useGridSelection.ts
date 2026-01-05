/**
 * Grid Selection Hook
 *
 * Manages row selection state for PsdDataGrid.
 * Features:
 * - RowId-based selection (never indices)
 * - Click semantics: plain, Ctrl, Shift, Ctrl+Shift
 * - Keyboard: Shift+Arrow extends selection, Space toggles
 * - Persistence across virtualization and refetch
 */

import { useCallback, useMemo, useState } from "react";

export interface SelectionState {
    /** Currently selected row IDs */
    selectedIds: Set<string>;
    /** Anchor row for shift-range selection */
    anchorId: string | null;
}

export interface UseGridSelectionOptions {
    /** Controlled selection (external state) */
    selectedRowIds?: Set<string>;
    /** Callback when selection changes */
    onSelectedRowIdsChange?: (ids: Set<string>) => void;
    /** Ordered list of row IDs (for range selection) */
    orderedRowIds: string[];
}

export interface UseGridSelectionResult {
    /** Current selected row IDs */
    selectedIds: Set<string>;
    /** Current anchor row ID (for shift-range selection) */
    anchorId: string | null;
    /** Check if a row is selected */
    isSelected: (rowId: string) => boolean;
    /** Handle row click with modifier keys */
    handleRowClick: (rowId: string, event: React.MouseEvent) => void;
    /** Handle keyboard selection (Shift+Arrow, Space) */
    handleKeyboardSelect: (rowId: string, event: React.KeyboardEvent) => void;
    /** Select a single row (plain click) */
    selectSingle: (rowId: string) => void;
    /** Toggle row selection (Ctrl+click) */
    toggleSelection: (rowId: string) => void;
    /** Select range from anchor to target (Shift+click) */
    selectRange: (targetId: string, additive?: boolean) => void;
    /** Clear all selection */
    clearSelection: () => void;
    /** Prune selection to only existing rowIds (after refetch) */
    pruneSelection: (existingIds: Set<string>) => void;
    /** Prune anchor to a visible row (or null) */
    pruneAnchor: (existingIds: Set<string>, fallbackId: string | null) => void;
}

/**
 * Compute range of indices between two rowIds in ordered list
 */
function getRange(orderedIds: string[], fromId: string, toId: string): string[] {
    const fromIndex = orderedIds.indexOf(fromId);
    const toIndex = orderedIds.indexOf(toId);

    if (fromIndex === -1 || toIndex === -1) {
        // One of the IDs not found, return just the target
        return toIndex !== -1 ? [orderedIds[toIndex]] : [];
    }

    const start = Math.min(fromIndex, toIndex);
    const end = Math.max(fromIndex, toIndex);
    return orderedIds.slice(start, end + 1);
}

export function useGridSelection({
    selectedRowIds: controlledSelectedIds,
    onSelectedRowIdsChange,
    orderedRowIds,
}: UseGridSelectionOptions): UseGridSelectionResult {
    // Internal state for uncontrolled mode
    const [internalState, setInternalState] = useState<SelectionState>({
        selectedIds: new Set(),
        anchorId: null,
    });

    // Use controlled or internal state
    const isControlled = controlledSelectedIds !== undefined;
    const selectedIds = isControlled ? controlledSelectedIds : internalState.selectedIds;
    const anchorId = internalState.anchorId;

    // Update selection (handles both controlled and uncontrolled)
    const updateSelection = useCallback(
        (nextIds: Set<string>, nextAnchorId?: string | null) => {
            if (isControlled) {
                onSelectedRowIdsChange?.(nextIds);
                if (nextAnchorId !== undefined) {
                    setInternalState((prev) => ({
                        ...prev,
                        anchorId: nextAnchorId,
                    }));
                }
            } else {
                setInternalState((prev) => ({
                    selectedIds: nextIds,
                    anchorId: nextAnchorId ?? prev.anchorId,
                }));
            }
        },
        [isControlled, onSelectedRowIdsChange]
    );

    const isSelected = useCallback(
        (rowId: string) => selectedIds.has(rowId),
        [selectedIds]
    );

    const selectSingle = useCallback(
        (rowId: string) => {
            const next = new Set([rowId]);
            updateSelection(next, rowId);
        },
        [updateSelection]
    );

    const toggleSelection = useCallback(
        (rowId: string) => {
            const next = new Set(selectedIds);
            if (next.has(rowId)) {
                next.delete(rowId);
            } else {
                next.add(rowId);
            }
            updateSelection(next, rowId);
        },
        [selectedIds, updateSelection]
    );

    const selectRange = useCallback(
        (targetId: string, additive = false) => {
            // Use anchor if set, otherwise just select single
            const anchor = anchorId && orderedRowIds.includes(anchorId) ? anchorId : targetId;
            const rangeIds = getRange(orderedRowIds, anchor, targetId);

            const next = additive ? new Set(selectedIds) : new Set<string>();
            for (const id of rangeIds) {
                next.add(id);
            }
            // Don't update anchor on range select (keep original anchor)
            updateSelection(next);
        },
        [anchorId, orderedRowIds, selectedIds, updateSelection]
    );

    const clearSelection = useCallback(() => {
        updateSelection(new Set(), null);
    }, [updateSelection]);

    const pruneSelection = useCallback(
        (existingIds: Set<string>) => {
            const next = new Set<string>();
            for (const id of selectedIds) {
                if (existingIds.has(id)) {
                    next.add(id);
                }
            }
            if (next.size !== selectedIds.size) {
                updateSelection(next);
            }
        },
        [selectedIds, updateSelection]
    );

    const pruneAnchor = useCallback(
        (existingIds: Set<string>, fallbackId: string | null) => {
            if (!anchorId) return;
            if (existingIds.has(anchorId)) return;
            setInternalState((prev) => ({
                ...prev,
                anchorId: fallbackId,
            }));
        },
        [anchorId]
    );

    const handleRowClick = useCallback(
        (rowId: string, event: React.MouseEvent) => {
            // Ignore non-left clicks
            if (event.button !== 0) return;

            const toggle = event.metaKey || event.ctrlKey;
            const shift = event.shiftKey;

            if (toggle && shift) {
                // Ctrl+Shift: add range to existing selection
                selectRange(rowId, true);
            } else if (shift) {
                // Shift: select range (replace selection)
                selectRange(rowId, false);
            } else if (toggle) {
                // Ctrl: toggle single row
                toggleSelection(rowId);
            } else {
                // Plain click: select single
                selectSingle(rowId);
            }
        },
        [selectRange, selectSingle, toggleSelection]
    );

    const handleKeyboardSelect = useCallback(
        (rowId: string, event: React.KeyboardEvent) => {
            if (event.key === " " || event.key === "Space") {
                // Space: toggle selection of active row
                event.preventDefault();
                toggleSelection(rowId);
            } else if (event.shiftKey && (event.key === "ArrowUp" || event.key === "ArrowDown")) {
                // Shift+Arrow: extend selection to new active row
                selectRange(rowId, false);
            }
        },
        [selectRange, toggleSelection]
    );

    return useMemo(
        () => ({
            selectedIds,
            anchorId,
            isSelected,
            handleRowClick,
            handleKeyboardSelect,
            selectSingle,
            toggleSelection,
            selectRange,
            clearSelection,
            pruneSelection,
            pruneAnchor,
        }),
        [
            selectedIds,
            anchorId,
            isSelected,
            handleRowClick,
            handleKeyboardSelect,
            selectSingle,
            toggleSelection,
            selectRange,
            clearSelection,
            pruneSelection,
            pruneAnchor,
        ]
    );
}
