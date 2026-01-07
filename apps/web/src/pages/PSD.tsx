import { useEffect, useMemo, useState } from "react";
import clsx from "clsx";

import CombosTable from "../components/CombosTable";
import MSBActionBox from "../components/MSBActionBox";
import MSBCard from "../components/MSBCard";
import MSBMiniCharts from "../components/MSBMiniCharts";
import OptionLegsTable from "../components/OptionLegsTable";
import PowerlawPanel from "../components/PowerlawPanel";
import { PsdShell } from "../components/psd/PsdShell";
import {
  PsdStocksGrid,
  mapLegsToStockRows,
  GridParityHarness,
  PsdStocksFilterBar,
} from "../components/psd/data-grid";
import RulesPanel from "../components/RulesPanel";
import StatsRibbon from "../components/StatsRibbon";
import StocksTable from "../components/StocksTable";
import { getPsdGridMode } from "../hooks/getPsdGridMode";
import { usePsdSnapshot } from "../hooks/usePsdSnapshot";
import { formatDuration, formatMoney } from "../lib/format";
import { buildFriendlyLegDisplay } from "../lib/labels";
import type { PSDLeg, PSDPositionsView } from "../lib/types";
import { formatSigned, valueTone } from "../components/tableUtils";
import { usePsdStocksFilterStore } from "../state/psdStocksFilters";
import { matchesNumberFilter, matchesStringFilter, type PsdNumberFilterValue } from "../components/psd/data-grid/filters";

const stockColumns = [
  { key: "symbol", label: "Symbol", align: "left" },
  { key: "qty", label: "Qty", align: "right" },
  { key: "mark", label: "Mark", align: "right" },
  { key: "dayPnl", label: "Day P&L", align: "right" },
  { key: "totalPnl", label: "Total P&L", align: "right" },
  { key: "exposure", label: "Exposure", align: "right" },
  { key: "source", label: "Source", align: "left" },
  { key: "staleness", label: "Staleness", align: "right" },
] as const;

const optionColumns = [
  { key: "symbol", label: "Symbol", align: "left" },
  { key: "qty", label: "Qty", align: "right" },
  { key: "mark", label: "Mark", align: "right" },
  { key: "dayPnl", label: "Day P&L", align: "right" },
  { key: "delta", label: "Δ", align: "right" },
  { key: "gamma", label: "Γ", align: "right" },
  { key: "theta", label: "Θ", align: "right" },
  { key: "source", label: "Source", align: "left" },
  { key: "staleness", label: "Staleness", align: "right" },
] as const;

type StockColumnKey = (typeof stockColumns)[number]["key"];
type OptionColumnKey = (typeof optionColumns)[number]["key"];
type ColumnAlignment = "left" | "right";

const alignmentClass = (key: string) =>
  key === "symbol" || key === "source" ? "text-left" : "text-right";

const finiteOrNull = (value: number | undefined | null): number | null =>
  typeof value === "number" && Number.isFinite(value) ? value : null;

const formatMoneyMaybe = (value: number | undefined | null) => formatMoney(finiteOrNull(value));

const formatGreek = (value: number | undefined | null) => formatSigned(finiteOrNull(value), 2);

const formatQty = (value: number): string => {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return "—";
  }
  return formatSigned(parsed, 0);
};

const formatStaleness = (seconds: number | undefined | null) =>
  formatDuration(finiteOrNull(typeof seconds === "number" ? seconds : null));

function LegRow({ leg, tabIndex = -1, className = "", underlyingHint }: { leg: PSDLeg; tabIndex?: number; className?: string; underlyingHint?: string }) {
  const greeks = leg.greeks ?? {};
  const dayPnlValue = finiteOrNull(leg.pnl_intraday);
  const totalPnlValue = finiteOrNull(leg.pnl_unrealized ?? leg.total_pnl ?? null);
  const isOptionLeg = leg.secType === "OPT" || leg.secType === "FOP";
  const isStock = leg.secType === "STK";
  const exposure = leg.mark != null ? leg.mark * Math.abs(leg.qty) : null;
  const friendlyDisplay = isOptionLeg
    ? buildFriendlyLegDisplay({
      symbol: leg.symbol,
      underlying: underlyingHint,
      right: leg.right,
      strike: leg.strike,
      expiry: leg.expiry,
    })
    : null;
  const labelText = friendlyDisplay?.label ?? leg.symbol;
  const labelTooltip = friendlyDisplay?.tooltip ?? leg.symbol;

  return (
    <tr
      tabIndex={tabIndex}
      className={clsx("border-b border-slate-800/60 last:border-0 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/60", className)}
    >
      <th
        scope="row"
        className={clsx("px-4 py-3 font-semibold text-slate-100", alignmentClass("symbol"))}
      >
        <span title={labelTooltip}>{labelText}</span>
      </th>
      <td className={clsx("px-4 py-3 font-mono text-sm text-slate-300", alignmentClass("qty"))}>{formatQty(leg.qty)}</td>
      <td className={clsx("px-4 py-3 font-mono text-sm text-slate-200", alignmentClass("mark"))}>{formatMoneyMaybe(leg.mark)}</td>
      <td
        className={clsx(
          "px-4 py-3 font-mono text-sm",
          alignmentClass("dayPnl"),
          valueTone(dayPnlValue),
        )}
      >
        {formatMoneyMaybe(leg.pnl_intraday)}
      </td>
      {isStock ? (
        <>
          <td
            className={clsx(
              "px-4 py-3 font-mono text-sm",
              alignmentClass("totalPnl"),
              valueTone(totalPnlValue),
            )}
          >
            {formatMoneyMaybe(totalPnlValue)}
          </td>
          <td className={clsx("px-4 py-3 font-mono text-sm text-slate-300", alignmentClass("exposure"))}>{formatMoneyMaybe(exposure)}</td>
        </>
      ) : (
        <>
          <td className={clsx("px-4 py-3 font-mono text-xs text-slate-300", "text-right")}>{formatGreek(greeks.delta)}</td>
          <td className={clsx("px-4 py-3 font-mono text-xs text-slate-300", "text-right")}>{formatGreek(greeks.gamma)}</td>
          <td className={clsx("px-4 py-3 font-mono text-xs text-slate-300", "text-right")}>{formatGreek(greeks.theta)}</td>
        </>
      )}
      <td
        className={clsx(
          "px-4 py-3 text-xs uppercase tracking-wide text-slate-400",
          alignmentClass("source"),
        )}
      >
        {leg.price_source ? leg.price_source.toUpperCase() : "—"}
      </td>
      <td className={clsx("px-4 py-3 text-xs text-slate-400", alignmentClass("staleness"))}>
        {formatStaleness(leg.stale_s)}
      </td>
    </tr>
  );
}

function CombosSection({ view }: { view: PSDPositionsView }) {
  const combos = view.option_combos ?? [];
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    setExpanded((prev) => {
      const next = new Set<string>();
      for (const combo of combos) {
        if (prev.has(combo.combo_id)) {
          next.add(combo.combo_id);
        }
      }
      return next;
    });
  }, [combos]);

  const toggle = (comboId: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(comboId)) {
        next.delete(comboId);
      } else {
        next.add(comboId);
      }
      return next;
    });
  };

  if (combos.length === 0) {
    return <p className="mt-3 text-sm text-slate-400">No option combos detected.</p>;
  }

  return (
    <div className="mt-3 space-y-3">
      {combos.map((combo) => {
        const greeks = combo.greeks_agg ?? {};
        const pnlValue = finiteOrNull(combo.pnl_intraday);
        const isExpanded = expanded.has(combo.combo_id);
        return (
          <div
            key={combo.combo_id}
            className="rounded-2xl border border-slate-900/60 bg-slate-950/50"
          >
            <button
              type="button"
              className="flex w-full flex-col items-stretch gap-3 px-4 py-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/60"
              onClick={() => toggle(combo.combo_id)}
              aria-expanded={isExpanded}
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <span className="text-sm font-semibold text-slate-100">{combo.name}</span>
                  {combo.underlier ? (
                    <span className="ml-3 text-xs uppercase tracking-wide text-slate-400">{combo.underlier}</span>
                  ) : null}
                </div>
                <span className={clsx("font-mono text-lg", valueTone(pnlValue))}>{formatMoneyMaybe(combo.pnl_intraday)}</span>
              </div>
              <div className="flex flex-wrap gap-4 text-xs text-slate-400">
                <span>Δ {formatGreek(greeks.delta)}</span>
                <span>Γ {formatGreek(greeks.gamma)}</span>
                <span>Θ {formatGreek(greeks.theta)}</span>
                <span className="ml-auto text-xs uppercase tracking-wide text-slate-500">
                  {isExpanded ? "Hide legs" : "Show legs"}
                </span>
              </div>
            </button>
            {isExpanded ? (
              <div className="border-t border-slate-900/70 bg-slate-950/60">
                <table className="min-w-full" role="grid" aria-label={`${combo.name} legs`}>
                  <thead>
                    <tr className="text-xs uppercase tracking-wide text-slate-400">
                      {optionColumns.map(({ key, label }) => (
                        <th
                          key={`${combo.combo_id}-${key}`}
                          scope="col"
                          className={clsx("px-4 py-2", alignmentClass(key))}
                        >
                          {label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {combo.legs.map((leg, index) => (
                      <LegRow
                        key={`${combo.combo_id}-${leg.conId ?? leg.symbol}-${index}`}
                        leg={leg}
                        className="bg-slate-950/40"
                        tabIndex={index === 0 ? 0 : -1}
                        underlyingHint={combo.underlier}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

/**
 * Stocks section with feature-flagged grid rendering.
 * Supports: old (LegsTable), new (PsdStocksGrid), parity (side-by-side comparison)
 */
function StocksSectionWithGrid({
  positionsView,
  isDataStable,
}: {
  positionsView: PSDPositionsView | undefined;
  isDataStable: boolean;
}) {
  const gridMode = getPsdGridMode();
  const legs = positionsView?.single_stocks ?? [];
  const stockRows = useMemo(() => mapLegsToStockRows(legs), [legs]);
  const columnFilters = usePsdStocksFilterStore((state) => state.columnFilters);
  const setColumnFilters = usePsdStocksFilterStore((state) => state.setColumnFilters);
  const resetFilters = usePsdStocksFilterStore((state) => state.resetFilters);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const params = new URLSearchParams(window.location.search);
    if (params.get("filters") !== "reset") {
      return;
    }
    resetFilters();
    params.delete("filters");
    const next = params.toString();
    const nextUrl = `${window.location.pathname}${next ? `?${next}` : ""}${window.location.hash}`;
    window.history.replaceState({}, "", nextUrl);
  }, [resetFilters]);

  const filteredStockRows = useMemo(() => {
    if (columnFilters.length === 0) {
      return stockRows;
    }
    return stockRows.filter((row) =>
      columnFilters.every((filter) => {
        if (filter.id === "symbol") {
          return matchesStringFilter(row.symbol, filter.value as string | null | undefined);
        }
        if (filter.id === "quantity") {
          return matchesNumberFilter(
            row.quantity,
            filter.value as PsdNumberFilterValue | null | undefined,
          );
        }
        if (filter.id === "markPrice") {
          return matchesNumberFilter(
            row.markPrice,
            filter.value as PsdNumberFilterValue | null | undefined,
          );
        }
        if (filter.id === "dayPnlAmount") {
          return matchesNumberFilter(
            row.dayPnlAmount,
            filter.value as PsdNumberFilterValue | null | undefined,
          );
        }
        if (filter.id === "totalPnlAmount") {
          return matchesNumberFilter(
            row.totalPnlAmount,
            filter.value as PsdNumberFilterValue | null | undefined,
          );
        }
        return true;
      }),
    );
  }, [stockRows, columnFilters]);

  const filteredLegs = useMemo(() => {
    if (columnFilters.length === 0) {
      return legs;
    }
    const allowedIds = new Set(filteredStockRows.map((row) => row.id));
    return legs.filter((leg) => allowedIds.has(`stock:${leg.conId ?? leg.symbol}`));
  }, [legs, filteredStockRows, columnFilters]);

  const renderOldGrid = () => (
    <LegsTable label="Single Stocks (Old)" legs={filteredLegs} />
  );

  const renderNewGrid = () => (
    <PsdStocksGrid
      data={stockRows}
      height="350px"
      columnFilters={columnFilters}
      onColumnFiltersChange={setColumnFilters}
      isDataStable={isDataStable}
    />
  );

  return (
    <section
      aria-label="Single Stocks"
      className="rounded-3xl border border-slate-900/60 bg-slate-950/50 p-5"
    >
      <h2 className="text-xl font-semibold text-slate-100">Single Stocks</h2>
      <div className="mt-3">
        <PsdStocksFilterBar
          columnFilters={columnFilters}
          onColumnFiltersChange={setColumnFilters}
          onReset={resetFilters}
        />
      </div>
      <div className="mt-4">
        {gridMode === "parity" ? (
          <GridParityHarness
            legs={filteredLegs}
            stockRows={filteredStockRows}
            renderOld={() => renderOldGrid()}
            renderNew={() => renderNewGrid()}
          />
        ) : gridMode === "new" ? (
          renderNewGrid()
        ) : (
          <LegsTable label="Single Stocks" legs={filteredLegs} />
        )}
      </div>
    </section>
  );
}

function LegsTable({ label, legs, type = "stock" }: { label: string; legs: PSDLeg[]; type?: "stock" | "option" }) {
  if (legs.length === 0) {
    return <p className="mt-3 text-sm text-slate-400">No positions available.</p>;
  }
  const columnsToUse = type === "option" ? optionColumns : stockColumns;
  return (
    <div className="mt-4 overflow-x-auto">
      <table className="min-w-full" role="grid" aria-label={label}>
        <thead>
          <tr className="text-xs uppercase tracking-wide text-slate-400">
            {columnsToUse.map(({ key, label: colLabel }) => (
              <th key={`${label}-${key}`} scope="col" className={clsx("px-4 py-2", alignmentClass(key))}>
                {colLabel}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {legs.map((leg, index) => (
            <LegRow
              key={`${label}-${leg.conId ?? leg.symbol}-${index}`}
              leg={leg}
              tabIndex={index === 0 ? 0 : -1}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

const PSDPage = () => {
  const { data: snapshot, isFetching, refetch } = usePsdSnapshot();
  const positionsView = snapshot?.positions_view;
  const hasView = useMemo(() => {
    if (!positionsView) {
      return false;
    }
    return (
      Array.isArray(positionsView.single_stocks) ||
      Array.isArray(positionsView.option_combos) ||
      Array.isArray(positionsView.single_options)
    );
  }, [positionsView]);

  return (
    <PsdShell>
      <div className="mx-auto max-w-[1400px] space-y-10 px-6 py-8" aria-label="Portfolio Sentinel sections">
        <StatsRibbon />
        <PowerlawPanel
          powerlaw={snapshot?.powerlaw}
          onRefresh={() => refetch()}
        />
        <section
          aria-label="Market Stress Barometer overview"
          className="grid gap-6 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]"
        >
          <div className="space-y-6">
            <MSBCard />
            <MSBMiniCharts />
          </div>
          <MSBActionBox />
        </section>

        {hasView ? (
          <>
            <StocksSectionWithGrid
              positionsView={positionsView}
              isDataStable={!isFetching}
            />

            <section aria-label="Options — Combos" className="rounded-3xl border border-slate-900/60 bg-slate-950/50 p-5">
              <h2 className="text-xl font-semibold text-slate-100">Options — Combos</h2>
              <CombosSection view={positionsView as PSDPositionsView} />
            </section>

            <section aria-label="Options — Singles" className="rounded-3xl border border-slate-900/60 bg-slate-950/50 p-5">
              <h2 className="text-xl font-semibold text-slate-100">Options — Singles</h2>
              <LegsTable label="Options — Singles" legs={positionsView?.single_options ?? []} type="option" />
            </section>
          </>
        ) : (
          <>
            <section aria-label="Single Stocks" className="rounded-3xl border border-slate-900/60 bg-slate-950/50 p-5">
              <h2 className="text-xl font-semibold text-slate-100">Single Stocks</h2>
              <p className="mt-1 text-sm text-slate-400">Ranked by intraday P&amp;L with mark source and staleness badges.</p>
              <div className="mt-4">
                <StocksTable />
              </div>
            </section>

            <section aria-label="Options" className="space-y-6 rounded-3xl border border-slate-900/60 bg-slate-950/50 p-5">
              <h2 className="text-xl font-semibold text-slate-100">Options</h2>
              <div>
                <h3 className="text-base font-medium text-slate-200">Combos</h3>
                <p className="mt-1 text-sm text-slate-400">Strategy view with aggregates, greeks, and mark provenance.</p>
                <div className="mt-3">
                  <CombosTable />
                </div>
              </div>
              <div>
                <h3 className="text-base font-medium text-slate-200">Single Option Legs</h3>
                <p className="mt-1 text-sm text-slate-400">Focus on orphan legs and combo components with theta coverage.</p>
                <div className="mt-3">
                  <OptionLegsTable />
                </div>
              </div>
            </section>
          </>
        )}

        <section aria-label="Rules & Fundamentals" className="rounded-3xl border border-slate-900/60 bg-slate-950/50 p-5">
          <h2 className="text-xl font-semibold text-slate-100">Rules & Fundamentals</h2>
          <p className="mt-1 text-sm text-slate-400">Breach triage, catalog actions, and fundamentals snapshots.</p>
          <div className="mt-4">
            <RulesPanel />
          </div>
        </section>
      </div>
    </PsdShell>
  );
};

export default PSDPage;
