import {
  Fragment,
  forwardRef,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type {
  ForwardedRef,
  KeyboardEvent as ReactKeyboardEvent,
  MouseEvent,
} from "react";
import clsx from "clsx";

import { useOptionCombos } from "../hooks/useOptions";
import { formatDuration, formatMoney, formatPercent } from "../lib/format";
import type { OptionComboLegRow, OptionComboRow } from "../lib/types";
import { MarkBadge } from "./MarkBadge";
import { deriveStalenessSeconds, formatSigned, stalenessTone, valueTone } from "./tableUtils";

const COLUMN_COUNT = 8;
const SKELETON_ROWS = Array.from({ length: 6 }, (_, idx) => idx);
const SHOULD_POLL = import.meta.env.MODE !== "test";

function CombosSkeleton() {
  return (
    <tbody>
      {SKELETON_ROWS.map((key) => (
        <tr
          key={`combo-skeleton-${key}`}
          role="row"
          data-testid="skeleton-row"
          className="animate-pulse border-b border-slate-900/60 last:border-0"
        >
          {Array.from({ length: COLUMN_COUNT }).map((_, cellIndex) => (
            <td key={`skeleton-cell-${key}-${cellIndex}`} role="gridcell" className="px-4 py-5">
              <div className="h-3 w-full max-w-[9rem] rounded bg-slate-900" />
            </td>
          ))}
        </tr>
      ))}
    </tbody>
  );
}

function ComboLegsDetail({ legs }: { legs: OptionComboLegRow[] }) {
  if (!legs.length) {
    return (
      <div className="rounded-xl border border-slate-900/60 bg-slate-950/50 p-4 text-sm text-slate-400">
        No legs attached to this combo.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-slate-900 text-sm text-slate-200">
        <thead>
          <tr className="text-xs uppercase tracking-wide text-slate-400">
            <th scope="col" className="px-3 py-2 text-left">
              Strike
            </th>
            <th scope="col" className="px-3 py-2 text-left">
              Right
            </th>
            <th scope="col" className="px-3 py-2 text-left">
              Qty
            </th>
            <th scope="col" className="px-3 py-2 text-left">
              Mark
            </th>
            <th scope="col" className="px-3 py-2 text-left">
              Δ
            </th>
            <th scope="col" className="px-3 py-2 text-left">
              Θ
            </th>
            <th scope="col" className="px-3 py-2 text-left">
              Day P&amp;L
            </th>
            <th scope="col" className="px-3 py-2 text-left">
              Unrealized P&amp;L
            </th>
          </tr>
        </thead>
        <tbody>
          {legs.map((leg) => (
            <tr key={leg.id} className="border-b border-slate-900/60 last:border-0">
              <td className="px-3 py-2 text-sm font-semibold text-slate-100">
                {leg.strike.toFixed(2)}
              </td>
              <td className="px-3 py-2 text-xs font-semibold uppercase text-slate-300">
                {leg.right}
              </td>
              <td className="px-3 py-2 text-sm text-slate-200">{leg.quantity}</td>
              <td className="px-3 py-2 text-sm text-slate-200">
                {formatMoney(leg.markPrice)}
              </td>
              <td className={clsx("px-3 py-2 text-sm", valueTone(leg.delta))}>
                {formatSigned(leg.delta)}
              </td>
              <td className={clsx("px-3 py-2 text-sm", valueTone(leg.theta))}>
                {formatSigned(leg.theta)}
              </td>
              <td className={clsx("px-3 py-2 text-sm", valueTone(leg.dayPnlAmount))}>
                {formatMoney(leg.dayPnlAmount)}
              </td>
              <td className={clsx("px-3 py-2 text-sm", valueTone(leg.totalPnlAmount))}>
                {formatMoney(leg.totalPnlAmount)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

type ComboRowProps = {
  combo: OptionComboRow;
  isExpanded: boolean;
  isActive: boolean;
  onToggle: (id: string) => void;
  onFocusRow: (index: number) => void;
  onRequestFocus: (index: number) => void;
  rowIndex: number;
  rowCount: number;
  now: number;
};

const ComboRow = (
  {
    combo,
    isExpanded,
    isActive,
    onToggle,
    onFocusRow,
    onRequestFocus,
    rowIndex,
    rowCount,
    now,
  }: ComboRowProps,
  ref: ForwardedRef<HTMLTableRowElement>,
) => {
  const stalenessSeconds = deriveStalenessSeconds(combo.markTime, now);
  const stalenessLabel = formatDuration(stalenessSeconds);
  const stalenessClass = stalenessTone(stalenessSeconds);

  const handleKeyDown = (event: ReactKeyboardEvent<HTMLTableRowElement>) => {
    if (event.defaultPrevented) {
      return;
    }
    switch (event.key) {
      case "ArrowDown": {
        event.preventDefault();
        onRequestFocus(Math.min(rowCount - 1, rowIndex + 1));
        break;
      }
      case "ArrowUp": {
        event.preventDefault();
        onRequestFocus(Math.max(0, rowIndex - 1));
        break;
      }
      case "Home": {
        event.preventDefault();
        onRequestFocus(0);
        break;
      }
      case "End": {
        event.preventDefault();
        onRequestFocus(rowCount - 1);
        break;
      }
      case "Enter":
      case " ":
      case "ArrowRight": {
        event.preventDefault();
        onToggle(combo.id);
        break;
      }
      case "ArrowLeft": {
        if (isExpanded) {
          event.preventDefault();
          onToggle(combo.id);
        }
        break;
      }
      default:
        break;
    }
  };

  const handleClick = (event: MouseEvent<HTMLTableRowElement>) => {
    if ((event.target as HTMLElement).closest("button")) {
      return;
    }
    onToggle(combo.id);
  };

  const netLabel = combo.side === "credit" ? "Credit" : "Debit";
  const netValue = formatMoney(Math.abs(combo.netPremium));

  return (
    <Fragment>
      <tr
        ref={ref}
        role="row"
        aria-label="combo row"
        aria-expanded={isExpanded}
        tabIndex={isActive ? 0 : -1}
        data-row-index={rowIndex}
        onFocus={() => onFocusRow(rowIndex)}
        onClick={handleClick}
        onKeyDown={handleKeyDown}
        className="cursor-pointer border-b border-slate-900/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/70 focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950"
      >
        <th
          scope="row"
          role="rowheader"
          className="px-4 py-4 text-left text-sm font-semibold text-slate-100"
        >
          <div className="flex items-center gap-3">
            <button
              type="button"
              className={clsx(
                "flex h-7 w-7 items-center justify-center rounded-full border border-slate-800 bg-slate-900 text-sm text-slate-300 transition hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500",
                isExpanded ? "font-medium" : "font-semibold",
              )}
              onClick={(event) => {
                event.stopPropagation();
                onToggle(combo.id);
              }}
              aria-label={`${isExpanded ? "Collapse" : "Expand"} ${combo.strategy}`}
              aria-expanded={isExpanded}
              aria-controls={`combo-legs-${combo.id}`}
            >
              {isExpanded ? "−" : "+"}
            </button>
            <div className="space-y-1">
              <span>{combo.strategy}</span>
              <p className="text-xs font-normal text-slate-400">
                {combo.underlying} • Exp {combo.expiry}
              </p>
            </div>
          </div>
        </th>
        <td role="gridcell" className="px-4 py-4 text-sm text-slate-200">
          <div className="space-y-1">
            <span className="font-medium text-slate-100">{combo.underlying}</span>
            <span className="block text-xs text-slate-400">
              ΣΔ {formatSigned(combo.delta)}
            </span>
          </div>
        </td>
        <td role="gridcell" className="px-4 py-4 text-sm text-slate-200">
          {combo.dte}d
        </td>
        <td role="gridcell" className="px-4 py-4 text-sm text-slate-200">
          <div className="space-y-1">
            <span className="text-xs uppercase tracking-wide text-slate-400">{netLabel}</span>
            <span className="text-sm font-semibold text-slate-100">{netValue}</span>
          </div>
        </td>
        <td role="gridcell" className="px-4 py-4 text-sm text-slate-200">
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
            <span className="text-slate-400">Δ</span>
            <span className={clsx("text-right", valueTone(combo.delta))}>
              {formatSigned(combo.delta)}
            </span>
            <span className="text-slate-400">Γ</span>
            <span className={clsx("text-right", valueTone(combo.gamma))}>
              {formatSigned(combo.gamma)}
            </span>
            <span className="text-slate-400">Θ</span>
            <span className={clsx("text-right", valueTone(combo.theta))}>
              {formatSigned(combo.theta)}
            </span>
            <span className="text-slate-400">ν</span>
            <span className={clsx("text-right", valueTone(combo.vega))}>
              {formatSigned(combo.vega)}
            </span>
          </div>
        </td>
        <td role="gridcell" className="px-4 py-4 text-sm">
          <div className="space-y-1">
            <div className={clsx("text-sm font-semibold", valueTone(combo.dayPnlAmount))}>
              {formatMoney(combo.dayPnlAmount)}
              <span className="ml-2 text-xs text-slate-400">
                {formatPercent(combo.dayPnlPercent, {
                  alreadyScaled: true,
                  signDisplay: "always",
                })}
              </span>
            </div>
            <div className={clsx("text-xs", valueTone(combo.totalPnlAmount))}>
              {formatMoney(combo.totalPnlAmount)}
              <span className="ml-2 text-[0.7rem] text-slate-400">
                {formatPercent(combo.totalPnlPercent, {
                  alreadyScaled: true,
                  signDisplay: "always",
                })}
              </span>
            </div>
          </div>
        </td>
        <td role="gridcell" className="px-4 py-4 text-sm">
          <div className="flex items-center gap-2">
            <span className="text-sm font-semibold text-slate-100">
              {formatMoney(combo.markPrice)}
            </span>
            <MarkBadge source={combo.markSource} />
          </div>
        </td>
        <td role="gridcell" className={clsx("px-4 py-4 text-sm", stalenessClass)}>
          {stalenessLabel}
        </td>
      </tr>
      {isExpanded ? (
        <tr
          role="row"
          aria-label="combo detail row"
          id={`combo-legs-${combo.id}`}
          className="border-b border-slate-900/70 bg-slate-950/40"
        >
          <td role="gridcell" colSpan={COLUMN_COUNT} className="px-6 pb-6 pt-2">
            <ComboLegsDetail legs={combo.legs} />
          </td>
        </tr>
      ) : null}
    </Fragment>
  );
};

const ForwardedComboRow = forwardRef<HTMLTableRowElement, ComboRowProps>(ComboRow);

export function CombosTable(): JSX.Element {
  const { data: combos = [], isLoading, isFetching, error, refetch } = useOptionCombos();
  const [expandedId, setExpandedId] = useState<string | null>(null);
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

  useEffect(() => {
    if (expandedId && !combos.some((combo: OptionComboRow) => combo.id === expandedId)) {
      setExpandedId(null);
    }
  }, [combos, expandedId]);

  useEffect(() => {
    if (combos.length === 0) {
      return;
    }
    if (activeIndex >= combos.length) {
      setActiveIndex(0);
    }
  }, [combos, activeIndex]);

  useEffect(() => {
    rowRefs.current = rowRefs.current.slice(0, combos.length);
  }, [combos.length]);

  const rowCount = combos.length;

  const setFocusByIndex = (targetIndex: number) => {
    if (rowCount === 0) {
      return;
    }
    const constrained = Math.min(Math.max(targetIndex, 0), rowCount - 1);
    setActiveIndex(constrained);
    const row = rowRefs.current[constrained];
    if (row) {
      window.requestAnimationFrame(() => row.focus());
    }
  };

  const gridRowCount = useMemo(() => {
    if (!rowCount) {
      return 1;
    }
    return rowCount + 1 + (expandedId ? 1 : 0);
  }, [rowCount, expandedId]);

  if (error) {
    return (
      <div className="rounded-3xl border border-rose-500/40 bg-rose-950/30 p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="text-lg font-semibold text-rose-100">
              Failed to load options combos
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
      <div className="flex items-center justify-between border-b border-slate-900/60 px-6 py-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">Options Combos</h2>
          <p className="text-xs text-slate-400">
            Aggregated strategies with keyboard navigation.
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

      <div className="overflow-x-auto">
        <table
          role="grid"
          aria-label="Options combos positions"
          aria-rowcount={gridRowCount}
          aria-colcount={COLUMN_COUNT}
          className="min-w-full divide-y divide-slate-900"
        >
          <thead>
            <tr role="row" className="text-xs uppercase tracking-wide text-slate-400">
              <th scope="col" role="columnheader" className="px-4 py-3 text-left">
                Strategy
              </th>
              <th scope="col" role="columnheader" className="px-4 py-3 text-left">
                Underlying
              </th>
              <th scope="col" role="columnheader" className="px-4 py-3 text-left">
                DTE
              </th>
              <th scope="col" role="columnheader" className="px-4 py-3 text-left">
                Net Credit/Debit
              </th>
              <th scope="col" role="columnheader" className="px-4 py-3 text-left">
                ΣΔ/Γ/Θ/ν
              </th>
              <th scope="col" role="columnheader" className="px-4 py-3 text-left">
                Day/Unrealized P&amp;L
              </th>
              <th scope="col" role="columnheader" className="px-4 py-3 text-left">
                Mark
              </th>
              <th scope="col" role="columnheader" className="px-4 py-3 text-left">
                Staleness
              </th>
            </tr>
          </thead>
          {isLoading ? (
            <CombosSkeleton />
          ) : (
            <tbody data-testid="rows-body">
              {combos.map((combo: OptionComboRow, index: number) => (
                <ForwardedComboRow
                  key={combo.id}
                  ref={(node) => {
                    rowRefs.current[index] = node;
                  }}
                  combo={combo}
                  isExpanded={expandedId === combo.id}
                  isActive={index === activeIndex}
                  onToggle={(id) =>
                    setExpandedId((current) => (current === id ? null : id))
                  }
                  onFocusRow={setActiveIndex}
                  onRequestFocus={setFocusByIndex}
                  rowIndex={index}
                  rowCount={rowCount}
                  now={now}
                />
              ))}
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

export default CombosTable;
