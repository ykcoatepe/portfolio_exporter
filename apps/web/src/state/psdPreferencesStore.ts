import { create } from "zustand";
import { persist } from "zustand/middleware";

/**
 * PSD Preferences Store
 *
 * Manages user accessibility and display preferences.
 * Persists to localStorage and syncs with CSS data-attributes on :root.
 */

export interface PsdPreferences {
    /** Disable motion/animations */
    reducedMotion: boolean;
    /** Disable glass/blur effects */
    reducedTranslucency: boolean;
    /** Sidebar collapsed state */
    sidebarCollapsed: boolean;
}

export interface PsdPreferencesActions {
    setReducedMotion: (value: boolean) => void;
    setReducedTranslucency: (value: boolean) => void;
    setSidebarCollapsed: (value: boolean) => void;
    toggleSidebar: () => void;
}

export type PsdPreferencesStore = PsdPreferences & PsdPreferencesActions;

const STORAGE_KEY = "psd-preferences";

/**
 * Syncs preferences to document root data-attributes.
 * This enables CSS-only reactivity to preference changes.
 */
function syncToDocument(state: PsdPreferences): void {
    if (typeof document === "undefined") return;

    const root = document.documentElement;
    root.dataset.reducedMotion = String(state.reducedMotion);
    root.dataset.reducedTranslucency = String(state.reducedTranslucency);
}

export const usePsdPreferences = create<PsdPreferencesStore>()(
    persist(
        (set, get) => ({
            // Defaults
            reducedMotion: false,
            reducedTranslucency: false,
            sidebarCollapsed: false,

            setReducedMotion: (value) => {
                set({ reducedMotion: value });
                syncToDocument(get());
            },

            setReducedTranslucency: (value) => {
                set({ reducedTranslucency: value });
                syncToDocument(get());
            },

            setSidebarCollapsed: (value) => {
                set({ sidebarCollapsed: value });
            },

            toggleSidebar: () => {
                set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed }));
            },
        }),
        {
            name: STORAGE_KEY,
            // On hydration, sync to document
            onRehydrateStorage: () => (state) => {
                if (state) {
                    syncToDocument(state);
                }
            },
        },
    ),
);

/**
 * Initialize preferences from system settings.
 * Call this once on app mount (e.g., in main.tsx).
 */
export function initPreferencesFromSystem(): void {
    if (typeof window === "undefined") return;

    const store = usePsdPreferences.getState();

    // Check if user has already set preferences (don't override)
    const persisted = localStorage.getItem(STORAGE_KEY);
    if (persisted) {
        // Already has preferences, just sync to document
        syncToDocument(store);
        return;
    }

    // Initialize from system preferences
    const prefersReducedMotion = window.matchMedia(
        "(prefers-reduced-motion: reduce)",
    ).matches;

    if (prefersReducedMotion) {
        store.setReducedMotion(true);
    }

    syncToDocument(store);
}
