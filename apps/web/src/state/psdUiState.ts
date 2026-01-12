import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

/**
 * PSD UI State Store
 *
 * Manages UI state that should persist across browser reloads:
 * - Expanded combos in the combos section
 * - Grid selection state
 * - Scroll positions (via sessionStorage)
 */

export interface PsdUiState {
  /** Set of expanded combo IDs */
  expandedCombos: Set<string>;
  /** Set of selected stock symbols in the grid */
  stocksGridSelection: Set<string>;
}

export interface PsdUiStateActions {
  toggleCombo: (comboId: string) => void;
  setExpandedCombos: (ids: Set<string>) => void;
  setStocksGridSelection: (ids: Set<string>) => void;
  clearStocksGridSelection: () => void;
}

export type PsdUiStateStore = PsdUiState & PsdUiStateActions;

const STORAGE_KEY = "psd-ui-state-v1";

/**
 * Custom storage that handles Set serialization.
 * Sets are converted to arrays for JSON storage.
 */
const setStorage = createJSONStorage<PsdUiState>(() => localStorage, {
  reviver: (key, value) => {
    // Convert arrays back to Sets on read
    if (key === 'expandedCombos' || key === 'stocksGridSelection') {
      return new Set(Array.isArray(value) ? value : []);
    }
    return value;
  },
  replacer: (key, value) => {
    // Convert Sets to arrays for JSON serialization on write
    if (value instanceof Set) {
      return Array.from(value);
    }
    return value;
  },
});

export const usePsdUiState = create<PsdUiStateStore>()(
  persist(
    (set) => ({
      // Defaults
      expandedCombos: new Set<string>(),
      stocksGridSelection: new Set<string>(),

      toggleCombo: (comboId) => {
        set((state) => {
          const newExpanded = new Set(state.expandedCombos);
          if (newExpanded.has(comboId)) {
            newExpanded.delete(comboId);
          } else {
            newExpanded.add(comboId);
          }
          return { expandedCombos: newExpanded };
        });
      },

      setExpandedCombos: (ids) => {
        set({ expandedCombos: new Set(ids) });
      },

      setStocksGridSelection: (ids) => {
        set({ stocksGridSelection: new Set(ids) });
      },

      clearStocksGridSelection: () => {
        set({ stocksGridSelection: new Set() });
      },
    }),
    {
      name: STORAGE_KEY,
      storage: setStorage,
    },
  ),
);
