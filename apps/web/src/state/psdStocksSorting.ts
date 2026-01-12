import { useSyncExternalStore } from "react";
import type { SortingState, Updater } from "@tanstack/react-table";

const STORAGE_KEY = "psd.stocks.sorting.v1";
const VALID_COLUMN_IDS = new Set([
  "symbol",
  "quantity",
  "markPrice",
  "dayPnlAmount",
  "dayPnlPercent",
  "totalPnlAmount",
  "totalPnlPercent",
  "exposure",
  "priceSource",
  "staleness",
]);

type InternalState = {
  sorting: SortingState;
};

const listeners = new Set<() => void>();

const isSortingState = (value: unknown): value is SortingState =>
  Array.isArray(value) &&
  value.every(
    (item) =>
      !!item &&
      typeof item === "object" &&
      typeof item.id === "string" &&
      typeof item.desc === "boolean",
  );

const sanitizeSorting = (sorting: SortingState): SortingState => {
  const seen = new Set<string>();
  const sanitized: SortingState = [];

  for (const sort of sorting) {
    if (!sort || typeof sort.id !== "string" || typeof sort.desc !== "boolean") {
      continue;
    }
    if (!VALID_COLUMN_IDS.has(sort.id)) {
      continue;
    }
    if (seen.has(sort.id)) {
      continue;
    }
    seen.add(sort.id);
    sanitized.push({ id: sort.id, desc: sort.desc });
  }

  return sanitized;
};

const loadInitialState = (): InternalState => {
  if (typeof window === "undefined") {
    return { sorting: [] };
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as { sorting?: SortingState };
      if (isSortingState(parsed?.sorting)) {
        return { sorting: sanitizeSorting(parsed.sorting) };
      }
    }
  } catch {
    // ignore storage/JSON errors
  }
  return { sorting: [] };
};

let state: InternalState = loadInitialState();

const notify = () => {
  for (const listener of listeners) {
    listener();
  }
};

const persist = (next: InternalState) => {
  if (typeof window === "undefined") return;
  try {
    if (next.sorting.length === 0) {
      window.localStorage.removeItem(STORAGE_KEY);
      return;
    }
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ sorting: next.sorting }),
    );
  } catch {
    // ignore storage errors in non-browser environments
  }
};

const setState = (partial: Partial<InternalState>) => {
  const next: InternalState = {
    ...state,
    ...partial,
  };
  if (next.sorting === state.sorting) {
    return;
  }
  state = next;
  persist(state);
  notify();
};

const setSorting = (sorting: Updater<SortingState>) => {
  const next = typeof sorting === "function" ? sorting(state.sorting) : sorting;
  setState({ sorting: sanitizeSorting(next) });
};

const getState = (): SortingState => state.sorting;

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};

export function usePsdStocksSorting(): SortingState {
  return useSyncExternalStore(subscribe, getState, getState);
}

export function setPsdStocksSorting(sorting: Updater<SortingState>): void {
  setSorting(sorting);
}
