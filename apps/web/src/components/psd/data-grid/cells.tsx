/**
 * PSD Data Grid Cell Renderers
 *
 * Reusable cell components for common data types.
 * Each renderer follows the terminal-first design system.
 */

import type { ReactNode } from "react";
import clsx from "clsx";

/**
 * Format a number with optional precision and optional sign
 */
export function formatNumber(
    value: number | null | undefined,
    options: {
        precision?: number;
        showSign?: boolean;
        suffix?: string;
        prefix?: string;
    } = {},
): string {
    if (value == null) return "—";
    const { precision = 2, showSign = false, suffix = "", prefix = "" } = options;
    const formatted = value.toFixed(precision);
    const sign = showSign && value > 0 ? "+" : "";
    return `${prefix}${sign}${formatted}${suffix}`;
}

/**
 * Get color class for positive/negative values
 */
export function valueTone(value: number | null | undefined): string {
    if (value == null) return "text-slate-500";
    if (value > 0) return "text-emerald-400";
    if (value < 0) return "text-rose-400";
    return "text-slate-400";
}

/**
 * Get staleness color based on seconds
 */
export function stalenessTone(seconds: number | null): string {
    if (seconds == null) return "text-slate-500";
    if (seconds < 60) return "text-slate-400";
    if (seconds < 300) return "text-amber-400";
    return "text-rose-400";
}

/**
 * Format currency value
 */
export function formatCurrency(
    value: number | null | undefined,
    options: { showSign?: boolean; precision?: number } = {},
): string {
    return formatNumber(value, { prefix: "$", ...options });
}

/**
 * Format percentage value
 */
export function formatPercent(
    value: number | null | undefined,
    options: { showSign?: boolean; precision?: number } = {},
): string {
    return formatNumber(value, { suffix: "%", ...options });
}

/**
 * Format Greek value (delta, gamma, theta, vega)
 */
export function formatGreek(value: number | null | undefined): string {
    if (value == null) return "—";
    return value.toFixed(3);
}

/**
 * Cell wrapper component with consistent styling
 */
interface CellWrapperProps {
    children: ReactNode;
    align?: "left" | "center" | "right";
    className?: string;
    title?: string;
}

export function CellWrapper({
    children,
    align = "left",
    className,
    title,
}: CellWrapperProps): JSX.Element {
    return (
        <div
            className={clsx(
                "truncate px-3 py-2 text-sm font-mono tabular-nums",
                align === "right" && "text-right",
                align === "center" && "text-center",
                className,
            )}
            title={title}
        >
            {children}
        </div>
    );
}

/**
 * Numeric cell with value-based coloring
 */
interface NumericCellProps {
    value: number | null | undefined;
    format?: (value: number | null | undefined) => string;
    showTone?: boolean;
    align?: "left" | "center" | "right";
}

export function NumericCell({
    value,
    format = (v) => formatNumber(v),
    showTone = true,
    align = "right",
}: NumericCellProps): JSX.Element {
    const toneClass = showTone ? valueTone(value) : "text-slate-300";
    return (
        <CellWrapper align={align} className={toneClass}>
            {format(value)}
        </CellWrapper>
    );
}

/**
 * Currency cell (automatically right-aligned with $ prefix)
 */
interface CurrencyCellProps {
    value: number | null | undefined;
    showSign?: boolean;
    precision?: number;
}

export function CurrencyCell({
    value,
    showSign = false,
    precision = 2,
}: CurrencyCellProps): JSX.Element {
    return (
        <NumericCell
            value={value}
            format={(v) => formatCurrency(v, { showSign, precision })}
            showTone={true}
            align="right"
        />
    );
}

/**
 * Percentage cell
 */
interface PercentCellProps {
    value: number | null | undefined;
    showSign?: boolean;
    precision?: number;
}

export function PercentCell({
    value,
    showSign = true,
    precision = 2,
}: PercentCellProps): JSX.Element {
    return (
        <NumericCell
            value={value}
            format={(v) => formatPercent(v, { showSign, precision })}
            showTone={true}
            align="right"
        />
    );
}

/**
 * Greek cell (delta, gamma, theta, vega)
 */
interface GreekCellProps {
    value: number | null | undefined;
}

export function GreekCell({ value }: GreekCellProps): JSX.Element {
    return (
        <NumericCell
            value={value}
            format={formatGreek}
            showTone={true}
            align="right"
        />
    );
}

/**
 * Symbol/ticker cell (left-aligned, bold)
 */
interface SymbolCellProps {
    symbol: string;
    subtitle?: string;
}

export function SymbolCell({ symbol, subtitle }: SymbolCellProps): JSX.Element {
    return (
        <CellWrapper align="left" className="text-slate-100 font-semibold">
            <div>{symbol}</div>
            {subtitle && (
                <div className="text-xs text-slate-500 font-normal">{subtitle}</div>
            )}
        </CellWrapper>
    );
}

/**
 * Text cell (generic string value)
 */
interface TextCellProps {
    value: string | null | undefined;
    align?: "left" | "center" | "right";
    className?: string;
}

export function TextCell({
    value,
    align = "left",
    className,
}: TextCellProps): JSX.Element {
    return (
        <CellWrapper align={align} className={clsx("text-slate-300", className)}>
            {value ?? "—"}
        </CellWrapper>
    );
}

/**
 * Badge cell (category/status indicator)
 */
interface BadgeCellProps {
    label: string;
    variant: "default" | "success" | "warning" | "danger" | "info";
}

const BADGE_VARIANTS = {
    default: "border-slate-700 bg-slate-800 text-slate-300",
    success: "border-emerald-500/40 bg-emerald-500/20 text-emerald-200",
    warning: "border-amber-500/40 bg-amber-500/20 text-amber-200",
    danger: "border-rose-500/40 bg-rose-500/20 text-rose-200",
    info: "border-sky-500/40 bg-sky-500/20 text-sky-200",
};

export function BadgeCell({ label, variant }: BadgeCellProps): JSX.Element {
    return (
        <CellWrapper align="center">
            <span
                className={clsx(
                    "inline-block rounded-full border px-2 py-0.5 text-xs font-medium uppercase",
                    BADGE_VARIANTS[variant],
                )}
            >
                {label}
            </span>
        </CellWrapper>
    );
}

/**
 * Progress bar cell
 */
interface ProgressCellProps {
    value: number | null | undefined;
    max?: number;
    showLabel?: boolean;
}

export function ProgressCell({
    value,
    max = 100,
    showLabel = true,
}: ProgressCellProps): JSX.Element {
    const percent = value != null ? Math.min(100, Math.max(0, (value / max) * 100)) : 0;
    const toneClass = percent >= 100 ? "bg-emerald-500" : percent >= 50 ? "bg-sky-500" : "bg-slate-600";

    return (
        <CellWrapper align="left" className="flex items-center gap-2">
            <div className="flex-1 h-1.5 rounded-full bg-slate-800 overflow-hidden">
                <div
                    className={clsx("h-full rounded-full transition-all", toneClass)}
                    style={{ width: `${percent}%` }}
                />
            </div>
            {showLabel && (
                <span className="text-xs text-slate-500 w-10 text-right">
                    {value != null ? `${Math.round(percent)}%` : "—"}
                </span>
            )}
        </CellWrapper>
    );
}

/**
 * Expand/collapse toggle cell
 */
interface ExpandCellProps {
    isExpanded: boolean;
    onToggle: () => void;
}

export function ExpandCell({ isExpanded, onToggle }: ExpandCellProps): JSX.Element {
    return (
        <CellWrapper align="center" className="px-1">
            <button
                type="button"
                onClick={(e) => {
                    e.stopPropagation();
                    onToggle();
                }}
                className={clsx(
                    "flex h-5 w-5 items-center justify-center rounded text-slate-500",
                    "hover:bg-slate-800 hover:text-slate-300",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/60",
                )}
                aria-label={isExpanded ? "Collapse row" : "Expand row"}
            >
                <svg
                    className={clsx(
                        "h-3 w-3 transition-transform",
                        isExpanded && "rotate-90",
                    )}
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                >
                    <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M9 5l7 7-7 7"
                    />
                </svg>
            </button>
        </CellWrapper>
    );
}

export default {
    formatNumber,
    formatCurrency,
    formatPercent,
    formatGreek,
    valueTone,
    stalenessTone,
    CellWrapper,
    NumericCell,
    CurrencyCell,
    PercentCell,
    GreekCell,
    SymbolCell,
    TextCell,
    BadgeCell,
    ProgressCell,
    ExpandCell,
};
