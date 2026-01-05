/**
 * Grid Parity Harness
 *
 * DEV-only side-by-side comparison of old vs new grid rendering.
 * Compares old table data (PSDLeg) against new grid data (StockRow).
 *
 * Activated via ?grid=parity (DEV mode only)
 */

import type { PSDLeg } from "../../../lib/types";
import type { StockRow } from "./mappers";
import { sumPnlCents, sumDelta } from "./mappers";

interface ParityResult {
    rowCountMatch: boolean;
    totalPnlMatch: boolean;
    totalDeltaMatch: boolean;
    oldRowCount: number;
    newRowCount: number;
    oldPnlCents: number;
    newPnlCents: number;
    oldDelta: number;
    newDelta: number;
    mismatches: ParityMismatch[];
}

interface ParityMismatch {
    rowId: string;
    field: string;
    oldValue: string;
    newValue: string;
}

interface GridParityHarnessProps {
    /** Raw PSDLeg data (old table source) */
    legs: PSDLeg[];
    /** Mapped StockRow data (new grid source) */
    stockRows: StockRow[];
    /** Render function for old grid */
    renderOld: () => JSX.Element;
    /** Render function for new grid */
    renderNew: () => JSX.Element;
}

/**
 * Sum P&L in cents from raw PSDLeg array (old table calculation)
 */
function sumLegPnlCents(legs: PSDLeg[]): number {
    return legs.reduce((sum, leg) => {
        const pnl = leg.pnl_intraday ?? 0;
        return sum + Math.round(pnl * 100);
    }, 0);
}

/**
 * Sum delta from raw PSDLeg array (old table calculation)
 */
function sumLegDelta(legs: PSDLeg[]): number {
    return legs.reduce((sum, leg) => sum + (leg.greeks?.delta ?? 0), 0);
}

/**
 * Compute parity between old (PSDLeg) and new (StockRow) data
 */
function computeParity(legs: PSDLeg[], stockRows: StockRow[]): ParityResult {
    const oldRowCount = legs.length;
    const newRowCount = stockRows.length;
    const rowCountMatch = oldRowCount === newRowCount;

    // Total P&L in cents (exact integer comparison)
    const oldPnlCents = sumLegPnlCents(legs);
    const newPnlCents = sumPnlCents(stockRows);
    const totalPnlMatch = oldPnlCents === newPnlCents;

    // Total delta
    const oldDelta = sumLegDelta(legs);
    const newDelta = sumDelta(stockRows);
    // Allow small epsilon for floating point
    const totalDeltaMatch = Math.abs(oldDelta - newDelta) < 0.0001;

    // Spot-check mismatches
    const mismatches: ParityMismatch[] = [];

    // Check row-level P&L mapping
    for (let i = 0; i < Math.min(legs.length, stockRows.length); i++) {
        const leg = legs[i];
        const row = stockRows[i];

        const legPnlCents = Math.round((leg.pnl_intraday ?? 0) * 100);
        if (legPnlCents !== row.dayPnlCents) {
            mismatches.push({
                rowId: row.id,
                field: "dayPnlCents",
                oldValue: String(legPnlCents),
                newValue: String(row.dayPnlCents),
            });
        }

        const legDelta = leg.greeks?.delta ?? null;
        if (legDelta !== row.delta) {
            mismatches.push({
                rowId: row.id,
                field: "delta",
                oldValue: String(legDelta),
                newValue: String(row.delta),
            });
        }
    }

    return {
        rowCountMatch,
        totalPnlMatch,
        totalDeltaMatch,
        oldRowCount,
        newRowCount,
        oldPnlCents,
        newPnlCents,
        oldDelta,
        newDelta,
        mismatches,
    };
}

/**
 * Format cents as dollars for display
 */
function centsToDollars(cents: number): string {
    return `$${(cents / 100).toFixed(2)}`;
}

export function GridParityHarness({
    legs,
    stockRows,
    renderOld,
    renderNew,
}: GridParityHarnessProps): JSX.Element {
    const parity = computeParity(legs, stockRows);

    const allMatch =
        parity.rowCountMatch &&
        parity.totalPnlMatch &&
        parity.totalDeltaMatch &&
        parity.mismatches.length === 0;

    return (
        <div className="space-y-4">
            {/* Parity Summary */}
            <div
                className={`rounded-lg border p-4 ${allMatch
                        ? "border-emerald-500/40 bg-emerald-500/10"
                        : "border-rose-500/40 bg-rose-500/10"
                    }`}
            >
                <h3 className="text-sm font-semibold text-slate-200 mb-2">
                    Parity Check
                    <span
                        className={`ml-2 ${allMatch ? "text-emerald-400" : "text-rose-400"
                            }`}
                    >
                        {allMatch ? "✓ PASS" : "✗ FAIL"}
                    </span>
                </h3>
                <dl className="grid grid-cols-3 gap-4 text-xs">
                    <div>
                        <dt className="text-slate-500">Row Count</dt>
                        <dd className={parity.rowCountMatch ? "text-slate-300" : "text-rose-400"}>
                            {parity.oldRowCount} → {parity.newRowCount}
                            {!parity.rowCountMatch && " ✗"}
                        </dd>
                    </div>
                    <div>
                        <dt className="text-slate-500">Total P&L</dt>
                        <dd className={parity.totalPnlMatch ? "text-slate-300" : "text-rose-400"}>
                            {centsToDollars(parity.oldPnlCents)} → {centsToDollars(parity.newPnlCents)}
                            {!parity.totalPnlMatch && " ✗"}
                        </dd>
                    </div>
                    <div>
                        <dt className="text-slate-500">Total Δ</dt>
                        <dd className={parity.totalDeltaMatch ? "text-slate-300" : "text-rose-400"}>
                            {parity.oldDelta.toFixed(2)} → {parity.newDelta.toFixed(2)}
                            {!parity.totalDeltaMatch && " ✗"}
                        </dd>
                    </div>
                </dl>

                {parity.mismatches.length > 0 && (
                    <div className="mt-3 border-t border-slate-700 pt-3">
                        <h4 className="text-xs font-medium text-rose-400 mb-1">
                            Mismatches ({parity.mismatches.length})
                        </h4>
                        <ul className="text-xs text-slate-400 space-y-1">
                            {parity.mismatches.slice(0, 5).map((m, i) => (
                                <li key={i}>
                                    {m.rowId} → {m.field}: "{m.oldValue}" vs "
                                    {m.newValue}"
                                </li>
                            ))}
                            {parity.mismatches.length > 5 && (
                                <li>...and {parity.mismatches.length - 5} more</li>
                            )}
                        </ul>
                    </div>
                )}
            </div>

            {/* Side-by-side grids */}
            <div className="grid grid-cols-2 gap-4">
                <div>
                    <h4 className="text-xs font-medium text-slate-500 mb-2 uppercase tracking-wide">
                        Old Grid ({parity.oldRowCount} rows)
                    </h4>
                    {renderOld()}
                </div>
                <div>
                    <h4 className="text-xs font-medium text-slate-500 mb-2 uppercase tracking-wide">
                        New Grid ({parity.newRowCount} rows)
                    </h4>
                    {renderNew()}
                </div>
            </div>
        </div>
    );
}

export default GridParityHarness;
