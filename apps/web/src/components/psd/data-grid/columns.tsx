/**
 * PSD Data Grid Column Definitions
 *
 * Column configurations for different data types.
 */

import type { ColumnDef } from "@tanstack/react-table";
import type { OptionLegRow as LibOptionLegRow, OptionComboRow, OptionComboGroupRow } from "../../../lib/types";
import type { StockRow, OptionLegRow as PsdOptionLegRow } from "./mappers";
import {
    SymbolCell,
    CurrencyCell,
    PercentCell,
    GreekCell,
    TextCell,
    ProgressCell,
    stalenessTone,
    CellWrapper,
} from "./cells";
import { formatDuration } from "../../../lib/format";

/**
 * Generate stable row ID for StockRow
 */
export function getStockRowId(row: StockRow): string {
    return row.id;
}

/**
 * Generate stable row ID for OptionLegRow
 */
export function getOptionLegRowId(row: LibOptionLegRow): string {
    return `leg:${row.id}`;
}

/**
 * Generate stable row ID for combo or group rows
 * For flattened combos table, we use:
 * - group:{comboGroupId} for group rows
 * - combo:{comboId} for combo rows
 */
export function getComboRowId(row: OptionComboRow | OptionComboGroupRow, isGroup: boolean): string {
    return isGroup ? `group:${row.id}` : `combo:${row.id}`;
}

/**
 * Stock positions table columns
 */
export const stockColumns: ColumnDef<StockRow>[] = [
    {
        id: "symbol",
        accessorKey: "symbol",
        header: "Symbol",
        size: 100,
        meta: {
            align: "left",
            sortable: true,
        },
        cell: ({ row }) => (
            <SymbolCell symbol={row.original.symbol} />
        ),
    },
    {
        id: "quantity",
        accessorKey: "quantity",
        header: "Qty",
        size: 80,
        meta: {
            align: "right",
            numeric: true,
            sortable: true,
        },
        cell: ({ getValue }) => {
            const value = getValue() as number;
            return (
                <TextCell
                    value={String(value)}
                    align="right"
                    className={value >= 0 ? "text-emerald-400" : "text-rose-400"}
                />
            );
        },
    },
    {
        id: "markPrice",
        accessorKey: "markPrice",
        header: "Mark",
        size: 90,
        meta: {
            align: "right",
            numeric: true,
            sortable: true,
        },
        cell: ({ getValue }) => (
            <CurrencyCell value={getValue() as number | null} />
        ),
    },
    {
        id: "dayPnlAmount",
        accessorKey: "dayPnlAmount",
        header: "Day P&L",
        size: 100,
        meta: {
            align: "right",
            numeric: true,
            sortable: true,
        },
        cell: ({ getValue }) => (
            <CurrencyCell value={getValue() as number | null} showSign />
        ),
    },
    {
        id: "dayPnlPercent",
        accessorKey: "dayPnlPercent",
        header: "Day %",
        size: 80,
        meta: {
            align: "right",
            numeric: true,
            sortable: true,
        },
        cell: ({ getValue }) => (
            <PercentCell value={getValue() as number | null} />
        ),
    },
    {
        id: "totalPnlAmount",
        accessorKey: "totalPnlAmount",
        header: "Total P&L",
        size: 100,
        meta: {
            align: "right",
            numeric: true,
            sortable: true,
        },
        cell: ({ getValue }) => (
            <CurrencyCell value={getValue() as number | null} showSign />
        ),
    },
    {
        id: "totalPnlPercent",
        accessorKey: "totalPnlPercent",
        header: "Total %",
        size: 80,
        meta: {
            align: "right",
            numeric: true,
            sortable: true,
        },
        cell: ({ getValue }) => (
            <PercentCell value={getValue() as number | null} />
        ),
    },
    {
        id: "exposure",
        accessorKey: "exposure",
        header: "Exposure",
        size: 100,
        meta: {
            align: "right",
            numeric: true,
            sortable: true,
        },
        cell: ({ getValue }) => (
            <CurrencyCell value={getValue() as number | undefined} />
        ),
    },
    {
        id: "priceSource",
        accessorKey: "priceSource",
        header: "Source",
        size: 80,
        sortingFn: "alphanumeric",
        meta: {
            align: "left",
            sortable: true,
        },
        cell: ({ getValue }) => (
            <TextCell value={getValue() as string | null} />
        ),
    },
    {
        id: "staleness",
        accessorKey: "stalenessSeconds",
        header: "Staleness",
        size: 90,
        sortingFn: "basic",
        sortUndefined: "last",
        meta: {
            align: "right",
            numeric: true,
            sortable: true,
        },
        cell: ({ getValue }) => {
            const seconds = getValue() as number | null;
            return (
                <CellWrapper align="right" className={stalenessTone(seconds)}>
                    {formatDuration(seconds)}
                </CellWrapper>
            );
        },
    },
];

/**
 * Option legs table columns
 */
export const optionLegColumns: ColumnDef<LibOptionLegRow>[] = [
    {
        id: "symbol",
        accessorKey: "symbol",
        header: "Contract",
        size: 180,
        meta: {
            align: "left",
            sortable: true,
        },
        cell: ({ row }) => (
            <SymbolCell
                symbol={row.original.label}
                subtitle={row.original.shortUnderlying}
            />
        ),
    },
    {
        id: "quantity",
        accessorKey: "quantity",
        header: "Qty",
        size: 60,
        meta: {
            align: "right",
            numeric: true,
        },
        cell: ({ getValue }) => {
            const value = getValue() as number;
            return (
                <TextCell
                    value={String(value)}
                    align="right"
                    className={value >= 0 ? "text-emerald-400" : "text-rose-400"}
                />
            );
        },
    },
    {
        id: "dte",
        accessorKey: "dte",
        header: "DTE",
        size: 60,
        meta: {
            align: "right",
            numeric: true,
            sortable: true,
        },
        cell: ({ getValue }) => {
            const dte = getValue() as number;
            const tone = dte <= 7 ? "text-rose-400" : dte <= 21 ? "text-amber-400" : "text-slate-400";
            return <TextCell value={String(dte)} align="right" className={tone} />;
        },
    },
    {
        id: "markPrice",
        accessorKey: "markPrice",
        header: "Mark",
        size: 80,
        meta: {
            align: "right",
            numeric: true,
        },
        cell: ({ getValue }) => (
            <CurrencyCell value={getValue() as number | null} />
        ),
    },
    {
        id: "delta",
        accessorKey: "delta",
        header: "Δ",
        size: 70,
        meta: {
            align: "right",
            numeric: true,
            headerTooltip: "Delta",
        },
        cell: ({ getValue }) => <GreekCell value={getValue() as number | null} />,
    },
    {
        id: "gamma",
        accessorKey: "gamma",
        header: "Γ",
        size: 70,
        meta: {
            align: "right",
            numeric: true,
            headerTooltip: "Gamma",
        },
        cell: ({ getValue }) => <GreekCell value={getValue() as number | null} />,
    },
    {
        id: "theta",
        accessorKey: "theta",
        header: "Θ",
        size: 70,
        meta: {
            align: "right",
            numeric: true,
            headerTooltip: "Theta",
        },
        cell: ({ getValue }) => <GreekCell value={getValue() as number | null} />,
    },
    {
        id: "vega",
        accessorKey: "vega",
        header: "V",
        size: 70,
        meta: {
            align: "right",
            numeric: true,
            headerTooltip: "Vega",
        },
        cell: ({ getValue }) => <GreekCell value={getValue() as number | null} />,
    },
    {
        id: "iv",
        accessorKey: "iv",
        header: "IV",
        size: 70,
        meta: {
            align: "right",
            numeric: true,
            sortable: true,
        },
        cell: ({ getValue }) => {
            const iv = getValue() as number | null;
            return <PercentCell value={iv != null ? iv * 100 : null} showSign={false} />;
        },
    },
    {
        id: "progressPct",
        accessorKey: "progressPct",
        header: "Progress",
        size: 100,
        meta: {
            align: "left",
        },
        cell: ({ getValue }) => {
            const value = getValue() as number | null;
            return <ProgressCell value={value != null ? value * 100 : null} />;
        },
    },
];

/**
 * PSD option legs table columns (for positions_view)
 */
export const psdOptionLegColumns: ColumnDef<PsdOptionLegRow>[] = [
    {
        id: "symbol",
        accessorKey: "label",
        header: "Symbol",
        size: 200,
        meta: {
            align: "left",
            sortable: true,
        },
        cell: ({ row }) => (
            <SymbolCell symbol={row.original.label} />
        ),
    },
    {
        id: "quantity",
        accessorKey: "quantity",
        header: "Qty",
        size: 70,
        meta: {
            align: "right",
            numeric: true,
            sortable: true,
        },
        cell: ({ getValue }) => {
            const value = getValue() as number;
            return (
                <TextCell
                    value={String(value)}
                    align="right"
                    className={value >= 0 ? "text-emerald-400" : "text-rose-400"}
                />
            );
        },
    },
    {
        id: "markPrice",
        accessorKey: "markPrice",
        header: "Mark",
        size: 90,
        meta: {
            align: "right",
            numeric: true,
            sortable: true,
        },
        cell: ({ getValue }) => (
            <CurrencyCell value={getValue() as number | null} />
        ),
    },
    {
        id: "dayPnlAmount",
        accessorKey: "dayPnlAmount",
        header: "Day P&L",
        size: 110,
        meta: {
            align: "right",
            numeric: true,
            sortable: true,
        },
        cell: ({ getValue }) => (
            <CurrencyCell value={getValue() as number | null} showSign />
        ),
    },
    {
        id: "delta",
        accessorKey: "delta",
        header: "Δ",
        size: 70,
        meta: {
            align: "right",
            numeric: true,
            sortable: true,
            headerTooltip: "Delta",
        },
        cell: ({ getValue }) => <GreekCell value={getValue() as number | null} />,
    },
    {
        id: "gamma",
        accessorKey: "gamma",
        header: "Γ",
        size: 70,
        meta: {
            align: "right",
            numeric: true,
            sortable: true,
            headerTooltip: "Gamma",
        },
        cell: ({ getValue }) => <GreekCell value={getValue() as number | null} />,
    },
    {
        id: "theta",
        accessorKey: "theta",
        header: "Θ",
        size: 70,
        meta: {
            align: "right",
            numeric: true,
            sortable: true,
            headerTooltip: "Theta",
        },
        cell: ({ getValue }) => <GreekCell value={getValue() as number | null} />,
    },
    {
        id: "priceSource",
        accessorKey: "priceSource",
        header: "Source",
        size: 90,
        sortingFn: "alphanumeric",
        meta: {
            align: "left",
            sortable: true,
        },
        cell: ({ getValue }) => {
            const value = getValue() as string | null;
            return <TextCell value={value ? value.toUpperCase() : value} />;
        },
    },
    {
        id: "staleness",
        accessorKey: "stalenessSeconds",
        header: "Staleness",
        size: 90,
        sortingFn: "basic",
        sortUndefined: "last",
        meta: {
            align: "right",
            numeric: true,
            sortable: true,
        },
        cell: ({ getValue }) => {
            const seconds = getValue() as number | null;
            return (
                <CellWrapper align="right" className={stalenessTone(seconds)}>
                    {formatDuration(seconds)}
                </CellWrapper>
            );
        },
    },
];

export default {
    stockColumns,
    optionLegColumns,
    psdOptionLegColumns,
    getStockRowId,
    getOptionLegRowId,
    getComboRowId,
};
