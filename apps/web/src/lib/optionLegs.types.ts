import type { OptionLegRow } from "./types";

const MARK_SOURCES = new Set(["MID", "LAST", "PREV", "MISSING"]);

export interface OptionLegsSeed {
  legs: OptionLegRow[];
  underlyings: string[];
  expiries: string[];
}

const isString = (value: unknown): value is string => typeof value === "string";
const isNumber = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
const isBoolean = (value: unknown): value is boolean => typeof value === "boolean";

const isNullableNumber = (value: unknown): value is number | null => value === null || isNumber(value);

const isOptionLegRow = (value: unknown): value is OptionLegRow => {
  if (!value || typeof value !== "object") {
    return false;
  }
  const record = value as Record<string, unknown>;
  if (!isString(record.id) || !isString(record.symbol) || !isString(record.labelText)) {
    return false;
  }
  if (!isString(record.shortUnderlying) || !isString(record.underlying) || !isString(record.expiry)) {
    return false;
  }
  if (!isNumber(record.dte) || !isNumber(record.strike) || !isBoolean(record.isOrphan)) {
    return false;
  }
  if (!isBoolean(record.isNearTarget) || !isNumber(record.delta) || !isNumber(record.gamma)) {
    return false;
  }
  if (!isNumber(record.theta) || !isNumber(record.vega)) {
    return false;
  }
  if (!isString(record.right) || (record.right !== "C" && record.right !== "P")) {
    return false;
  }
  if (!isNumber(record.quantity) || !isString(record.markSource) || !MARK_SOURCES.has(record.markSource)) {
    return false;
  }
  if ("comboId" in record && record.comboId !== null && !isString(record.comboId)) {
    return false;
  }
  if ("comboGroupId" in record && record.comboGroupId !== null && !isString(record.comboGroupId)) {
    return false;
  }
  if ("expiryShort" in record && record.expiryShort !== null && !isString(record.expiryShort)) {
    return false;
  }
  const nullableStringFields = [
    record.label,
    record.labelTooltip,
    record.markTime,
    record.nextAction,
  ];
  if (!nullableStringFields.every((field) => field === null || typeof field === "string")) {
    return false;
  }
  const nullableNumberFields = [
    record.markPrice,
    record.iv,
    record.dayPnlAmount,
    record.dayPnlPercent,
    record.totalPnlAmount,
    record.totalPnlPercent,
    record.tpBandLowPct,
    record.tpBandHighPct,
    record.progressPct,
    record.progressPctOfGoal,
    record.progressPctOfR,
    record.progressPctOfMax,
  ];
  if (!nullableNumberFields.every((field) => isNullableNumber(field))) {
    return false;
  }
  const booleanFields = [record.tpHit, record.tpDone, record.slHit];
  if (!booleanFields.every(isBoolean)) {
    return false;
  }
  return true;
};

export function isOptionLegsSeed(value: unknown): value is OptionLegsSeed {
  if (!value || typeof value !== "object") {
    return false;
  }
  const record = value as Partial<OptionLegsSeed>;
  if (!Array.isArray(record.legs) || !record.legs.every(isOptionLegRow)) {
    return false;
  }
  if (!Array.isArray(record.underlyings) || !record.underlyings.every(isString)) {
    return false;
  }
  if (!Array.isArray(record.expiries) || !record.expiries.every(isString)) {
    return false;
  }
  return true;
}
