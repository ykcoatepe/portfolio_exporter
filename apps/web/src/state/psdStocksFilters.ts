import { useSyncExternalStore } from "react";
import type { ColumnFilter, ColumnFiltersState, Updater } from "@tanstack/react-table";

import { isPsdNumberFilterValue } from "../components/psd/data-grid/filters";

export type PsdStocksFiltersStore = {
  columnFilters: ColumnFiltersState;
  setColumnFilters: (filters: Updater<ColumnFiltersState>) => void;
  setFilterValue: (columnId: string, value: ColumnFilter["value"] | null) => void;
  resetFilters: () => void;
};

const STORAGE_KEY = "psd.stocks.filters.v2";
const LEGACY_STORAGE_KEY = "psd.stocks.filter";
const VALID_COLUMN_IDS = new Set([
  "symbol",
  "quantity",
  "markPrice",
  "dayPnlAmount",
  "delta",
]);

type InternalState = {
  columnFilters: ColumnFiltersState;
};

const listeners = new Set<() => void>();

const isColumnFiltersState = (value: unknown): value is ColumnFiltersState =>
  Array.isArray(value) &&
  value.every(
    (item) =>
      !!item &&
      typeof item === "object" &&
      typeof (item as ColumnFilter).id === "string",
  );

const sanitizeColumnFilters = (filters: ColumnFiltersState): ColumnFiltersState => {
  const byId = new Map<string, ColumnFilter>();
  for (const filter of filters) {
    if (!filter || typeof filter.id !== "string") {
      continue;
    }
    if (!VALID_COLUMN_IDS.has(filter.id)) {
      continue;
    }
    if (filter.id === "symbol") {
      if (typeof filter.value !== "string") {
        continue;
      }
      if (filter.value.trim().length === 0) {
        continue;
      }
      byId.set(filter.id, { id: filter.id, value: filter.value });
      continue;
    }
    if (!isPsdNumberFilterValue(filter.value)) {
      continue;
    }
    byId.set(filter.id, { id: filter.id, value: filter.value });
  }
  return Array.from(byId.values()).sort((a, b) => a.id.localeCompare(b.id));
};

const loadInitialState = (): InternalState => {
  if (typeof window === "undefined") {
    return { columnFilters: [] };
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw) as { columnFilters?: ColumnFiltersState };
      if (isColumnFiltersState(parsed?.columnFilters)) {
        return { columnFilters: sanitizeColumnFilters(parsed.columnFilters) };
      }
    }

    const legacy = window.localStorage.getItem(LEGACY_STORAGE_KEY);
    if (legacy && legacy.trim().length > 0) {
      const legacyFilters = sanitizeColumnFilters([
        { id: "symbol", value: legacy },
      ]);
      return { columnFilters: legacyFilters };
    }
  } catch {
    // ignore storage/JSON errors
  }
  return { columnFilters: [] };
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
    if (next.columnFilters.length === 0) {
      window.localStorage.removeItem(STORAGE_KEY);
      return;
    }
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ columnFilters: next.columnFilters }),
    );
  } catch {
    // ignore storage errors in non-browser environments
  }
};

const setState = (partial: Partial<InternalState>, options: { persist?: boolean } = {}) => {
  const next: InternalState = {
    ...state,
    ...partial,
  };
  if (next.columnFilters === state.columnFilters) {
    return;
  }
  state = next;
  if (options.persist) {
    persist(state);
  }
  notify();
};

const actions = {
  setColumnFilters(filters: Updater<ColumnFiltersState>) {
    const next =
      typeof filters === "function" ? filters(state.columnFilters) : filters;
    setState({ columnFilters: sanitizeColumnFilters(next) }, { persist: true });
  },
  setFilterValue(columnId: string, value: ColumnFilter["value"] | null) {
    const next = state.columnFilters.filter((filter) => filter.id !== columnId);
    if (value !== null && value !== undefined && value !== "") {
      next.push({ id: columnId, value });
    }
    setState({ columnFilters: sanitizeColumnFilters(next) }, { persist: true });
  },
  resetFilters() {
    setState({ columnFilters: [] }, { persist: true });
  },
};

const getState = (): PsdStocksFiltersStore => ({
  columnFilters: state.columnFilters,
  setColumnFilters: actions.setColumnFilters,
  setFilterValue: actions.setFilterValue,
  resetFilters: actions.resetFilters,
});

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};

export function usePsdStocksFilterStore<T>(
  selector: (store: PsdStocksFiltersStore) => T,
): T {
  return useSyncExternalStore(subscribe, () => selector(getState()), () =>
    selector(getState()),
  );
}
