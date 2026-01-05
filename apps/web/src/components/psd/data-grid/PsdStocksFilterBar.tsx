import { useEffect, useMemo, useRef, useState } from "react";
import clsx from "clsx";
import type { ColumnFiltersState, OnChangeFn } from "@tanstack/react-table";

import {
  formatNumberFilterValue,
  parseNumberFilterInput,
  type PsdNumberFilterValue,
} from "./filters";

type PsdStocksFilterBarProps = {
  columnFilters: ColumnFiltersState;
  onColumnFiltersChange: OnChangeFn<ColumnFiltersState>;
  onReset: () => void;
};

const findFilterValue = <T,>(filters: ColumnFiltersState, id: string): T | null => {
  const entry = filters.find((filter) => filter.id === id);
  return (entry?.value as T | null) ?? null;
};

export function PsdStocksFilterBar({
  columnFilters,
  onColumnFiltersChange,
  onReset,
}: PsdStocksFilterBarProps): JSX.Element {
  const symbolInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    function handleGlobalKeyDown(event: KeyboardEvent) {
      if (event.key !== "/" || event.metaKey || event.ctrlKey || event.altKey) {
        return;
      }
      const target = event.target as HTMLElement | null;
      if (target) {
        const tag = target.tagName.toLowerCase();
        if (tag === "input" || tag === "textarea" || target.isContentEditable) {
          return;
        }
      }
      event.preventDefault();
      symbolInputRef.current?.focus();
      symbolInputRef.current?.select();
    }

    window.addEventListener("keydown", handleGlobalKeyDown);
    return () => window.removeEventListener("keydown", handleGlobalKeyDown);
  }, []);

  const symbolFilter = useMemo(
    () => (findFilterValue<string>(columnFilters, "symbol") ?? ""),
    [columnFilters],
  );

  const quantityFilter = useMemo(
    () =>
      formatNumberFilterValue(
        findFilterValue<PsdNumberFilterValue>(columnFilters, "quantity"),
      ),
    [columnFilters],
  );

  const dayPnlFilter = useMemo(
    () =>
      formatNumberFilterValue(
        findFilterValue<PsdNumberFilterValue>(columnFilters, "dayPnlAmount"),
      ),
    [columnFilters],
  );

  const [quantityInput, setQuantityInput] = useState(quantityFilter);
  const [dayPnlInput, setDayPnlInput] = useState(dayPnlFilter);

  useEffect(() => {
    setQuantityInput(quantityFilter);
  }, [quantityFilter]);

  useEffect(() => {
    setDayPnlInput(dayPnlFilter);
  }, [dayPnlFilter]);

  const setFilterValue = (columnId: string, value: unknown | null) => {
    const next = columnFilters.filter((filter) => filter.id !== columnId);
    if (value !== null && value !== undefined && value !== "") {
      next.push({ id: columnId, value });
    }
    onColumnFiltersChange(next);
  };

  return (
    <div className="flex flex-wrap items-end gap-3 rounded-2xl border border-slate-900/60 bg-slate-950/40 px-4 py-3">
      <label className="flex flex-col gap-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
        Symbol
        <input
          ref={symbolInputRef}
          type="text"
          value={symbolFilter}
          onChange={(event) => setFilterValue("symbol", event.target.value)}
          placeholder="Filter symbol"
          aria-label="Filter symbols"
          className={clsx(
            "w-48 rounded-md border border-slate-800 bg-slate-900 px-2 py-1 text-sm text-slate-100",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500",
          )}
        />
      </label>

      <label className="flex flex-col gap-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
        Qty
        <input
          type="text"
          value={quantityInput}
          onChange={(event) => {
            const nextValue = event.target.value;
            setQuantityInput(nextValue);
            if (!nextValue.trim()) {
              setFilterValue("quantity", null);
              return;
            }
            const parsed = parseNumberFilterInput(nextValue);
            if (parsed) {
              setFilterValue("quantity", parsed);
            }
          }}
          placeholder=">= 0 or 10-20"
          aria-label="Filter quantity"
          className={clsx(
            "w-40 rounded-md border border-slate-800 bg-slate-900 px-2 py-1 text-sm text-slate-100",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500",
          )}
        />
      </label>

      <label className="flex flex-col gap-1 text-xs font-semibold uppercase tracking-wide text-slate-400">
        Day P&L
        <input
          type="text"
          value={dayPnlInput}
          onChange={(event) => {
            const nextValue = event.target.value;
            setDayPnlInput(nextValue);
            if (!nextValue.trim()) {
              setFilterValue("dayPnlAmount", null);
              return;
            }
            const parsed = parseNumberFilterInput(nextValue);
            if (parsed) {
              setFilterValue("dayPnlAmount", parsed);
            }
          }}
          placeholder=">= 0 or -50-10"
          aria-label="Filter day pnl"
          className={clsx(
            "w-40 rounded-md border border-slate-800 bg-slate-900 px-2 py-1 text-sm text-slate-100",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500",
          )}
        />
      </label>

      <button
        type="button"
        onClick={onReset}
        className="ml-auto rounded-full border border-slate-800 bg-slate-900 px-3 py-1.5 text-xs font-semibold uppercase tracking-wide text-slate-300 hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
      >
        Reset filters
      </button>

      <span className="text-xs uppercase tracking-wide text-slate-500">
        Press / to focus
      </span>
    </div>
  );
}

export default PsdStocksFilterBar;
