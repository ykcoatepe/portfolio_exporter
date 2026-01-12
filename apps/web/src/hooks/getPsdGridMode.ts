/**
 * PSD Grid Mode
 *
 * Tri-state configuration for grid rendering:
 * - "old": Legacy table components
 * - "new": PsdDataGrid with virtualization
 * - "parity": Side-by-side comparison (DEV only)
 *
 * Priority: query param → localStorage → env default
 */

export type PsdGridMode = "old" | "new" | "parity";

const STORAGE_KEY = "psd.grid.mode";
const VALID_MODES: PsdGridMode[] = ["old", "new", "parity"];

function isValidMode(value: string | null): value is PsdGridMode {
    return value !== null && VALID_MODES.includes(value as PsdGridMode);
}

/**
 * Get the current grid mode.
 *
 * Not a React hook (no state/effects), so can be called anywhere.
 * Named without "use" prefix to avoid eslint-plugin-react-hooks confusion.
 */
export function getPsdGridMode(): PsdGridMode {
    // SSR / test guard
    if (typeof window === "undefined") {
        return "new";
    }

    try {
        // 1. Query param: ?grid=new|old|parity
        const params = new URLSearchParams(window.location.search);
        const qp = params.get("grid");
        if (isValidMode(qp)) {
            // Parity is DEV-only
            if (qp === "parity" && !import.meta.env.DEV) {
                return "new";
            }
            return qp;
        }

        // 2. localStorage: psd.grid.mode
        const stored = localStorage.getItem(STORAGE_KEY);
        if (isValidMode(stored)) {
            if (stored === "parity" && !import.meta.env.DEV) {
                return "new";
            }
            return stored;
        }
    } catch {
        // localStorage access can throw in some contexts
    }

    // 3. Env default
    const envMode = import.meta.env.VITE_PSD_GRID_MODE;
    if (isValidMode(envMode)) {
        return envMode;
    }

    return "new";
}

/**
 * Set the grid mode in localStorage.
 * Useful for dev tools / settings panel.
 */
export function setPsdGridMode(mode: PsdGridMode): void {
    if (typeof window === "undefined") return;
    try {
        localStorage.setItem(STORAGE_KEY, mode);
    } catch {
        // ignore
    }
}

/**
 * Clear the grid mode from localStorage (revert to env default).
 */
export function clearPsdGridMode(): void {
    if (typeof window === "undefined") return;
    try {
        localStorage.removeItem(STORAGE_KEY);
    } catch {
        // ignore
    }
}
