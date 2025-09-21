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
import type { OptionComboGroupRow, OptionComboLegRow, OptionComboRow } from "../lib/types";
import { fmtPrice, fmtSide } from "../lib/labels";
import { MarkBadge } from "./MarkBadge";
import { deriveStalenessSeconds, formatSigned, stalenessTone, valueTone } from "./tableUtils";

const COLUMN_COUNT = 8;
const SKELETON_ROWS = Array.from({ length: 6 }, (_, idx) => idx);
const SHOULD_POLL = import.meta.env.MODE !== "test";
const QTY_TOOLTIP = "+ = long (debit), − = short (credit); magnitude = contracts";

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
              Leg
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
                <span title={leg.labelTooltip ?? leg.symbol}>{leg.label}</span>
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

type GroupDetailProps = {
  group: OptionComboGroupRow;
  combos: OptionComboRow[];
};

function GroupDetail({ group, combos }: GroupDetailProps) {
  return (
    <div className="space-y-4">
      <div>
        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Combos</h4>
        <ul className="mt-2 space-y-2 text-sm text-slate-200">
          {combos.map((combo) => (
            <li key={combo.id} className="rounded-lg border border-slate-900/60 bg-slate-950/40 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="font-semibold text-slate-100" title={combo.id}>
                  {combo.label}
                </div>
                <div className="text-xs uppercase tracking-wide text-slate-400">
                  {fmtSide(combo.netPremium)} {fmtPrice(combo.netPremium)} • Qty {combo.comboQty}
                </div>
              </div>
              <div className="mt-2 grid grid-cols-2 gap-3 text-xs text-slate-300 sm:grid-cols-4">
                <span>Δ {formatSigned(combo.delta)}</span>
                <span>Γ {formatSigned(combo.gamma)}</span>
                <span>Θ {formatSigned(combo.theta)}</span>
                <span>ν {formatSigned(combo.vega)}</span>
              </div>
            </li>
          ))}
        </ul>
      </div>
      <div>
        <h4 className="text-xs font-semibold uppercase tracking-wide text-slate-400">Legs</h4>
        <div className="mt-2 flex flex-wrap gap-2">
          {group.legs.map((leg) => (
            <span
              key={leg.id}
              className="rounded-full border border-slate-800 bg-slate-950 px-3 py-1 text-xs text-slate-200"
              title={leg.labelTooltip ?? leg.symbol}
            >
              {leg.label}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

type TableRowData =
  | { kind: "group"; id: string; row: OptionComboGroupRow; combos: OptionComboRow[] }
  | { kind: "combo"; id: string; row: OptionComboRow };

type ComboRowProps = {
  entry: TableRowData;
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
    entry,
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
  const base = entry.kind === "group" ? entry.row : entry.row;
  const stalenessSeconds = entry.kind === "group"
    ? entry.row.staleSeconds ?? null
    : deriveStalenessSeconds(entry.row.markTime, now);
  const stalenessLabel = stalenessSeconds !== null ? formatDuration(stalenessSeconds) : "—";
  const stalenessClass = stalenessSeconds !== null ? stalenessTone(stalenessSeconds) : "text-slate-400";

  const handleKeyDown = (event: ReactKeyboardEvent<HTMLTableRowElement>) => {
    if (event.defaultPrevented) {
      return;
    }
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
      case "Enter":
      case " ":
      case "ArrowRight":
        event.preventDefault();
        onToggle(entry.id);
        break;
      case "ArrowLeft":
        if (isExpanded) {
          event.preventDefault();
          onToggle(entry.id);
        }
        break;
      default:
        break;
    }
  };

  const handleClick = (event: MouseEvent<HTMLTableRowElement>) => {
    if ((event.target as HTMLElement).closest("button")) {
      return;
    }
    onToggle(entry.id);
  };

  const quantity = entry.kind === "group" ? entry.row.groupQty : entry.row.comboQty;
  const netPrice = entry.kind === "group" ? entry.row.netPrice : entry.row.netPremium;
  const quantityNumber = Number(quantity);
  const hasQuantity = Number.isFinite(quantityNumber);
  const quantityRounded = hasQuantity
    ? (Number.isInteger(quantityNumber) ? quantityNumber : Number(quantityNumber.toFixed(2)))
    : null;
  const quantityDisplay =
    quantityRounded === null
      ? null
      : quantityRounded > 0
        ? `+${quantityRounded}`
        : quantityRounded === 0
          ? "0"
          : String(quantityRounded);
  const netPriceNumber = Number(netPrice ?? 0);
  const hasNetPrice = Number.isFinite(netPriceNumber);
  const sideLabel = hasNetPrice && netPriceNumber !== 0
    ? netPriceNumber > 0
      ? "Credit"
      : "Debit"
    : null;
  const priceText = fmtPrice(hasNetPrice ? netPriceNumber : 0);
  const greeks = entry.kind === "group"
    ? entry.row
    : entry.row;

  const markPrice = entry.kind === "group" ? null : entry.row.markPrice;
  const markSource = entry.kind === "group" ? entry.row.markSource : entry.row.markSource;
  const rowLegs = entry.kind === "group" ? entry.row.legs : entry.row.legs;
  const labelText = entry.kind === "group" ? entry.row.label : entry.row.label;
  const tooltipSymbols = rowLegs
    .map((leg) => leg.symbol)
    .filter((symbol): symbol is string => typeof symbol === "string" && symbol.trim().length > 0);
  const labelTooltip =
    tooltipSymbols.length > 0
      ? tooltipSymbols.join(" • ")
      : entry.kind === "group"
        ? labelText
        : entry.row.id;

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
                onToggle(entry.id);
              }}
              aria-label={`${isExpanded ? "Collapse" : "Expand"} ${entry.kind === "group" ? "group" : "combo"}`}
              aria-expanded={isExpanded}
              aria-controls={`combo-legs-${entry.id}`}
            >
              {isExpanded ? "−" : "+"}
            </button>
            <div className="space-y-1">
              <span title={labelTooltip}>{labelText}</span>
              <p className="text-xs font-normal text-slate-400">
                {entry.kind === "group" ? entry.row.display?.short_ul ?? entry.row.underlying : entry.row.underlying}
              </p>
            </div>
          </div>
        </th>
        <td role="gridcell" className="px-4 py-4 text-sm text-slate-200">
          <div className="space-y-1">
            <span className="font-medium text-slate-100">
              {entry.kind === "group" ? entry.row.underlying : entry.row.underlying}
            </span>
            <span className="block text-xs text-slate-400">
              ΣΔ {formatSigned(greeks.delta)}
            </span>
          </div>
        </td>
        <td role="gridcell" className="px-4 py-4 text-sm text-slate-200">
          {entry.kind === "group" ? entry.row.dte : entry.row.dte}d
        </td>
        <td role="gridcell" className="px-4 py-4 text-sm text-slate-200">
          <div className="space-y-1">
            <span className="text-xs uppercase tracking-wide text-slate-400">{fmtSide(netPrice)}</span>
            <span className="text-sm font-semibold text-slate-100">{fmtPrice(netPrice)}</span>
          </div>
        </td>
        <td role="gridcell" className="px-4 py-4 text-sm text-slate-200">
          <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
            <span className="text-slate-400">Δ</span>
            <span className={clsx("text-right", valueTone(greeks.delta))}>
              {formatSigned(greeks.delta)}
            </span>
            <span className="text-slate-400">Γ</span>
            <span className={clsx("text-right", valueTone(greeks.gamma))}>
              {formatSigned(greeks.gamma)}
            </span>
            <span className="text-slate-400">Θ</span>
            <span className={clsx("text-right", valueTone(greeks.theta))}>
              {formatSigned(greeks.theta)}
            </span>
            <span className="text-slate-400">ν</span>
            <span className={clsx("text-right", valueTone(greeks.vega))}>
              {formatSigned(greeks.vega)}
            </span>
          </div>
        </td>
        <td role="gridcell" className="px-4 py-4 text-sm">
          {entry.kind === "group" ? (
            <span className="text-xs text-slate-400">—</span>
          ) : (
            <div className="space-y-1">
              <div className={clsx("text-sm font-semibold", valueTone(entry.row.dayPnlAmount))}>
                {formatMoney(entry.row.dayPnlAmount)}
                <span className="ml-2 text-xs text-slate-400">
                  {formatPercent(entry.row.dayPnlPercent, {
                    alreadyScaled: true,
                    signDisplay: "always",
                  })}
                </span>
              </div>
              <div className={clsx("text-xs", valueTone(entry.row.totalPnlAmount))}>
                {formatMoney(entry.row.totalPnlAmount)}
                <span className="ml-2 text-[0.7rem] text-slate-400">
                  {formatPercent(entry.row.totalPnlPercent, {
                    alreadyScaled: true,
                    signDisplay: "always",
                  })}
                </span>
              </div>
            </div>
          )}
        </td>
        <td role="gridcell" className="px-4 py-4 text-sm">
          {entry.kind === "group" ? (
            <span className="text-xs text-slate-400">—</span>
          ) : (
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-slate-100">
                {formatMoney(markPrice)}
              </span>
              <MarkBadge source={markSource} />
            </div>
          )}
        </td>
        <td role="gridcell" className={clsx("px-4 py-4 text-sm", stalenessClass)}>
          {stalenessLabel}
        </td>
      </tr>
      {isExpanded ? (
        <tr
          role="row"
          aria-label="combo detail row"
          id={`combo-legs-${entry.id}`}
          className="border-b border-slate-900/70 bg-slate-950/40"
        >
          <td role="gridcell" colSpan={COLUMN_COUNT} className="px-6 pb-6 pt-2">
            {entry.kind === "group" ? (
              <GroupDetail group={entry.row} combos={entry.combos} />
            ) : (
              <ComboLegsDetail legs={entry.row.legs} />
            )}
          </td>
        </tr>
      ) : null}
    </Fragment>
  );
};

const ForwardedComboRow = forwardRef<HTMLTableRowElement, ComboRowProps>(ComboRow);

export function CombosTable(): JSX.Element {
  const {
    groups = [],
    rawCombos = [],
    groupCombos,
    isLoading,
    isFetching,
    error,
    refetch,
  } = useOptionCombos();
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [activeIndex, setActiveIndex] = useState(0);
  const [showRaw, setShowRaw] = useState(false);
  const rowRefs = useRef<Array<HTMLTableRowElement | null>>([]);

  useEffect(() => {
    if (!SHOULD_POLL) {
      return;
    }
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const rows = useMemo<TableRowData[]>(() => {
    if (showRaw) {
      return rawCombos.map((combo) => ({ kind: "combo", id: combo.id, row: combo }));
    }
    return groups.map((group) => ({
      kind: "group" as const,
      id: group.id,
      row: group,
      combos: groupCombos.get(group.id) ?? [],
    }));
  }, [showRaw, rawCombos, groups, groupCombos]);

  useEffect(() => {
    if (expandedId && !rows.some((entry) => entry.id === expandedId)) {
      setExpandedId(null);
    }
  }, [rows, expandedId]);

  useEffect(() => {
    if (rows.length === 0) {
      return;
    }
    if (activeIndex >= rows.length) {
      setActiveIndex(0);
    }
  }, [rows, activeIndex]);

  useEffect(() => {
    rowRefs.current = rowRefs.current.slice(0, rows.length);
  }, [rows.length]);

  const setFocusByIndex = (targetIndex: number) => {
    if (rows.length === 0) {
      return;
    }
    const constrained = Math.min(Math.max(targetIndex, 0), rows.length - 1);
    setActiveIndex(constrained);
    const row = rowRefs.current[constrained];
    if (row) {
      window.requestAnimationFrame(() => row.focus());
    }
  };

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

  const gridRowCount = rows.length ? rows.length + 1 + (expandedId ? 1 : 0) : 1;

  return (
    <div className="rounded-3xl border border-slate-900/60 bg-slate-950/40 backdrop-blur">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-900/60 px-6 py-4">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">Options Combos</h2>
          <p className="text-xs text-slate-400">
            Aggregated strategies with keyboard navigation.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <label className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
            <input
              type="checkbox"
              checked={showRaw}
              onChange={(event) => setShowRaw(event.target.checked)}
              className="h-4 w-4 rounded border-slate-700 bg-slate-900 text-sky-500 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
            />
            Show raw combos
          </label>
          <button
            type="button"
            onClick={() => refetch()}
            className="rounded-full border border-slate-800 bg-slate-900 px-3 py-1.5 text-xs font-semibold uppercase tracking-wide text-slate-300 hover:bg-slate-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500"
          >
            Refresh
          </button>
        </div>
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
                Label
              </th>
              <th scope="col" role="columnheader" className="px-4 py-3 text-left">
                Underlying
              </th>
              <th scope="col" role="columnheader" className="px-4 py-3 text-left">
                DTE
              </th>
              <th scope="col" role="columnheader" className="px-4 py-3 text-left">
                Credit/Debit
              </th>
              <th scope="col" role="columnheader" className="px-4 py-3 text-left">
                ΣΔ/Γ/Θ/ν
              </th>
              <th scope="col" role="columnheader" className="px-4 py-3 text-left">
                P&amp;L
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
              {rows.map((entry, index) => (
                <ForwardedComboRow
                  key={entry.id}
                  ref={(node) => {
                    rowRefs.current[index] = node;
                  }}
                  entry={entry}
                  isExpanded={expandedId === entry.id}
                  isActive={index === activeIndex}
                  onToggle={(id) =>
                    setExpandedId((current) => (current === id ? null : id))
                  }
                  onFocusRow={setActiveIndex}
                  onRequestFocus={setFocusByIndex}
                  rowIndex={index}
                  rowCount={rows.length}
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
