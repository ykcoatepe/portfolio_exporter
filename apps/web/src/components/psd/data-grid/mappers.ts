/**
 * PSD Data Grid Type Mappers
 *
 * Transform API types (PSDLeg, etc.) to grid-compatible row types.
 * Ensures stable formatting and row identity.
 */

import type { PSDLeg } from "../../../lib/types";
import { buildFriendlyLegDisplay } from "../../../lib/labels";

/**
 * Row type for single stocks grid
 */
export interface StockRow {
    /** Stable row ID */
    id: string;
    /** Contract ID (preferred for stability) */
    conId: number | null;
    /** Ticker symbol */
    symbol: string;
    /** Position quantity */
    quantity: number;
    /** Mark price */
    markPrice: number | null;
    /** Intraday P&L in dollars */
    dayPnlAmount: number | null;
    /** Intraday P&L in cents (for parity comparison) */
    dayPnlCents: number;
    /** Intraday P&L percentage */
    dayPnlPercent: number | null;
    /** Total/unrealized P&L in dollars */
    totalPnlAmount: number | null;
    /** Total/unrealized P&L percentage */
    totalPnlPercent: number | null;
    /** Position exposure (market value) */
    exposure: number | null;
    /** Price source (last, mid, etc.) */
    priceSource: string | null;
    /** Staleness in seconds */
    stalenessSeconds: number | null;
}

/**
 * Convert dollars to cents (integer for exact comparison)
 */
function toCents(dollars: number | null | undefined): number {
    if (dollars == null || !Number.isFinite(dollars)) return 0;
    return Math.round(dollars * 100);
}

function toNullableNumber(value: unknown): number | null {
    if (value === null || value === undefined) {
        return null;
    }
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
}

function computePercent(amount: number | null, basis: number | null): number | null {
    if (amount === null || basis === null) {
        return null;
    }
    if (!Number.isFinite(amount) || !Number.isFinite(basis)) {
        return null;
    }
    const denominator = Math.abs(basis);
    if (denominator === 0) {
        return null;
    }
    const ratio = amount / denominator;
    return Number.isFinite(ratio) ? ratio * 100 : null;
}

/**
 * Map PSDLeg array to StockRow array
 */
export function mapLegsToStockRows(legs: PSDLeg[]): StockRow[] {
    return legs.map((leg, index) => {
        const markPrice = leg.mark ?? null;
        const quantity = toNullableNumber(leg.qty) ?? 0;
        const dayPnl = toNullableNumber(leg.day_pnl ?? leg.pnl_intraday);
        const totalPnl = toNullableNumber(leg.pnl_unrealized ?? leg.total_pnl);
        const previousClose = toNullableNumber(leg.previous_close);
        const avgCost = toNullableNumber(leg.avg_cost);
        const dayBasis =
            previousClose !== null ? Math.abs(quantity) * previousClose : null;
        const totalBasis =
            avgCost !== null ? Math.abs(quantity) * avgCost : null;
        const dayPercentFromApi = toNullableNumber(
            leg.day_pnl_percent ?? leg.day_pnl_pct,
        );
        const totalPercentFromApi = toNullableNumber(
            leg.pnl_unrealized_percent ?? leg.pnl_unrealized_pct ?? leg.total_pnl_percent,
        );
        const dayPnlPercent = dayPercentFromApi ?? computePercent(dayPnl, dayBasis);
        const totalPnlPercent =
            totalPercentFromApi ?? computePercent(totalPnl, totalBasis);
        const exposure = markPrice != null ? markPrice * Math.abs(quantity) : null;

        return {
            id: `stock:${leg.conId ?? leg.symbol}`,
            conId: leg.conId ?? null,
            symbol: leg.symbol,
            quantity: quantity,
            markPrice: markPrice,
            dayPnlAmount: dayPnl,
            dayPnlCents: toCents(dayPnl),
            dayPnlPercent: dayPnlPercent,
            totalPnlAmount: totalPnl,
            totalPnlPercent: totalPnlPercent,
            exposure: exposure,
            priceSource: leg.price_source ?? null,
            stalenessSeconds: leg.stale_s ?? null,
        };
    });
}

/**
 * Row type for option legs grid
 */
export interface OptionLegRow {
    id: string;
    conId: number | null;
    symbol: string;
    /** Friendly display label (e.g., "TSLA 250C 01/19") */
    label: string;
    /** Short underlying symbol */
    shortUnderlying: string | null;
    quantity: number;
    dte: number | null;
    markPrice: number | null;
    dayPnlAmount: number | null;
    dayPnlCents: number;
    delta: number | null;
    gamma: number | null;
    theta: number | null;
    vega: number | null;
    iv: number | null;
    right: "CALL" | "PUT" | null;
    strike: number | null;
    expiry: string | null;
    priceSource: string | null;
    stalenessSeconds: number | null;
}

/**
 * Calculate DTE from expiry string (YYYYMMDD format)
 */
function calculateDte(expiry: string | null | undefined): number | null {
    if (!expiry) return null;
    const year = parseInt(expiry.slice(0, 4), 10);
    const month = parseInt(expiry.slice(4, 6), 10) - 1;
    const day = parseInt(expiry.slice(6, 8), 10);
    const expiryDate = new Date(year, month, day);
    const now = new Date();
    const diffMs = expiryDate.getTime() - now.getTime();
    return Math.max(0, Math.ceil(diffMs / (1000 * 60 * 60 * 24)));
}

/**
 * Map PSDLeg array to OptionLegRow array
 */
export function mapLegsToOptionLegRows(
    legs: PSDLeg[],
    underlying?: string,
): OptionLegRow[] {
    return legs.map((leg) => {
        const display = buildFriendlyLegDisplay({
            symbol: leg.symbol,
            underlying,
            right: leg.right ?? null,
            strike: leg.strike ?? null,
            expiry: leg.expiry ?? null,
        });
        const symbol = typeof leg.symbol === "string" && leg.symbol.trim()
            ? leg.symbol
            : display.label;
        const fallbackId = [
            symbol,
            leg.right ?? "",
            leg.strike ?? "",
            leg.expiry ?? "",
        ].join("|");
        const idSeed = leg.conId != null ? String(leg.conId) : fallbackId || display.label;

        return {
            id: `leg:${idSeed}`,
            conId: leg.conId ?? null,
            symbol: symbol,
            label: display.label,
            shortUnderlying: display.shortUnderlying ?? null,
            quantity: leg.qty,
            dte: calculateDte(leg.expiry),
            markPrice: leg.mark ?? null,
            dayPnlAmount: leg.pnl_intraday ?? null,
            dayPnlCents: toCents(leg.pnl_intraday),
            delta: leg.greeks?.delta ?? null,
            gamma: leg.greeks?.gamma ?? null,
            theta: leg.greeks?.theta ?? null,
            vega: null, // Not available in PSDGreeks
            iv: null, // Not available in PSDGreeks
            right: leg.right === "CALL" ? "CALL" : leg.right === "PUT" ? "PUT" : null,
            strike: leg.strike ?? null,
            expiry: leg.expiry ?? null,
            priceSource: leg.price_source ?? null,
            stalenessSeconds: leg.stale_s ?? null,
        };
    });
}

/**
 * Parity check utilities
 */
export function sumPnlCents(rows: { dayPnlCents: number }[]): number {
    return rows.reduce((sum, row) => sum + row.dayPnlCents, 0);
}

export function sumDelta(rows: { delta?: number | null }[]): number {
    return rows.reduce((sum, row) => sum + (row.delta ?? 0), 0);
}
