/**
 * PSD Grid Filter Functions
 *
 * Custom filter implementations for TanStack Table.
 * Semantics:
 * - String: case-insensitive, trim whitespace, nulls = non-match
 * - Numeric: NaN/null = non-match
 *
 * Numeric filters expect a structured, typed value (no parsing inside filter fn).
 */

import type { FilterFn } from "@tanstack/react-table";

export type PsdStringFilterValue = string;

export type PsdNumberFilterValue =
    | { op: "gt" | "gte" | "lt" | "lte" | "eq"; a: number }
    | { op: "between"; a: number; b: number };

/**
 * Normalize a string value for filtering:
 * - Trim whitespace
 * - Lowercase for case-insensitive comparison
 * - Returns null for non-string/empty values
 */
function normalizeString(value: unknown): string | null {
    if (typeof value !== "string") return null;
    const trimmed = value.trim().toLowerCase();
    return trimmed.length > 0 ? trimmed : null;
}

/**
 * Normalize a numeric value for filtering:
 * - Returns finite numbers only
 * - Returns null for NaN, Infinity, non-numbers
 */
function normalizeNumber(value: unknown): number | null {
    if (typeof value === "number" && Number.isFinite(value)) {
        return value;
    }
    if (typeof value === "string") {
        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : null;
    }
    return null;
}

export function isPsdNumberFilterValue(value: unknown): value is PsdNumberFilterValue {
    if (!value || typeof value !== "object") return false;
    const candidate = value as PsdNumberFilterValue;
    if (candidate.op === "between") {
        return Number.isFinite(candidate.a) && Number.isFinite(candidate.b);
    }
    if (
        candidate.op === "gt" ||
        candidate.op === "gte" ||
        candidate.op === "lt" ||
        candidate.op === "lte" ||
        candidate.op === "eq"
    ) {
        return Number.isFinite(candidate.a);
    }
    return false;
}

export function matchesStringFilter(
    value: unknown,
    filterValue: PsdStringFilterValue | null | undefined,
): boolean {
    const normalized = normalizeString(value);
    const normalizedFilter = normalizeString(filterValue);

    // Empty filter = match all
    if (normalizedFilter === null) return true;

    // Null cell value = non-match
    if (normalized === null) return false;

    // Substring match (contains)
    return normalized.includes(normalizedFilter);
}

export function matchesNumberFilter(
    value: unknown,
    filterValue: PsdNumberFilterValue | null | undefined,
): boolean {
    if (!filterValue || !isPsdNumberFilterValue(filterValue)) return true;
    const normalized = normalizeNumber(value);
    if (normalized === null) return false;

    if (filterValue.op === "between") {
        const min = Math.min(filterValue.a, filterValue.b);
        const max = Math.max(filterValue.a, filterValue.b);
        return normalized >= min && normalized <= max;
    }

    if (filterValue.op === "gt") {
        return normalized > filterValue.a;
    }
    if (filterValue.op === "gte") {
        return normalized >= filterValue.a;
    }
    if (filterValue.op === "lt") {
        return normalized < filterValue.a;
    }
    if (filterValue.op === "lte") {
        return normalized <= filterValue.a;
    }
    return normalized === filterValue.a;
}

export function formatNumberFilterValue(
    value: PsdNumberFilterValue | null | undefined,
): string {
    if (!value) return "";
    if (value.op === "between") {
        return `${value.a}-${value.b}`;
    }
    if (value.op === "gt") {
        return `> ${value.a}`;
    }
    if (value.op === "gte") {
        return `>= ${value.a}`;
    }
    if (value.op === "lt") {
        return `< ${value.a}`;
    }
    if (value.op === "lte") {
        return `<= ${value.a}`;
    }
    return `${value.a}`;
}

export function parseNumberFilterInput(input: string): PsdNumberFilterValue | null {
    const trimmed = input.trim();
    if (!trimmed) return null;

    const rangeMatch = trimmed.match(/^(-?\d+(?:\.\d+)?)\s*-\s*(-?\d+(?:\.\d+)?)$/);
    if (rangeMatch) {
        const a = Number(rangeMatch[1]);
        const b = Number(rangeMatch[2]);
        if (Number.isFinite(a) && Number.isFinite(b)) {
            return { op: "between", a, b };
        }
        return null;
    }

    const opMatch = trimmed.match(/^(>=|<=|=|>|<)\s*(-?\d+(?:\.\d+)?)$/);
    if (opMatch) {
        const opToken = opMatch[1];
        const value = Number(opMatch[2]);
        if (!Number.isFinite(value)) return null;
        if (opToken === ">") return { op: "gt", a: value };
        if (opToken === ">=") return { op: "gte", a: value };
        if (opToken === "<") return { op: "lt", a: value };
        if (opToken === "<=") return { op: "lte", a: value };
        return { op: "eq", a: value };
    }

    const parsed = Number(trimmed);
    if (!Number.isFinite(parsed)) return null;
    return { op: "eq", a: parsed };
}

/**
 * String filter function for PSD grid columns.
 * Case-insensitive, trims whitespace, nulls = non-match.
 */
export const psdFilterString: FilterFn<unknown> = (row, columnId, filterValue) => {
    const cellValue = row.getValue(columnId);
    return matchesStringFilter(cellValue, filterValue as PsdStringFilterValue | null | undefined);
};

// For TanStack Table's FilterFn registry
psdFilterString.autoRemove = (val: unknown) =>
    val === undefined || val === null || val === "";

/**
 * Numeric filter function for PSD grid columns.
 * Supports exact match, range, or comparison using structured filter values.
 * NaN/null = non-match.
 */
export const psdFilterNumber: FilterFn<unknown> = (row, columnId, filterValue) => {
    const cellValue = row.getValue(columnId);
    return matchesNumberFilter(cellValue, filterValue as PsdNumberFilterValue | null | undefined);
};

psdFilterNumber.autoRemove = (val: unknown) => val == null || !isPsdNumberFilterValue(val);

/**
 * Map of filter function names to implementations.
 * Register with TanStack Table's filterFns option.
 */
export const psdFilterFns = {
    psdString: psdFilterString,
    psdNumber: psdFilterNumber,
};

export type PsdFilterFnKey = keyof typeof psdFilterFns;
