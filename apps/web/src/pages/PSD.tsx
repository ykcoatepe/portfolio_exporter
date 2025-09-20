import { useEffect, useMemo, useState } from "react";
import clsx from "clsx";

import CombosTable from "../components/CombosTable";
import OptionLegsTable from "../components/OptionLegsTable";
import RulesPanel from "../components/RulesPanel";
import StatsRibbon from "../components/StatsRibbon";
import StocksTable from "../components/StocksTable";
import { usePsdSnapshot } from "../hooks/usePsdSnapshot";
import { formatDuration, formatMoney } from "../lib/format";
import type { PSDLeg, PSDPositionsView } from "../lib/types";
import { formatSigned, valueTone } from "../components/tableUtils";

const columns = [
  "Symbol",
  "Qty",
  "Mark",
  "P&L",
  "Δ",
  "Γ",
  "Θ",
  "Source",
  "Staleness",
];

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

function LegRow({ leg, tabIndex = -1, className = "" }: { leg: PSDLeg; tabIndex?: number; className?: string }) {
  const greeks = leg.greeks ?? {};
  const pnlValue = finiteOrNull(leg.pnl_intraday);
  return (
    <tr
      tabIndex={tabIndex}
      className={clsx("border-b border-slate-800/60 last:border-0 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/60", className)}
    >
      <th scope="row" className="px-4 py-3 text-left font-semibold text-slate-100">
        {leg.symbol}
      </th>
      <td className="px-4 py-3 text-right font-mono text-sm text-slate-300">{formatQty(leg.qty)}</td>
      <td className="px-4 py-3 text-right font-mono text-sm text-slate-200">{formatMoneyMaybe(leg.mark)}</td>
      <td className={clsx("px-4 py-3 text-right font-mono text-sm", valueTone(pnlValue))}>{formatMoneyMaybe(leg.pnl_intraday)}</td>
      <td className="px-4 py-3 text-right font-mono text-xs text-slate-300">{formatGreek(greeks.delta)}</td>
      <td className="px-4 py-3 text-right font-mono text-xs text-slate-300">{formatGreek(greeks.gamma)}</td>
      <td className="px-4 py-3 text-right font-mono text-xs text-slate-300">{formatGreek(greeks.theta)}</td>
      <td className="px-4 py-3 text-right text-xs uppercase tracking-wide text-slate-400">
        {leg.price_source ? leg.price_source.toUpperCase() : "—"}
      </td>
      <td className="px-4 py-3 text-right text-xs text-slate-400">{formatStaleness(leg.stale_s)}</td>
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
                      {columns.map((col) => (
                        <th key={`${combo.combo_id}-${col}`} scope="col" className="px-4 py-2 text-left">
                          {col}
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

function LegsTable({ label, legs }: { label: string; legs: PSDLeg[] }) {
  if (legs.length === 0) {
    return <p className="mt-3 text-sm text-slate-400">No positions available.</p>;
  }
  return (
    <div className="mt-4 overflow-x-auto">
      <table className="min-w-full" role="grid" aria-label={label}>
        <thead>
          <tr className="text-xs uppercase tracking-wide text-slate-400">
            {columns.map((col) => (
              <th key={`${label}-${col}`} scope="col" className="px-4 py-2 text-left">
                {col}
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
  const { data: snapshot } = usePsdSnapshot();
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
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-900/70 bg-slate-950/80">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-4 px-6 py-6">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Portfolio Sentinel Dashboard</h1>
            <p className="mt-1 text-sm text-slate-400">Keyboard-first monitoring for equities and derivatives portfolios.</p>
          </div>
          <div className="rounded-full border border-slate-800 bg-slate-900/80 px-4 py-2 text-xs uppercase tracking-wide text-slate-400">
            PSD • Preview
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[1400px] space-y-10 px-6 py-8" aria-label="Portfolio Sentinel sections">
        <StatsRibbon />

        {hasView ? (
          <>
            <section aria-label="Single Stocks" className="rounded-3xl border border-slate-900/60 bg-slate-950/50 p-5">
              <h2 className="text-xl font-semibold text-slate-100">Single Stocks</h2>
              <LegsTable label="Single Stocks" legs={positionsView?.single_stocks ?? []} />
            </section>

            <section aria-label="Options — Combos" className="rounded-3xl border border-slate-900/60 bg-slate-950/50 p-5">
              <h2 className="text-xl font-semibold text-slate-100">Options — Combos</h2>
              <CombosSection view={positionsView as PSDPositionsView} />
            </section>

            <section aria-label="Options — Singles" className="rounded-3xl border border-slate-900/60 bg-slate-950/50 p-5">
              <h2 className="text-xl font-semibold text-slate-100">Options — Singles</h2>
              <LegsTable label="Options — Singles" legs={positionsView?.single_options ?? []} />
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
      </main>
    </div>
  );
};

export default PSDPage;
