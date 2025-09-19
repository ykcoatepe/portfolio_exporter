import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent as ReactKeyboardEvent } from "react";
import clsx from "clsx";

import { MarkBadge } from "./MarkBadge";
import { useStocks } from "../hooks/useStocks";
import { formatDuration, formatMoney, formatPercent } from "../lib/format";
import type { StockRow } from "../lib/types";

const SKELETON_ROWS = Array.from({ length: 8 }, (_, idx) => idx);
const COLUMN_COUNT = 7;
const SHOULD_POLL = import.meta.env.MODE !== "test";


const severityTone: Record<string, string> = {
  CRITICAL: "bg-rose-500/10 text-rose-300 border border-rose-400/40",
  WARNING: "bg-amber-500/10 text-amber-300 border border-amber-400/40",
  INFO: "bg-sky-500/10 text-sky-200 border border-sky-400/40",
};

const placeholderBreaches = [
  {
    severity: "CRITICAL",
    title: "Max drawdown exceeded",
    subtitle: "13m ago • Risk engine",
  },
  {
    severity: "WARNING",
    title: "VWAP drift over 2%",
    subtitle: "32m ago • Sentinel",
  },
  {
    severity: "INFO",
    title: "Price gap vs. peers",
    subtitle: "47m ago • Analytics",
  },
];

function valueTone(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value) || value === 0) {
    return "text-slate-300";
  }
  return value > 0 ? "text-emerald-300" : "text-rose-300";
}

function stalenessTone(seconds: number | null): string {
  if (seconds === null) {
    return "text-slate-300";
  }
  if (seconds >= 900) {
    return "text-rose-300";
  }
  if (seconds >= 300) {
    return "text-amber-300";
  }
  return "text-emerald-300";
}

function deriveStalenessSeconds(markTime: string | null, now: number): number | null {
  if (!markTime) {
    return null;
  }
  const ts = Date.parse(markTime);
  if (Number.isNaN(ts)) {
    return null;
  }
  return Math.max(0, Math.floor((now - ts) / 1000));
}

function StocksTableSkeleton() {
  return (
    <tbody>
      {SKELETON_ROWS.map((key) => (
        <tr
          key={`skeleton-${key}`}
          role="row"
          className="animate-pulse border-b border-slate-800/60 last:border-0"
        >
          <td role="gridcell" className="px-4 py-4">
            <div className="h-3 w-16 rounded bg-slate-800" />
          </td>
          <td role="gridcell" className="px-4 py-4">
            <div className="h-3 w-10 rounded bg-slate-800" />
          </td>
          <td role="gridcell" className="px-4 py-4">
            <div className="h-3 w-16 rounded bg-slate-800" />
          </td>
          <td role="gridcell" className="px-4 py-4">
            <div className="flex items-center gap-2">
              <div className="h-3 w-16 rounded bg-slate-800" />
              <div className="h-5 w-12 rounded-full bg-slate-800" />
            </div>
          </td>
          <td role="gridcell" className="px-4 py-4">
            <div className="h-3 w-20 rounded bg-slate-800" />
          </td>
          <td role="gridcell" className="px-4 py-4">
            <div className="h-3 w-20 rounded bg-slate-800" />
          </td>
          <td role="gridcell" className="px-4 py-4">
            <div className="h-3 w-14 rounded bg-slate-800" />
          </td>
        </tr>
      ))}
    </tbody>
  );
}

function ExpansionDrawer({ symbol }: { symbol: string }) {
  return (
    <div className="grid gap-6 rounded-xl border border-slate-800/80 bg-slate-900/60 p-4 sm:grid-cols-2">
      <div>
        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Fundamentals</h4>
        <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3 text-sm text-slate-200">
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500">Market Cap</dt>
            <dd className="mt-1 text-slate-100">Coming soon</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500">P/E</dt>
            <dd className="mt-1 text-slate-100">Pending</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500">Beta</dt>
            <dd className="mt-1 text-slate-100">Pending</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-slate-500">Next Earnings</dt>
            <dd className="mt-1 text-slate-100">TBD</dd>
          </div>
        </dl>
      </div>
      <div>
        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Recent Breaches</h4>
        <ul className="mt-3 space-y-2 text-sm">
          {placeholderBreaches.map((item) => (
            <li key={`${symbol}-${item.title}`} className="flex items-start gap-3 rounded-lg border border-slate-800/60 bg-slate-950/40 p-3">
              <span className={clsx("rounded-full px-2 py-0.5 text-[0.65rem] font-semibold uppercase tracking-wide", severityTone[item.severity])}>
                {item.severity}
              </span>
              <div>
                <p className="text-sm font-semibold text-slate-100">{item.title}</p>
                <p className="text-xs text-slate-400">{item.subtitle}</p>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export function StocksTable(): JSX.Element {
  const { data, isLoading, isFetching, error, refetch } = useStocks();
  const [filter, setFilter] = useState("");
  const [expandedSymbol, setExpandedSymbol] = useState<string | null>(null);
  const [activeSymbol, setActiveSymbol] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [sortDirection, setSortDirection] = useState<"ascending" | "descending">(
    "descending",
  );
  const filterRef = useRef<HTMLInputElement>(null);
  const rowRefs = useRef<Record<string, HTMLTableRowElement | null>>({});

  useEffect(() => {
    if (!SHOULD_POLL) {
      return;
    }
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

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
      filterRef.current?.focus();
      filterRef.current?.select();
    }

    window.addEventListener("keydown", handleGlobalKeyDown);
    return () => window.removeEventListener("keydown", handleGlobalKeyDown);
  }, []);

  const sortedRows = useMemo(() => {
    const rows = [...data];
    return rows.sort((a, b) => {
      const delta = a.dayPnlAmount - b.dayPnlAmount;
      return sortDirection === "ascending" ? delta : -delta;
    });
  }, [data, sortDirection]);

  const filteredRows = useMemo(() => {
    const trimmed = filter.trim().toUpperCase();
    if (!trimmed) {
      return sortedRows;
    }
    return sortedRows.filter((row) => row.symbol.toUpperCase().includes(trimmed));
  }, [sortedRows, filter]);

  useEffect(() => {
    if (!expandedSymbol) {
      return;
    }
    if (!filteredRows.some((row) => row.symbol === expandedSymbol)) {
      setExpandedSymbol(null);
    }
  }, [expandedSymbol, filteredRows]);

  useEffect(() => {
    if (filteredRows.length === 0) {
      if (activeSymbol !== null) {
        setActiveSymbol(null);
      }
      return;
    }

    if (!activeSymbol || !filteredRows.some((row) => row.symbol === activeSymbol)) {
      setActiveSymbol(filteredRows[0].symbol);
    }
  }, [filteredRows, activeSymbol]);

  const showSkeleton = isLoading;
  const showEmpty = !isLoading && !error && filteredRows.length === 0;
  const bodyRowCount = showSkeleton ? SKELETON_ROWS.length : showEmpty ? 1 : filteredRows.length;
  const totalRowCount = bodyRowCount + 1;

  function toggleRow(symbol: string) {
    setExpandedSymbol((prev) => (prev === symbol ? null : symbol));
  }

  function toggleSortDirection() {
    setSortDirection((prev) => (prev === "descending" ? "ascending" : "descending"));
  }

  function focusRowBySymbol(symbol?: string) {
    if (!symbol) {
      return;
    }
    setActiveSymbol(symbol);
    const focusNode = () => {
      const node = rowRefs.current[symbol];
      node?.focus();
    };
    if (typeof window !== "undefined" && typeof window.requestAnimationFrame === "function") {
      window.requestAnimationFrame(focusNode);
    } else {
      setTimeout(focusNode, 0);
    }
  }

  function handleRowKeyDown(
    event: ReactKeyboardEvent<HTMLTableRowElement>,
    row: StockRow,
    orderIndex: number,
  ) {
    switch (event.key) {
      case "ArrowDown": {
        event.preventDefault();
        const nextIndex = Math.min(filteredRows.length - 1, orderIndex + 1);
        focusRowBySymbol(filteredRows[nextIndex]?.symbol);
        return;
      }
      case "ArrowUp": {
        event.preventDefault();
        const prevIndex = Math.max(0, orderIndex - 1);
        focusRowBySymbol(filteredRows[prevIndex]?.symbol);
        return;
      }
      case "Home": {
        event.preventDefault();
        focusRowBySymbol(filteredRows[0]?.symbol);
        return;
      }
      case "End": {
        event.preventDefault();
        focusRowBySymbol(filteredRows[filteredRows.length - 1]?.symbol);
        return;
      }
      case "Enter":
      case " ":
      case "Space":
      case "Spacebar": {
        event.preventDefault();
        toggleRow(row.symbol);
        return;
      }
      default:
        break;
    }
  }

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-950/80 shadow-xl shadow-slate-950/40">
      <div className="flex flex-wrap items-center gap-3 border-b border-slate-800/80 px-4 py-3">
        <div className="mr-auto">
          <h2 className="text-base font-semibold text-slate-100">Single Stocks</h2>
          <p className="text-xs text-slate-400">Sorted by Day P&L · press / to filter</p>
        </div>
        <div className="relative">
          <input
            ref={filterRef}
            type="search"
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
            placeholder="Filter by symbol"
            className="w-48 rounded-full border border-slate-700 bg-slate-900/80 px-4 py-2 text-sm text-slate-100 placeholder:text-slate-500 focus:border-sky-500 focus:outline-none"
            aria-label="Filter symbols"
          />
          <span className="absolute inset-y-0 right-3 flex items-center text-[0.65rem] uppercase tracking-wide text-slate-500">/</span>
        </div>
      </div>

      {error ? (
        <div className="border-b border-slate-800 bg-rose-950/40 px-4 py-3 text-sm text-rose-200">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span>Unable to load stocks right now.</span>
            <button
              type="button"
              onClick={() => refetch()}
              className="rounded-full border border-rose-400/60 bg-rose-500/10 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-rose-200 hover:bg-rose-500/20"
            >
              Retry
            </button>
          </div>
        </div>
      ) : null}

      <div className="overflow-x-auto">
        <table
          role="grid"
          aria-label="Single stocks positions"
          aria-rowcount={totalRowCount}
          aria-colcount={COLUMN_COUNT}
          aria-busy={isLoading || isFetching ? true : undefined}
          className="min-w-full border-collapse text-sm text-slate-200"
        >
          <thead>
            <tr
              role="row"
              className="border-b border-slate-800/80 bg-slate-950/60 text-xs uppercase tracking-wide text-slate-400"
            >
              <th scope="col" role="columnheader" className="px-4 py-3 text-left">
                Symbol
              </th>
              <th scope="col" role="columnheader" className="px-4 py-3 text-right">
                Qty
              </th>
              <th scope="col" role="columnheader" className="px-4 py-3 text-right">
                Avg
              </th>
              <th scope="col" role="columnheader" className="px-4 py-3 text-right">
                Mark
              </th>
              <th
                scope="col"
                role="columnheader"
                aria-sort={sortDirection}
                className="px-4 py-3 text-right"
              >
                <button
                  type="button"
                  onClick={toggleSortDirection}
                  className="inline-flex items-center gap-2 rounded-full px-2 py-1 text-xs font-semibold uppercase tracking-wide text-slate-200 transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
                >
                  Day P&amp;L
                  <span aria-hidden className="text-[0.65rem] font-normal text-slate-500">
                    {sortDirection === "descending" ? "▼" : "▲"}
                  </span>
                </button>
              </th>
              <th scope="col" role="columnheader" className="px-4 py-3 text-right">
                Total P&amp;L
              </th>
              <th scope="col" role="columnheader" className="px-4 py-3 text-right">
                Staleness
              </th>
            </tr>
          </thead>

          {showSkeleton ? (
            <StocksTableSkeleton />
          ) : (
            <tbody>
              {filteredRows.map((row, orderIndex) => {
                const { symbol } = row;
                const isExpanded = expandedSymbol === symbol;
                const stalenessSeconds = deriveStalenessSeconds(row.markTime, now);
                const isActiveRow = activeSymbol ? activeSymbol === symbol : orderIndex === 0;
                const ariaRowIndex = orderIndex + 2;
                return (
                  <Fragment key={symbol}>
                    <tr
                      ref={(node) => {
                        if (node) {
                          rowRefs.current[symbol] = node;
                        } else {
                          delete rowRefs.current[symbol];
                        }
                      }}
                      role="row"
                      tabIndex={isActiveRow ? 0 : -1}
                      aria-selected={isActiveRow}
                      aria-expanded={isExpanded}
                      aria-rowindex={ariaRowIndex}
                      className={clsx(
                        "border-b border-slate-900/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-400 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950",
                        isExpanded ? "bg-slate-900/70" : "hover:bg-slate-900/40",
                      )}
                      onClick={() => {
                        focusRowBySymbol(symbol);
                        toggleRow(symbol);
                      }}
                      onFocus={() => setActiveSymbol(symbol)}
                      onKeyDown={(event) => handleRowKeyDown(event, row, orderIndex)}
                    >
                      <th
                        scope="row"
                        role="rowheader"
                        className="px-4 py-3 font-semibold tracking-wide text-slate-100"
                      >
                        <div className="flex items-center gap-2">
                          <span>{symbol}</span>
                          <span
                            aria-hidden
                            className={clsx(
                              "inline-flex h-5 w-5 items-center justify-center rounded-full border border-slate-800/70 text-[0.6rem]",
                              isExpanded ? "bg-slate-800 text-slate-200" : "text-slate-500",
                            )}
                          >
                            {isExpanded ? "−" : "+"}
                          </span>
                        </div>
                      </th>
                      <td
                        role="gridcell"
                        className="px-4 py-3 text-right font-mono text-sm text-slate-200"
                      >
                        {row.quantity.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                      </td>
                      <td
                        role="gridcell"
                        className="px-4 py-3 text-right font-mono text-sm text-slate-200"
                      >
                        {formatMoney(row.averagePrice, { currency: row.currency })}
                      </td>
                      <td role="gridcell" className="px-4 py-3 text-right font-mono text-sm">
                        <div className="flex items-center justify-end gap-3">
                          <span>{formatMoney(row.markPrice, { currency: row.currency })}</span>
                          <MarkBadge source={row.markSource} />
                        </div>
                      </td>
                      <td role="gridcell" className="px-4 py-3 text-right">
                        <div className="flex flex-col items-end gap-1">
                          <span className={clsx("font-mono text-sm", valueTone(row.dayPnlAmount))}>
                            {formatMoney(row.dayPnlAmount, { currency: row.currency, signDisplay: "always" })}
                          </span>
                          <span className={clsx("text-xs", valueTone(row.dayPnlPercent))}>
                            {formatPercent(row.dayPnlPercent, { alreadyScaled: true, signDisplay: "always" })}
                          </span>
                        </div>
                      </td>
                      <td role="gridcell" className="px-4 py-3 text-right">
                        <div className="flex flex-col items-end gap-1">
                          <span className={clsx("font-mono text-sm", valueTone(row.totalPnlAmount))}>
                            {formatMoney(row.totalPnlAmount, { currency: row.currency, signDisplay: "always" })}
                          </span>
                          <span className={clsx("text-xs", valueTone(row.totalPnlPercent))}>
                            {formatPercent(row.totalPnlPercent, { alreadyScaled: true, signDisplay: "always" })}
                          </span>
                        </div>
                      </td>
                      <td role="gridcell" className="px-4 py-3 text-right font-mono text-sm">
                        <span className={stalenessTone(stalenessSeconds)}>
                          {formatDuration(stalenessSeconds)}
                        </span>
                      </td>
                    </tr>
                    {isExpanded ? (
                      <tr role="row" className="border-b border-slate-900/60 bg-slate-950/60">
                        <td role="gridcell" colSpan={COLUMN_COUNT} className="px-4 py-4">
                          <ExpansionDrawer symbol={symbol} />
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                );
              })}
              {showEmpty ? (
                <tr role="row">
                  <td
                    role="gridcell"
                    className="px-4 py-6 text-center text-sm text-slate-400"
                    colSpan={COLUMN_COUNT}
                  >
                    No matching positions. Clear filters to see all symbols.
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

export default StocksTable;
