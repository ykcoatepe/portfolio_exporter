import { useSyncExternalStore } from "react";

export type StocksFilterStore = {
  query: string;
  autoCleared: boolean;
  setQuery: (value: string) => void;
  reset: () => void;
  markAutoCleared: () => void;
};

const STORAGE_KEY = "psd.stocks.filter";

type InternalState = {
  query: string;
  autoCleared: boolean;
};

const listeners = new Set<() => void>();

const loadInitialQuery = (): string => {
  if (typeof window === "undefined") {
    return "";
  }
  try {
    const value = window.localStorage.getItem(STORAGE_KEY);
    return typeof value === "string" ? value : "";
  } catch {
    return "";
  }
};

const persistQuery = (query: string) => {
  if (typeof window === "undefined") {
    return;
  }
  try {
    if (query) {
      window.localStorage.setItem(STORAGE_KEY, query);
    } else {
      window.localStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    // ignore storage errors in non-browser environments
  }
};

let state: InternalState = {
  query: loadInitialQuery(),
  autoCleared: false,
};

const notify = () => {
  for (const listener of listeners) {
    listener();
  }
};

const setState = (partial: Partial<InternalState>, options: { persist?: boolean } = {}) => {
  const next: InternalState = {
    ...state,
    ...partial,
  };
  if (next.query === state.query && next.autoCleared === state.autoCleared) {
    return;
  }
  state = next;
  if (options.persist) {
    persistQuery(state.query);
  }
  notify();
};

const actions = {
  setQuery(value: string) {
    setState({ query: value }, { persist: true });
  },
  reset() {
    setState({ query: "" }, { persist: true });
  },
  markAutoCleared() {
    if (!state.autoCleared) {
      setState({ autoCleared: true });
    }
  },
};

const getState = (): StocksFilterStore => ({
  query: state.query,
  autoCleared: state.autoCleared,
  setQuery: actions.setQuery,
  reset: actions.reset,
  markAutoCleared: actions.markAutoCleared,
});

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};

export function useStocksFilterStore<T>(selector: (store: StocksFilterStore) => T): T {
  return useSyncExternalStore(subscribe, () => selector(getState()), () => selector(getState()));
}
