import { resolveApiBaseUrl } from "./http";
import type { MsbReading } from "./types";

const isFiniteNumber = (value: unknown): value is number =>
  typeof value === "number" && Number.isFinite(value);

const toNumberField = (value: unknown, field: string): number => {
  if (!isFiniteNumber(value)) {
    throw new Error(`Invalid MSB field: ${field}`);
  }
  return value;
};

const toIntegerField = (value: unknown, field: string): number => {
  const numeric = toNumberField(value, field);
  return Math.trunc(numeric);
};

const toOptionalNumber = (value: unknown): number | null => {
  if (value === null || value === undefined) {
    return null;
  }
  return isFiniteNumber(value) ? value : null;
};

const toBooleanField = (value: unknown, field: string): boolean => {
  if (typeof value !== "boolean") {
    throw new Error(`Invalid MSB field: ${field}`);
  }
  return value;
};

const toStringField = (value: unknown, field: string): string => {
  if (typeof value !== "string") {
    throw new Error(`Invalid MSB field: ${field}`);
  }
  const trimmed = value.trim();
  if (trimmed.length === 0) {
    throw new Error(`Invalid MSB field: ${field}`);
  }
  return trimmed;
};

const toOptionalString = (value: unknown): string | null => {
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
};

const toStringArray = (value: unknown): string[] => {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .map((item) => (typeof item === "string" ? item.trim() : ""))
    .filter((item): item is string => item.length > 0);
};

export const resolveMsbBaseUrl = (baseUrl?: string): string => resolveApiBaseUrl(baseUrl);

export const MSB_CURRENT_QUERY_KEY = ["msb.current"] as const;

export const msbHistoryQueryKey = (days: number): ["msb.history", number] => [
  "msb.history",
  days,
];

export const parseMsbReading = (payload: unknown): MsbReading => {
  if (!payload || typeof payload !== "object") {
    throw new Error("Invalid MSB payload");
  }
  const record = payload as Record<string, unknown>;

  const reading: MsbReading = {
    date: toStringField(record.date, "date"),
    hy: toNumberField(record.hy, "hy"),
    vx1: toNumberField(record.vx1, "vx1"),
    vx2: toNumberField(record.vx2, "vx2"),
    z_hy: toOptionalNumber(record.z_hy),
    term_ratio: toOptionalNumber(record.term_ratio),
    cal_spread_pct: toOptionalNumber(record.cal_spread_pct),
    cal_spread_abs: toOptionalNumber(record.cal_spread_abs),
    saturated: toBooleanField(record.saturated, "saturated"),
    hy_score: toIntegerField(record.hy_score, "hy_score"),
    vix_score: toIntegerField(record.vix_score, "vix_score"),
    msb: toIntegerField(record.msb, "msb"),
    color: toStringField(record.color, "color"),
    triggers: toStringArray(record.triggers),
    winsor_clipped_n: toIntegerField(record.winsor_clipped_n, "winsor_clipped_n"),
    cooldown_until: toOptionalString(record.cooldown_until),
  };

  return reading;
};

export const parseMsbHistory = (payload: unknown): MsbReading[] => {
  if (!Array.isArray(payload)) {
    throw new Error("Invalid MSB history payload");
  }
  return payload.map((entry) => parseMsbReading(entry));
};
