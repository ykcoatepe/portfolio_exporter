/**
 * Grid Context Menu
 *
 * Portal-rendered context menu for grid row actions.
 * Features:
 * - Renders in document.body (avoids grid overflow clipping)
 * - Viewport clamping (adjusts position near edges)
 * - Selection-aware action targeting
 */

import { useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import type { ContextMenuPosition } from "./useContextMenu";

export interface GridContextMenuProps {
    isOpen: boolean;
    position: ContextMenuPosition;
    targetRowIds: string[];
    /** Map rowId → symbol for Copy action */
    rowSymbolMap: Map<string, string>;
    onClose: () => void;
    onCopySymbols?: (symbols: string[]) => void;
    onViewDetails?: (rowId: string) => void;
}

interface MenuPosition {
    x: number;
    y: number;
}

const MENU_WIDTH = 180;
const MENU_HEIGHT_ESTIMATE = 100;
const EDGE_PADDING = 8;

/**
 * Clamp menu position to stay within viewport
 */
function clampPosition(
    position: ContextMenuPosition,
    menuRect: DOMRect | null
): MenuPosition {
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;

    const menuWidth = menuRect?.width ?? MENU_WIDTH;
    const menuHeight = menuRect?.height ?? MENU_HEIGHT_ESTIMATE;

    let x = position.x;
    let y = position.y;

    // Clamp right edge
    if (x + menuWidth > viewportWidth - EDGE_PADDING) {
        x = viewportWidth - menuWidth - EDGE_PADDING;
    }

    // Clamp bottom edge
    if (y + menuHeight > viewportHeight - EDGE_PADDING) {
        y = viewportHeight - menuHeight - EDGE_PADDING;
    }

    // Clamp left/top edges
    x = Math.max(EDGE_PADDING, x);
    y = Math.max(EDGE_PADDING, y);

    return { x, y };
}

export function GridContextMenu({
    isOpen,
    position,
    targetRowIds,
    rowSymbolMap,
    onClose,
    onCopySymbols,
    onViewDetails,
}: GridContextMenuProps): JSX.Element | null {
    const menuRef = useRef<HTMLDivElement>(null);
    const [clampedPos, setClampedPos] = useState<MenuPosition>(position);

    // Clamp position after render to get actual menu size
    useLayoutEffect(() => {
        if (!isOpen) return;

        const menuRect = menuRef.current?.getBoundingClientRect() ?? null;
        const newPos = clampPosition(position, menuRect);
        setClampedPos(newPos);
    }, [isOpen, position]);

    if (!isOpen) return null;

    const isSingleTarget = targetRowIds.length === 1;

    const handleCopySymbols = () => {
        const symbols = targetRowIds
            .map((id) => rowSymbolMap.get(id))
            .filter((s): s is string => !!s);
        onCopySymbols?.(symbols);
        onClose();
    };

    const handleViewDetails = () => {
        if (isSingleTarget) {
            onViewDetails?.(targetRowIds[0]);
        }
        onClose();
    };

    const menuContent = (
        <div
            ref={menuRef}
            data-testid="grid-context-menu"
            className="fixed z-50 min-w-[180px] rounded-lg border border-slate-700 bg-slate-900 py-1 shadow-xl"
            style={{
                left: clampedPos.x,
                top: clampedPos.y,
            }}
            role="menu"
            aria-label="Row actions"
        >
            <button
                type="button"
                data-testid="ctx-copy-symbol"
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-slate-200 hover:bg-slate-800"
                onClick={handleCopySymbols}
                role="menuitem"
            >
                <span className="text-slate-400">📋</span>
                Copy Symbol{targetRowIds.length > 1 ? "s" : ""}
                {targetRowIds.length > 1 && (
                    <span className="ml-auto text-xs text-slate-500">
                        ({targetRowIds.length})
                    </span>
                )}
            </button>

            <button
                type="button"
                data-testid="ctx-view-details"
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-slate-200 hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-50"
                onClick={handleViewDetails}
                disabled={!isSingleTarget}
                role="menuitem"
            >
                <span className="text-slate-400">🔍</span>
                View Details
                {!isSingleTarget && (
                    <span className="ml-auto text-xs text-slate-500">
                        (single only)
                    </span>
                )}
            </button>

            <div className="mx-2 my-1 border-t border-slate-700" />

            <div className="px-3 py-1 text-xs text-slate-500">
                {targetRowIds.length === 1
                    ? rowSymbolMap.get(targetRowIds[0]) ?? "1 row"
                    : `${targetRowIds.length} rows selected`}
            </div>
        </div>
    );

    return createPortal(menuContent, document.body);
}
