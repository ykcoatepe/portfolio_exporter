/**
 * PSD Data Grid Type Mappers
 *
 * Transform API types (PSDLeg, etc.) to grid-compatible row types.
 * Ensures stable formatting and row identity.
 */

import type { PSDLeg, PSDPositionsView, PSDCombo } from "../../../lib/types";

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

/**
 * Map PSDLeg array to StockRow array
 */
export function mapLegsToStockRows(legs: PSDLeg[]): StockRow[] {
    return legs.map((leg, index) => {
        const markPrice = leg.mark ?? null;
        const quantity = leg.qty;
        const dayPnl = leg.pnl_intraday ?? null;
        const totalPnl = leg.pnl_unrealized ?? leg.total_pnl ?? null;
        const exposure = markPrice != null ? markPrice * Math.abs(quantity) : null;

        return {
            id: `stock:${leg.conId ?? leg.symbol}`,
            conId: leg.conId ?? null,
            symbol: leg.symbol,
            quantity: quantity,
            markPrice: markPrice,
            dayPnlAmount: dayPnl,
            dayPnlCents: toCents(dayPnl),
            dayPnlPercent: leg.day_pnl_percent ?? leg.day_pnl_pct ?? null,
            totalPnlAmount: totalPnl,
            totalPnlPercent: leg.pnl_unrealized_percent ?? leg.pnl_unrealized_pct ?? leg.total_pnl_percent ?? null,
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
 * Build friendly option label (e.g., "TSLA 250C 01/19")
 */
function buildOptionLabel(leg: PSDLeg, underlying?: string): string {
    const ticker = underlying ?? leg.symbol.split(" ")[0] ?? leg.symbol;
    const strike = leg.strike != null ? leg.strike.toString() : "";
    const right = leg.right === "CALL" ? "C" : leg.right === "PUT" ? "P" : "";
    const expiry = leg.expiry
        ? `${leg.expiry.slice(4, 6)}/${leg.expiry.slice(6, 8)}`
        : "";

    if (strike && right && expiry) {
        return `${ticker} ${strike}${right} ${expiry}`;
    }
    return leg.symbol;
}

/**
 * Map PSDLeg array to OptionLegRow array
 */
export function mapLegsToOptionLegRows(
    legs: PSDLeg[],
    underlying?: string,
): OptionLegRow[] {
    return legs.map((leg) => ({
        id: `leg:${leg.conId ?? leg.symbol}`,
        conId: leg.conId ?? null,
        symbol: leg.symbol,
        label: buildOptionLabel(leg, underlying),
        shortUnderlying: underlying ?? null,
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
    }));
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
