import { useMemo } from "react";

import type {
  PSDCombo,
  PSDGreeks,
  PSDLeg,
  PSDPositionsView,
  PSDSnapshot,
} from "../lib/types";
import { usePsdSnapshot } from "./usePsdSnapshot";

export type PortfolioMetrics = {
  dayPnl: number | null;
  totalPnl: number | null;
  sumDelta: number | null;
  sumTheta: number | null;
  updatedAt: number | null;
  stalenessSeconds: number | null;
  session: PSDSnapshot["session"] | null;
};

function toFiniteNumber(value: unknown): number | null {
  if (typeof value !== "number") {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) {
      return null;
    }
    return parsed;
  }
  return Number.isFinite(value) ? value : null;
}

function sumGreek(greeks: PSDGreeks | undefined, key: keyof PSDGreeks): number | null {
  if (!greeks) {
    return null;
  }
  return toFiniteNumber(greeks[key]);
}

function computeLegUnrealized(leg: PSDLeg): number | null {
  const mark = toFiniteNumber(leg.mark);
  const avgCost = toFiniteNumber(leg.avg_cost);
  const qty = toFiniteNumber(leg.qty);
  const rawMultiplier = toFiniteNumber(leg.multiplier);
  if (mark === null || avgCost === null || qty === null) {
    return null;
  }
  const multiplier = rawMultiplier ?? (leg.secType === "OPT" || leg.secType === "FOP" ? 100 : 1);
  if (!Number.isFinite(multiplier)) {
    return null;
  }
  return (mark - avgCost) * qty * multiplier;
}

function collectLegs(view: PSDPositionsView | undefined): PSDLeg[] {
  if (!view) {
    return [];
  }
  const stocks = Array.isArray(view.single_stocks) ? view.single_stocks : [];
  const singles = Array.isArray(view.single_options) ? view.single_options : [];
  const comboLegs = Array.isArray(view.option_combos)
    ? view.option_combos.flatMap((combo) => combo.legs ?? [])
    : [];
  return [...stocks, ...comboLegs, ...singles];
}

function aggregateComboGreek(combo: PSDCombo, key: keyof PSDGreeks): number | null {
  const fromAgg = sumGreek(combo.greeks_agg, key);
  if (fromAgg !== null) {
    return fromAgg;
  }
  const legs = Array.isArray(combo.legs) ? combo.legs : [];
  let total = 0;
  let hasValue = false;
  for (const leg of legs) {
    const legValue = sumGreek(leg.greeks, key);
    if (legValue === null) {
      continue;
    }
    total += legValue;
    hasValue = true;
  }
  return hasValue ? total : null;
}

export function usePortfolioMetrics(): PortfolioMetrics {
  const { data: snapshot } = usePsdSnapshot();

  return useMemo(() => {
    const view = snapshot?.positions_view;
    const stocks = Array.isArray(view?.single_stocks) ? view!.single_stocks : [];
    const combos = Array.isArray(view?.option_combos) ? view!.option_combos : [];
    const singles = Array.isArray(view?.single_options) ? view!.single_options : [];

    let dayPnl = 0;
    let hasDayPnl = false;
    let totalPnl = 0;
    let hasTotalPnl = false;
    let sumDelta = 0;
    let hasDelta = false;
    let sumTheta = 0;
    let hasTheta = false;

    for (const stock of stocks) {
      const dayValue = toFiniteNumber(stock.pnl_intraday);
      if (dayValue !== null) {
        dayPnl += dayValue;
        hasDayPnl = true;
      }
      const totalValue = computeLegUnrealized(stock);
      if (totalValue !== null) {
        totalPnl += totalValue;
        hasTotalPnl = true;
      }
      const deltaValue = sumGreek(stock.greeks, "delta");
      if (deltaValue !== null) {
        sumDelta += deltaValue;
        hasDelta = true;
      }
      const thetaValue = sumGreek(stock.greeks, "theta");
      if (thetaValue !== null) {
        sumTheta += thetaValue;
        hasTheta = true;
      }
    }

    for (const combo of combos) {
      const dayValue = toFiniteNumber(combo.pnl_intraday);
      if (dayValue !== null) {
        dayPnl += dayValue;
        hasDayPnl = true;
      }
      const legs = Array.isArray(combo.legs) ? combo.legs : [];
      for (const leg of legs) {
        const totalValue = computeLegUnrealized(leg);
        if (totalValue !== null) {
          totalPnl += totalValue;
          hasTotalPnl = true;
        }
      }
      const deltaValue = aggregateComboGreek(combo, "delta");
      if (deltaValue !== null) {
        sumDelta += deltaValue;
        hasDelta = true;
      }
      const thetaValue = aggregateComboGreek(combo, "theta");
      if (thetaValue !== null) {
        sumTheta += thetaValue;
        hasTheta = true;
      }
    }

    for (const leg of singles) {
      const dayValue = toFiniteNumber(leg.pnl_intraday);
      if (dayValue !== null) {
        dayPnl += dayValue;
        hasDayPnl = true;
      }
      const totalValue = computeLegUnrealized(leg);
      if (totalValue !== null) {
        totalPnl += totalValue;
        hasTotalPnl = true;
      }
      const deltaValue = sumGreek(leg.greeks, "delta");
      if (deltaValue !== null) {
        sumDelta += deltaValue;
        hasDelta = true;
      }
      const thetaValue = sumGreek(leg.greeks, "theta");
      if (thetaValue !== null) {
        sumTheta += thetaValue;
        hasTheta = true;
      }
    }

    const staleSamples = collectLegs(view)
      .map((leg) => toFiniteNumber(leg.stale_s))
      .filter((value): value is number => value !== null && value >= 0);

    const stalenessSeconds = staleSamples.length > 0 ? Math.max(...staleSamples) : null;
    const updatedAt = typeof snapshot?.ts === "number" && Number.isFinite(snapshot.ts)
      ? snapshot.ts
      : null;
    const session = snapshot?.session ?? null;

    return {
      dayPnl: hasDayPnl ? dayPnl : null,
      totalPnl: hasTotalPnl ? totalPnl : null,
      sumDelta: hasDelta ? sumDelta : null,
      sumTheta: hasTheta ? sumTheta : null,
      updatedAt,
      stalenessSeconds,
      session,
    };
  }, [snapshot]);
}
