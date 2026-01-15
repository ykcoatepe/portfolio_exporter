import { useEffect, useMemo, useRef, useState } from "react";
import clsx from "clsx";

import CombosTable from "../components/CombosTable";
import MSBActionBox from "../components/MSBActionBox";
import MSBCard from "../components/MSBCard";
import MSBMiniCharts from "../components/MSBMiniCharts";
import OptionLegsTable from "../components/OptionLegsTable";
import PowerlawPanel, { triggerPowerlawRefresh } from "../components/PowerlawPanel";
import { PsdShell } from "../components/psd/PsdShell";
import {
  PsdStocksGrid,
  mapLegsToStockRows,
  mapLegsToOptionLegRows,
  PsdOptionLegsGrid,
  PsdStocksFilterBar,
} from "../components/psd/data-grid";
import RulesPanel from "../components/RulesPanel";
import StatsRibbon from "../components/StatsRibbon";
import StocksTable from "../components/StocksTable";
import { usePsdSnapshot } from "../hooks/usePsdSnapshot";
import { formatDuration, formatMoney } from "../lib/format";
import { buildFriendlyLegDisplay } from "../lib/labels";
import type { PSDLeg, PSDPositionsView } from "../lib/types";
import { formatSigned, valueTone } from "../components/tableUtils";
import { usePsdStocksFilterStore } from "../state/psdStocksFilters";
import { usePsdStocksSorting, setPsdStocksSorting } from "../state/psdStocksSorting";
import { usePsdUiState } from "../state/psdUiState";

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

const EMPTY_PSD_LEGS: PSDLeg[] = [];

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
  const { expandedCombos, toggleCombo, setExpandedCombos } = usePsdUiState();

  // Prune expanded combos that no longer exist in the current view
  useEffect(() => {
    const next = new Set<string>();
    for (const combo of combos) {
      if (expandedCombos.has(combo.combo_id)) {
        next.add(combo.combo_id);
      }
    }
    if (next.size !== expandedCombos.size) {
      setExpandedCombos(next);
    }
  }, [combos, expandedCombos, setExpandedCombos]);

  if (combos.length === 0) {
    return <p className="mt-3 text-sm text-slate-400">No option combos detected.</p>;
  }

  return (
    <div className="mt-3 space-y-3">
      {combos.map((combo) => {
        const greeks = combo.greeks_agg ?? {};
        const pnlValue = finiteOrNull(combo.pnl_intraday);
        const isExpanded = expandedCombos.has(combo.combo_id);
        return (
          <div
            key={combo.combo_id}
            className="rounded-2xl border border-slate-900/60 bg-slate-950/50"
          >
            <button
              type="button"
              className="flex w-full flex-col items-stretch gap-3 px-4 py-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/60"
              onClick={() => toggleCombo(combo.combo_id)}
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
 * Stocks section using the PSD data grid with filters and sorting.
 */
function StocksSectionWithGrid({
  positionsView,
  isDataStable,
}: {
  positionsView: PSDPositionsView | undefined;
  isDataStable: boolean;
}) {
  const legs = positionsView?.single_stocks ?? EMPTY_PSD_LEGS;
  const stockRows = useMemo(() => mapLegsToStockRows(legs), [legs]);
  const columnFilters = usePsdStocksFilterStore((state) => state.columnFilters);
  const setColumnFilters = usePsdStocksFilterStore((state) => state.setColumnFilters);
  const resetFilters = usePsdStocksFilterStore((state) => state.resetFilters);
  const sorting = usePsdStocksSorting();

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

  const { stocksGridSelection, setStocksGridSelection } = usePsdUiState();

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
        <PsdStocksGrid
          data={stockRows}
          height="350px"
          columnFilters={columnFilters}
          onColumnFiltersChange={setColumnFilters}
          sorting={sorting}
          onSortingChange={setPsdStocksSorting}
          isDataStable={isDataStable}
          selectedRowIds={stocksGridSelection}
          onSelectedRowIdsChange={setStocksGridSelection}
        />
      </div>
    </section>
  );
}

const PSDPage = () => {
  const { data: snapshot, isFetching, refetch } = usePsdSnapshot();
  const [refreshing, setRefreshing] = useState(false);
  const refreshStatus: "idle" | "running" | "success" | "failed" | "timeout" =
    (snapshot?.powerlaw?.refresh?.status as "idle" | "running" | "success" | "failed" | "timeout" | undefined) ?? "idle";
  const positionsView = snapshot?.positions_view;
  const optionLegs = positionsView?.single_options ?? EMPTY_PSD_LEGS;
  const optionLegRows = useMemo(() => mapLegsToOptionLegRows(optionLegs), [optionLegs]);
  const missingGreeksCount = useMemo(
    () =>
      optionLegRows.reduce(
        (count, row) =>
          row.delta == null || row.gamma == null || row.theta == null ? count + 1 : count,
        0,
      ),
    [optionLegRows],
  );
  const comboMissingGreeksCount = useMemo(() => {
    const combos = positionsView?.option_combos ?? [];
    return combos.reduce((count, combo) => {
      const hasMissingGreeks = (combo.legs ?? []).some((leg) => {
        if (leg.secType !== "OPT" && leg.secType !== "FOP") {
          return false;
        }
        const greeks = leg.greeks ?? {};
        return (
          finiteOrNull(greeks.delta) === null ||
          finiteOrNull(greeks.gamma) === null ||
          finiteOrNull(greeks.theta) === null
        );
      });
      return hasMissingGreeks ? count + 1 : count;
    }, 0);
  }, [positionsView]);
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

  // Track previous refresh status to detect completion
  const prevRefreshStatusRef = useRef(refreshStatus);

  // Poll more frequently while refresh is running
  useEffect(() => {
    const prevStatus = prevRefreshStatusRef.current;
    prevRefreshStatusRef.current = refreshStatus;

    // Refresh just completed - do a final refetch to get fresh data
    if (prevStatus === "running" && refreshStatus !== "running") {
      setRefreshing(false);
      refetch();
      return;
    }

    // Not running - nothing to poll
    if (refreshStatus !== "running") {
      return;
    }

    // Currently running - poll every 2 seconds
    const interval = setInterval(() => {
      refetch();
    }, 2000);
    return () => clearInterval(interval);
  }, [refreshStatus, refetch]);

  const handleMasterRefresh = async () => {
    if (refreshing || refreshStatus === "running") return;
    setRefreshing(true);
    let nextStatus: string | null = null;
    try {
      await triggerPowerlawRefresh();
    } catch {
      // Ignore trigger errors; we'll refetch to see the latest status.
    }
    try {
      const result = await refetch();
      nextStatus = result.data?.powerlaw?.refresh?.status ?? null;
    } catch {
      nextStatus = null;
    }
    if (nextStatus !== "running") {
      setRefreshing(false);
    }
    // If the backend reports running, let the useEffect handle completion.
  };

  return (
    <PsdShell>
      <div className="mx-auto max-w-[1400px] space-y-10 px-6 py-8" aria-label="Portfolio Sentinel sections">
        <StatsRibbon onRefresh={handleMasterRefresh} refreshing={refreshing} refreshStatus={refreshStatus} />
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
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-xl font-semibold text-slate-100">Options — Combos</h2>
                {comboMissingGreeksCount > 0 ? (
                  <span
                    data-testid="combo-greeks-missing-chip"
                    className="rounded-full border border-amber-400/40 bg-amber-500/10 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-amber-200"
                    title={`Missing delta/gamma/theta for ${comboMissingGreeksCount} combo${comboMissingGreeksCount === 1 ? "" : "s"}`}
                  >
                    Greeks missing • {comboMissingGreeksCount}
                  </span>
                ) : null}
              </div>
              <CombosSection view={positionsView as PSDPositionsView} />
            </section>

            <section aria-label="Options — Singles" className="rounded-3xl border border-slate-900/60 bg-slate-950/50 p-5">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-xl font-semibold text-slate-100">Options — Singles</h2>
                {missingGreeksCount > 0 ? (
                  <span
                    data-testid="greeks-missing-chip"
                    className="rounded-full border border-amber-400/40 bg-amber-500/10 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-amber-200"
                    title={`Missing delta/gamma/theta for ${missingGreeksCount} leg${missingGreeksCount === 1 ? "" : "s"}`}
                  >
                    Greeks missing • {missingGreeksCount}
                  </span>
                ) : null}
              </div>
              <PsdOptionLegsGrid
                data={optionLegRows}
                height="350px"
                isDataStable={!isFetching}
              />
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
