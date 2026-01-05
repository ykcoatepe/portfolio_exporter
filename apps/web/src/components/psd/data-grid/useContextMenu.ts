/**
 * Context Menu Hook
 *
 * Manages context menu state for grid row actions.
 * Features:
 * - Portal rendering (outside grid overflow)
 * - Viewport clamping
 * - Close on Escape, scroll (capture), outside click
 */

import { useCallback, useEffect, useState } from "react";

export interface ContextMenuPosition {
    x: number;
    y: number;
}

export interface ContextMenuState {
    isOpen: boolean;
    targetRowIds: string[];
    position: ContextMenuPosition;
}

export interface UseContextMenuResult {
    state: ContextMenuState;
    open: (targetRowIds: string[], position: ContextMenuPosition) => void;
    close: () => void;
}

const INITIAL_STATE: ContextMenuState = {
    isOpen: false,
    targetRowIds: [],
    position: { x: 0, y: 0 },
};

export function useContextMenu(): UseContextMenuResult {
    const [state, setState] = useState<ContextMenuState>(INITIAL_STATE);

    const open = useCallback((targetRowIds: string[], position: ContextMenuPosition) => {
        setState({
            isOpen: true,
            targetRowIds,
            position,
        });
    }, []);

    const close = useCallback(() => {
        setState(INITIAL_STATE);
    }, []);

    // Close on Escape
    useEffect(() => {
        if (!state.isOpen) return;

        const handleKeyDown = (e: KeyboardEvent) => {
            if (e.key === "Escape") {
                close();
            }
        };

        document.addEventListener("keydown", handleKeyDown);
        return () => document.removeEventListener("keydown", handleKeyDown);
    }, [state.isOpen, close]);

    // Close on any scroll (capture phase to catch virtualizer scrolls)
    useEffect(() => {
        if (!state.isOpen) return;

        const handleScroll = () => {
            close();
        };

        document.addEventListener("scroll", handleScroll, true);
        return () => document.removeEventListener("scroll", handleScroll, true);
    }, [state.isOpen, close]);

    // Close on outside click
    useEffect(() => {
        if (!state.isOpen) return;

        const handleClick = (e: MouseEvent) => {
            const target = e.target as HTMLElement;
            if (!target.closest('[data-testid="grid-context-menu"]')) {
                close();
            }
        };

        // Use timeout to avoid closing immediately on the right-click that opened it
        const timeoutId = setTimeout(() => {
            document.addEventListener("click", handleClick);
        }, 0);

        return () => {
            clearTimeout(timeoutId);
            document.removeEventListener("click", handleClick);
        };
    }, [state.isOpen, close]);

    // Close on resize
    useEffect(() => {
        if (!state.isOpen) return;

        const handleResize = () => {
            close();
        };

        window.addEventListener("resize", handleResize);
        return () => window.removeEventListener("resize", handleResize);
    }, [state.isOpen, close]);

    return { state, open, close };
}
