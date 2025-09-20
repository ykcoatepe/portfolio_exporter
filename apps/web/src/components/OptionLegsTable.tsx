import {
  forwardRef,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type {
  ChangeEvent,
  ForwardedRef,
  KeyboardEvent as ReactKeyboardEvent,
} from "react";
import clsx from "clsx";

import { useOptionLegs } from "../hooks/useOptions";
import { formatDuration, formatMoney, formatPercent } from "../lib/format";
import type { OptionLegRow } from "../lib/types";
import { MarkBadge } from "./MarkBadge";
import { deriveStalenessSeconds, formatSigned, stalenessTone, valueTone } from "./tableUtils";

const COLUMN_COUNT = 11;
const SKELETON_ROWS = Array.from({ length: 10 }, (_, idx) => idx);
const DEFAULT_DELTA_RANGE = { min: -1, max: 1 } as const;
const SHOULD_POLL = import.meta.env.MODE !== "test";

type ExpiryWindowId = "all" | "0-7" | "8-30" | "31-90" | "90+";
interface ExpiryWindow {
  id: ExpiryWindowId;
  label: string;
  min: number | null;
  max: number | null;
}

const EXPIRY_WINDOW_OPTIONS: ExpiryWindow[] = [
  { id: "all", label: "All", min: null, max: null },
  { id: "0-7", label: "0-7d", min: 0, max: 7 },
  { id: "8-30", label: "8-30d", min: 8, max: 30 },
  { id: "31-90", label: "31-90d", min: 31, max: 90 },
  { id: "90+", label: "90d+", min: 91, max: null },
];

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

function LegsSkeleton() {
  return (
    <tbody>
      {SKELETON_ROWS.map((key) => (
        <tr
          key={`legs-skeleton-${key}`}
          role="row"
          data-testid="skeleton-row"
          className="animate-pulse border-b border-slate-900/60 last:border-0"
        >
          {Array.from({ length: COLUMN_COUNT }).map((_, cellIdx) => (
            <td key={`legs-skeleton-${key}-${cellIdx}`} role="gridcell" className="px-3 py-4">
              <div className="h-3 w-full max-w-[8rem] rounded bg-slate-900" />
            </td>
          ))}
        </tr>
      ))}
    </tbody>
  );
}

type LegRowProps = {
  leg: OptionLegRow;
  isActive: boolean;
  onFocusRow: (index: number) => void;
  onRequestFocus: (index: number) => void;
  rowIndex: number;
  rowCount: number;
  now: number;
};

const LegRow = (
  { leg, isActive, onFocusRow, onRequestFocus, rowIndex, rowCount, now }: LegRowProps,
  ref: ForwardedRef<HTMLTableRowElement>,
) => {
  const stalenessSeconds = deriveStalenessSeconds(leg.markTime, now);
  const stalenessLabel = formatDuration(stalenessSeconds);
  const stalenessClass = stalenessTone(stalenessSeconds);

  const handleKeyDown = (event: ReactKeyboardEvent<HTMLTableRowElement>) => {
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        onRequestFocus(Math.min(rowCount - 1, rowIndex + 1));
        break;
      case "ArrowUp":
        event.preventDefault();
        onRequestFocus(Math.max(0, rowIndex - 1));
        break;
      case "Home":
        event.preventDefault();
        onRequestFocus(0);
        break;
      case "End":
        event.preventDefault();
        onRequestFocus(rowCount - 1);
        break;
      default:
        break;
    }
  };

  return (
    <tr
      ref={ref}
      role="row"
      aria-label="leg row"
      tabIndex={isActive ? 0 : -1}
      data-row-index={rowIndex}
      onFocus={() => onFocusRow(rowIndex)}
      onKeyDown={handleKeyDown}
      className="border-b border-slate-900/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/70 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
    >
      <th
        scope="row"
        role="rowheader"
        className="px-3 py-3 text-left text-sm font-semibold text-slate-100"
      >
        <div className="space-y-1">
          <span>{leg.underlying}</span>
          <span className="block text-xs uppercase tracking-wide text-slate-400">
            {leg.isOrphan ? "Orphan" : "Combo"}
          </span>
        </div>
      </th>
      <td role="gridcell" className="px-3 py-3 text-sm text-slate-200">
        <div className="space-y-1">
          <span className="font-medium text-slate-100">{leg.expiry}</span>
          <span className="block text-xs text-slate-400">{leg.dte}d</span>
        </div>
      </td>
      <td role="gridcell" className="px-3 py-3 text-sm text-slate-200">
        {leg.strike.toFixed(2)}
      </td>
      <td role="gridcell" className="px-3 py-3 text-xs font-semibold uppercase text-slate-300">
        {leg.right}
      </td>
      <td role="gridcell" className="px-3 py-3 text-sm text-slate-200">
        {leg.quantity}
      </td>
      <td role="gridcell" className="px-3 py-3 text-sm">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-slate-100">
            {formatMoney(leg.markPrice)}
          </span>
          <MarkBadge source={leg.markSource} />
        </div>
      </td>
      <td role="gridcell" className="px-3 py-3 text-sm text-slate-200">
        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
          <span className="text-slate-400">Δ</span>
          <span className={clsx("text-right", valueTone(leg.delta))}>
            {formatSigned(leg.delta)}
          </span>
          <span className="text-slate-400">Γ</span>
          <span className={clsx("text-right", valueTone(leg.gamma))}>
            {formatSigned(leg.gamma)}
          </span>
          <span className="text-slate-400">Θ</span>
          <span className={clsx("text-right", valueTone(leg.theta))}>
            {formatSigned(leg.theta)}
          </span>
          <span className="text-slate-400">ν</span>
          <span className={clsx("text-right", valueTone(leg.vega))}>
            {formatSigned(leg.vega)}
          </span>
        </div>
      </td>
      <td role="gridcell" className="px-3 py-3 text-sm text-slate-200">
        {leg.iv !== null ? (
          formatPercent(leg.iv, { alreadyScaled: true })
        ) : (
          <span className="text-slate-500">—</span>
        )}
      </td>
      <td role="gridcell" className="px-3 py-3 text-sm">
        <div className="space-y-1">
          <div className={clsx("text-sm font-semibold", valueTone(leg.dayPnlAmount))}>
            {formatMoney(leg.dayPnlAmount)}
            <span className="ml-2 text-xs text-slate-400">
              {formatPercent(leg.dayPnlPercent, {
                alreadyScaled: true,
                signDisplay: "always",
              })}
            </span>
          </div>
          <div className={clsx("text-xs", valueTone(leg.totalPnlAmount))}>
            {formatMoney(leg.totalPnlAmount)}
            <span className="ml-2 text-[0.7rem] text-slate-400">
              {formatPercent(leg.totalPnlPercent, {
                alreadyScaled: true,
                signDisplay: "always",
              })}
            </span>
          </div>
        </div>
      </td>
      <td role="gridcell" className={clsx("px-3 py-3 text-sm", stalenessClass)}>
        {stalenessLabel}
      </td>
      <td role="gridcell" className="px-3 py-3 text-xs text-slate-400">
        {leg.comboId ? leg.comboId : "—"}
      </td>
    </tr>
  );
};

const ForwardedLegRow = forwardRef<HTMLTableRowElement, LegRowProps>(LegRow);

function filterByWindow(leg: OptionLegRow, window: ExpiryWindow): boolean {
  if (window.id === "all" || (window.min === null && window.max === null)) {
    return true;
  }
  if (window.min !== null && leg.dte < window.min) {
    return false;
  }
  if (window.max !== null && leg.dte > window.max) {
    return false;
  }
  return true;
}

export function OptionLegsTable(): JSX.Element {
  const {
    data: legs = [],
    isLoading,
    isFetching,
    error,
    refetch,
    underlyings = [],
  } = useOptionLegs();
  const [selectedUnderlyings, setSelectedUnderlyings] = useState<string[]>([]);
  const [selectedWindow, setSelectedWindow] = useState<ExpiryWindow>(EXPIRY_WINDOW_OPTIONS[0]);
  const [deltaRange, setDeltaRange] = useState<{ min: number; max: number }>(
    DEFAULT_DELTA_RANGE,
  );
  const [onlyOrphans, setOnlyOrphans] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const [activeIndex, setActiveIndex] = useState(0);
  const rowRefs = useRef<Array<HTMLTableRowElement | null>>([]);

  useEffect(() => {
    if (!SHOULD_POLL) {
      return;
    }
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const toggleUnderlying = (symbol: string) => {
    setSelectedUnderlyings((prev) => {
      if (prev.includes(symbol)) {
        return prev.filter((item) => item !== symbol);
      }
      return [...prev, symbol];
    });
  };

  const resetUnderlyings = () => setSelectedUnderlyings([]);

  const handleDeltaChange = (bound: "min" | "max") => (event: ChangeEvent<HTMLInputElement>) => {
    const value = Number.parseFloat(event.target.value);
    if (Number.isNaN(value)) {
      return;
    }
    setDeltaRange((prev) => {
      const next = {
        ...prev,
        [bound]: clamp(value, -1, 1),
      };
      if (next.min > next.max) {
        return bound === "min"
          ? { min: next.max, max: next.max }
          : { min: next.min, max: next.min };
      }
      return next;
    });
  };

  const filteredLegs = useMemo(() => {
    return legs.filter((leg: OptionLegRow) => {
      if (onlyOrphans && !leg.isOrphan) {
        return false;
      }
      if (selectedUnderlyings.length > 0 && !selectedUnderlyings.includes(leg.underlying)) {
        return false;
      }
      if (!filterByWindow(leg, selectedWindow)) {
        return false;
      }
      if (Number.isFinite(deltaRange.min) && Number.isFinite(deltaRange.max) && leg.delta !== null) {
        if (leg.delta < deltaRange.min || leg.delta > deltaRange.max) {
          return false;
        }
      }
      return true;
    });
  }, [legs, onlyOrphans, selectedUnderlyings, selectedWindow, deltaRange]);

  useEffect(() => {
    if (filteredLegs.length === 0) {
      setActiveIndex(0);
      return;
    }
    if (activeIndex >= filteredLegs.length) {
      setActiveIndex(0);
    }
  }, [filteredLegs, activeIndex]);

  useEffect(() => {
    rowRefs.current = rowRefs.current.slice(0, filteredLegs.length);
  }, [filteredLegs.length]);

  const setFocusByIndex = (targetIndex: number) => {
    if (filteredLegs.length === 0) {
      return;
    }
    const constrained = Math.min(Math.max(targetIndex, 0), filteredLegs.length - 1);
    setActiveIndex(constrained);
    const row = rowRefs.current[constrained];
    if (row) {
      window.requestAnimationFrame(() => row.focus());
    }
  };

  const gridRowCount = filteredLegs.length + 1;

  if (error) {
    return (
      <div className="rounded-3xl border border-rose-500/40 bg-rose-950/30 p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="text-lg font-semibold text-rose-100">
              Failed to load option legs
            </h3>
            <p className="mt-2 text-sm text-rose-200/80">{error.message}</p>
          </div>
          <button
            type="button"
            onClick={() => refetch()}
            className="rounded-full border border-rose-400/50 px-4 py-2 text-sm font-medium text-rose-100 transition hover:bg-rose-900/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-rose-400"
          >
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-3xl border border-slate-900/60 bg-slate-950/40 backdrop-blur">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-slate-900/60 px-6 py-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">Option Legs</h2>
          <p className="text-xs text-slate-400">
            Filterable per underlying, DTE window, and orphan status.
          </p>
        </div>
        <button
          type="button"
          onClick={() => refetch()}
          className="rounded-full border border-slate-800 bg-slate-900 px-3 py-1.5 text-xs font-semibold uppercase tracking-wide text-slate-300 hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
        >
          Refresh
        </button>
      </div>

      <div className="space-y-4 border-b border-slate-900/60 px-6 py-4 text-xs text-slate-300">
        <div>
          <p className="mb-2 font-semibold uppercase tracking-wide text-slate-400">
            Underlyings
          </p>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={resetUnderlyings}
              aria-pressed={selectedUnderlyings.length === 0}
              className={clsx(
                "rounded-full border px-3 py-1.5 text-xs font-semibold uppercase tracking-wide transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500",
                selectedUnderlyings.length === 0
                  ? "border-sky-500/60 bg-sky-500/10 text-sky-100"
                  : "border-slate-800 bg-slate-900 text-slate-300 hover:bg-slate-800",
              )}
            >
              All
            </button>
            {underlyings.map((symbol: string) => {
              const isActive = selectedUnderlyings.includes(symbol);
              return (
                <button
                  key={symbol}
                  type="button"
                  aria-pressed={isActive}
                  onClick={() => toggleUnderlying(symbol)}
                  className={clsx(
                    "rounded-full border px-3 py-1.5 text-xs font-semibold uppercase tracking-wide transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500",
                    isActive
                      ? "border-sky-500/60 bg-sky-500/10 text-sky-100"
                      : "border-slate-800 bg-slate-900 text-slate-300 hover:bg-slate-800",
                  )}
                >
                  {symbol}
                </button>
              );
            })}
          </div>
        </div>

        <div>
          <p className="mb-2 font-semibold uppercase tracking-wide text-slate-400">
            Expiry Window
          </p>
          <div className="flex flex-wrap gap-2">
            {EXPIRY_WINDOW_OPTIONS.map((windowOption) => (
              <button
                key={windowOption.id}
                type="button"
                aria-pressed={selectedWindow.id === windowOption.id}
                onClick={() => setSelectedWindow(windowOption)}
                className={clsx(
                  "rounded-full border px-3 py-1.5 text-xs font-semibold uppercase tracking-wide transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500",
                  selectedWindow.id === windowOption.id
                    ? "border-sky-500/60 bg-sky-500/10 text-sky-100"
                    : "border-slate-800 bg-slate-900 text-slate-300 hover:bg-slate-800",
                )}
              >
                {windowOption.label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <label className="flex items-center gap-2">
            <span className="uppercase tracking-wide text-slate-400">Δ Min</span>
            <input
              type="number"
              step="0.05"
              min="-1"
              max="1"
              value={deltaRange.min}
              onChange={handleDeltaChange("min")}
              className="w-20 rounded-md border border-slate-800 bg-slate-900 px-2 py-1 text-sm text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
            />
          </label>
          <label className="flex items-center gap-2">
            <span className="uppercase tracking-wide text-slate-400">Δ Max</span>
            <input
              type="number"
              step="0.05"
              min="-1"
              max="1"
              value={deltaRange.max}
              onChange={handleDeltaChange("max")}
              className="w-20 rounded-md border border-slate-800 bg-slate-900 px-2 py-1 text-sm text-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
            />
          </label>
          <button
            type="button"
            onClick={() => setDeltaRange({ ...DEFAULT_DELTA_RANGE })}
            className="rounded-full border border-slate-800 bg-slate-900 px-3 py-1.5 text-xs font-semibold uppercase tracking-wide text-slate-300 hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
          >
            Reset Δ
          </button>
          <label className="ml-auto inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
            <input
              type="checkbox"
              checked={onlyOrphans}
              onChange={(event) => setOnlyOrphans(event.target.checked)}
              className="h-4 w-4 rounded border-slate-700 bg-slate-900 text-sky-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
            />
            Only orphan legs
          </label>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table
          role="grid"
          aria-label="Single option legs"
          aria-rowcount={gridRowCount}
          aria-colcount={COLUMN_COUNT}
          className="min-w-full divide-y divide-slate-900"
        >
          <thead>
            <tr role="row" className="text-xs uppercase tracking-wide text-slate-400">
              <th scope="col" role="columnheader" className="px-3 py-3 text-left">
                UL
              </th>
              <th scope="col" role="columnheader" className="px-3 py-3 text-left">
                Expiry
              </th>
              <th scope="col" role="columnheader" className="px-3 py-3 text-left">
                Strike
              </th>
              <th scope="col" role="columnheader" className="px-3 py-3 text-left">
                Right
              </th>
              <th scope="col" role="columnheader" className="px-3 py-3 text-left">
                Qty
              </th>
              <th scope="col" role="columnheader" className="px-3 py-3 text-left">
                Mark
              </th>
              <th scope="col" role="columnheader" className="px-3 py-3 text-left">
                Δ/Γ/Θ/ν
              </th>
              <th scope="col" role="columnheader" className="px-3 py-3 text-left">
                IV
              </th>
              <th scope="col" role="columnheader" className="px-3 py-3 text-left">
                Day/Unrealized P&amp;L
              </th>
              <th scope="col" role="columnheader" className="px-3 py-3 text-left">
                Staleness
              </th>
              <th scope="col" role="columnheader" className="px-3 py-3 text-left">
                Combo ID
              </th>
            </tr>
          </thead>
          {isLoading ? (
            <LegsSkeleton />
          ) : (
            <tbody data-testid="rows-body">
              {filteredLegs.map((leg: OptionLegRow, index: number) => (
                <ForwardedLegRow
                  key={leg.id}
                  ref={(node) => {
                    rowRefs.current[index] = node;
                  }}
                  leg={leg}
                  isActive={index === activeIndex}
                  onFocusRow={setActiveIndex}
                  onRequestFocus={setFocusByIndex}
                  rowIndex={index}
                  rowCount={filteredLegs.length}
                  now={now}
                />
              ))}
              {filteredLegs.length === 0 ? (
                <tr role="row">
                  <td
                    role="gridcell"
                    colSpan={COLUMN_COUNT}
                    className="px-4 py-10 text-center text-sm text-slate-400"
                  >
                    No option legs match the selected filters.
                  </td>
                </tr>
              ) : null}
            </tbody>
          )}
        </table>
      </div>

      {isFetching && !isLoading ? (
        <div className="flex items-center justify-end gap-2 border-t border-slate-900/70 px-4 py-2 text-xs text-slate-500">
          <span className="relative inline-flex h-2 w-2">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-sky-400/50" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-sky-400" />
          </span>
          Refreshing…
        </div>
      ) : null}
    </div>
  );
}

export default OptionLegsTable;
