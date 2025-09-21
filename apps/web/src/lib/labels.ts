import type { OptionComboLegApi } from "./types";

const MONTH_NAMES = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
];

const OSI_SYMBOL_FRAGMENT = /\d{6,8}[CP]\d{8}/;

function safeParseDate(value: string | null | undefined): Date | null {
  if (!value) {
    return null;
  }
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  const isoCandidate = trimmed.length === 8 && /^\d{8}$/.test(trimmed)
    ? `${trimmed.slice(0, 4)}-${trimmed.slice(4, 6)}-${trimmed.slice(6, 8)}`
    : trimmed;
  const date = new Date(isoCandidate);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return date;
}

function toMonthName(index: number): string | null {
  if (!Number.isFinite(index) || index < 0 || index > 11) {
    return null;
  }
  return MONTH_NAMES[index];
}

function normalizeRight(value: string | null | undefined): string {
  if (!value) {
    return "";
  }
  const upper = value.toUpperCase();
  if (upper.startsWith("C")) {
    return "C";
  }
  if (upper.startsWith("P")) {
    return "P";
  }
  return upper.slice(0, 1);
}

export function normalizeRightCode(value: string | null | undefined): "C" | "P" {
  const normalized = normalizeRight(value);
  return normalized === "P" ? "P" : "C";
}

export function sanitizeLabel(candidate: string | null | undefined, fallback: string): string {
  if (typeof candidate !== "string") {
    return fallback;
  }
  const trimmed = candidate.trim();
  if (!trimmed) {
    return fallback;
  }
  return OSI_SYMBOL_FRAGMENT.test(trimmed) ? fallback : trimmed;
}

export type ParsedOsi = {
  ul: string;
  expiryISO: string;
  side: "C" | "P";
  strike: number;
};

export function parseOsi(symbol: string | null | undefined): ParsedOsi | null {
  if (typeof symbol !== "string") {
    return null;
  }
  const sanitized = symbol.replace(/\s+/g, "").toUpperCase();
  if (!sanitized) {
    return null;
  }

  const STRIKE_LEN = 8;
  const TYPE_LEN = 1;
  const expiryCandidates = [8, 6] as const;

  for (const expiryLen of expiryCandidates) {
    const rootLen = sanitized.length - (expiryLen + TYPE_LEN + STRIKE_LEN);
    if (rootLen < 1 || rootLen > 6) {
      continue;
    }
    const root = sanitized.slice(0, rootLen);
    const expiryDigits = sanitized.slice(rootLen, rootLen + expiryLen);
    const optionType = sanitized.charAt(rootLen + expiryLen);
    const strikeDigits = sanitized.slice(rootLen + expiryLen + TYPE_LEN);

    if (!/^[CP]$/.test(optionType)) {
      continue;
    }
    if (!/^\d+$/.test(expiryDigits) || !/^\d+$/.test(strikeDigits)) {
      continue;
    }

    let year: number;
    let month: number;
    let day: number;

    if (expiryLen === 8) {
      year = Number(expiryDigits.slice(0, 4));
      month = Number(expiryDigits.slice(4, 6));
      day = Number(expiryDigits.slice(6, 8));
    } else {
      const yy = Number(expiryDigits.slice(0, 2));
      year = yy >= 70 ? 1900 + yy : 2000 + yy;
      month = Number(expiryDigits.slice(2, 4));
      day = Number(expiryDigits.slice(4, 6));
    }

    if (!Number.isFinite(year) || !Number.isFinite(month) || !Number.isFinite(day)) {
      continue;
    }
    if (month < 1 || month > 12 || day < 1 || day > 31) {
      continue;
    }

    const strike = Number(strikeDigits) / 1000;
    if (!Number.isFinite(strike)) {
      continue;
    }

    const expiryISO = `${year.toString().padStart(4, "0")}-${month
      .toString()
      .padStart(2, "0")}-${day.toString().padStart(2, "0")}`;
    const normalizedSide: "C" | "P" = optionType === "P" ? "P" : "C";

    return {
      ul: root,
      expiryISO,
      side: normalizedSide,
      strike,
    };
  }

  return null;
}

export function formatExpiryShort(expiry: string): string | null {
  const date = safeParseDate(expiry);
  if (!date) {
    return null;
  }
  const month = toMonthName(date.getUTCMonth());
  if (!month) {
    return null;
  }
  const day = date.getUTCDate();
  const year = date.getUTCFullYear().toString().slice(-2);
  return `${month} ${day} '${year}`;
}

export function formatMonthShort(expiry: string): string | null {
  const date = safeParseDate(expiry);
  if (!date) {
    return null;
  }
  return toMonthName(date.getUTCMonth());
}

export function fmtStrike(value: number | null | undefined): string {
  if (!Number.isFinite(value)) {
    return "?";
  }
  const normalized = Number(value);
  return Number.isInteger(normalized) ? normalized.toString() : normalized.toFixed(2).replace(/(?:\.\d*?)0+$/u, (match) => match.replace(/0+$/u, "").replace(/\.$/u, ""));
}

export function fmtPrice(value: number | null | undefined): string {
  if (!Number.isFinite(value)) {
    return "0.00";
  }
  return Math.abs(Number(value)).toFixed(2);
}

export function fmtSide(netPrice: number | null | undefined): "Credit" | "Debit" | "Even" {
  if (!Number.isFinite(netPrice) || netPrice === 0) {
    return "Even";
  }
  return netPrice! > 0 ? "Credit" : "Debit";
}

export interface FormatLegLabelInput {
  ul: string;
  strike: number;
  side: string;
  expiryISO: string;
}

export function formatLegLabel({ ul, strike, side, expiryISO }: FormatLegLabelInput): string {
  const shortUl = ul.toUpperCase();
  const strikeText = fmtStrike(strike);
  const rightCode = normalizeRight(side);
  const expiryShort = formatExpiryShort(expiryISO) ?? expiryISO;
  return `${shortUl} ${strikeText}${rightCode} • ${expiryShort}`;
}

function normalizeExpiry(expiry: string | null | undefined): string {
  if (typeof expiry !== "string") {
    return "";
  }
  const trimmed = expiry.trim();
  if (!trimmed) {
    return "";
  }
  if (/^\d{8}$/.test(trimmed)) {
    return `${trimmed.slice(0, 4)}-${trimmed.slice(4, 6)}-${trimmed.slice(6, 8)}`;
  }
  if (/^\d{6}$/.test(trimmed)) {
    const yearPrefix = Number(trimmed.slice(0, 2));
    const year = yearPrefix >= 70 ? 1900 + yearPrefix : 2000 + yearPrefix;
    return `${year.toString().padStart(4, "0")}-${trimmed.slice(2, 4)}-${trimmed.slice(4, 6)}`;
  }
  return trimmed;
}

export type FriendlyLegDisplayInput = {
  symbol?: string | null;
  label?: string | null;
  displayLabel?: string | null;
  displayShortUl?: string | null;
  displayExpiryShort?: string | null;
  underlying?: string | null;
  right?: string | null;
  strike?: number | string | null;
  expiry?: string | null;
};

export type FriendlyLegDisplay = {
  label: string;
  tooltip: string;
  shortUnderlying: string;
  expiryShort: string | null;
  expiryISO: string;
  right: "C" | "P";
};

export function buildFriendlyLegDisplay(input: FriendlyLegDisplayInput): FriendlyLegDisplay {
  const parsedSymbol = parseOsi(input.symbol ?? undefined);
  const sanitizedSymbol = typeof input.symbol === "string" ? input.symbol.replace(/\s+/g, "").toUpperCase() : "";

  const rawUnderlying = typeof input.underlying === "string" ? input.underlying.trim() : "";
  const displayShort = typeof input.displayShortUl === "string" ? input.displayShortUl.trim() : "";
  const underlyingFallback = (rawUnderlying || parsedSymbol?.ul || "").toUpperCase();
  const shortUnderlying = displayShort || underlyingFallback || "?";

  let strikeValue: number | null = null;
  if (typeof input.strike === "number" && Number.isFinite(input.strike)) {
    strikeValue = input.strike;
  } else if (typeof input.strike === "string" && input.strike.trim()) {
    const numeric = Number(input.strike);
    if (Number.isFinite(numeric)) {
      strikeValue = numeric;
    }
  }
  const normalizedStrike = strikeValue ?? parsedSymbol?.strike ?? 0;

  const expiryNormalized = normalizeExpiry(input.expiry) || parsedSymbol?.expiryISO || "";
  const right = parsedSymbol?.side ?? normalizeRightCode(input.right);

  const labelCandidate =
    typeof input.displayLabel === "string"
      ? input.displayLabel
      : typeof input.label === "string"
        ? input.label
        : undefined;
  const fallbackLabel = formatLegLabel({
    ul: shortUnderlying,
    strike: normalizedStrike,
    side: right,
    expiryISO: expiryNormalized,
  });
  const label = sanitizeLabel(labelCandidate, fallbackLabel);

  const tooltip = sanitizedSymbol && OSI_SYMBOL_FRAGMENT.test(sanitizedSymbol)
    ? sanitizedSymbol
    : typeof input.symbol === "string" && input.symbol.trim()
      ? input.symbol.trim()
      : fallbackLabel;

  const expiryShort =
    typeof input.displayExpiryShort === "string" && input.displayExpiryShort.trim()
      ? input.displayExpiryShort.trim()
      : formatExpiryShort(expiryNormalized) ?? (expiryNormalized || null);

  return {
    label,
    tooltip,
    shortUnderlying,
    expiryShort,
    expiryISO: expiryNormalized,
    right,
  };
}

export function deriveGroupKey(legs: Array<{ right: string; strike: number; expiry: string }>): string {
  const parts = legs.reduce<(string)[]>((acc, leg) => {
    const expiry = leg.expiry;
    const right = normalizeRight(leg.right);
    const strike = fmtStrike(leg.strike);
    const key = `${right}:${strike}@${expiry}`;
    if (!acc.includes(key)) {
      acc.push(key);
    }
    return acc;
  }, []);
  return parts.sort((a, b) => a.localeCompare(b)).join("|");
}

export function formatComboLabel(
  strategy: string,
  legs: OptionComboLegApi[],
  dte: number,
  netPrice: number,
  underlying: string,
): string {
  const sideLabel = fmtSide(netPrice);
  const priceText = fmtPrice(netPrice);
  const dteText = `${Math.max(0, dte)}d`;
  const upperStrategy = strategy.toUpperCase();
  const upperUl = underlying.toUpperCase();

  const callLegs = legs.filter((leg) => normalizeRight(leg.right as string) === "C");
  const putLegs = legs.filter((leg) => normalizeRight(leg.right as string) === "P");

  if (upperStrategy === "VERTICAL") {
    const strikeSet = callLegs.length === 2 ? callLegs : putLegs;
    if (strikeSet.length === 2) {
      const [low, high] = strikeSet
        .map((leg) => leg.strike)
        .sort((a, b) => a - b);
      const suffix = strikeSet === callLegs ? "C" : "P";
      return `${upperUl} ${fmtStrike(low)}/${fmtStrike(high)}${suffix} • ${dteText} • ${sideLabel} ${priceText}`;
    }
  }

  if (upperStrategy === "IRON_CONDOR" || upperStrategy === "IRON_BUTTERFLY") {
    const callStrikes = callLegs.map((leg) => leg.strike).sort((a, b) => a - b);
    const putStrikes = putLegs.map((leg) => leg.strike).sort((a, b) => a - b);
    const callSpan = callStrikes.length >= 2 ? `${fmtStrike(callStrikes[0])}/${fmtStrike(callStrikes[callStrikes.length - 1])}C` : "C";
    const putSpan = putStrikes.length >= 2 ? `${fmtStrike(putStrikes[0])}/${fmtStrike(putStrikes[putStrikes.length - 1])}P` : "P";
    return `${upperUl} ${putSpan} + ${callSpan} • ${dteText} • ${sideLabel} ${priceText}`;
  }

  const isCalendarLike = upperStrategy.includes("CALENDAR") || upperStrategy.includes("DIAGONAL");
  if (isCalendarLike) {
    const longLeg = legs.find((leg) => (leg.quantity ?? 0) > 0) ?? legs[0];
    const strike = longLeg ? fmtStrike(longLeg.strike) : "?";
    const rightCode = longLeg ? normalizeRight(longLeg.right as string) : "?";

    const monthEntries = legs
      .map((leg) => ({
        month: formatMonthShort(leg.expiry),
        time: safeParseDate(leg.expiry)?.getTime() ?? Number.POSITIVE_INFINITY,
      }))
      .filter((entry) => Boolean(entry.month));
    const distinctMonths = Array.from(
      new Map(monthEntries.map((entry) => [entry.month as string, entry.time])).entries(),
    )
      .sort((a, b) => a[1] - b[1])
      .map(([month]) => month);
    const monthSpan = distinctMonths.length >= 2 ? `${distinctMonths[0]}→${distinctMonths[distinctMonths.length - 1]}` : distinctMonths[0] ?? "";

    return `${upperUl} ${strike}${rightCode} CAL • ${monthSpan} • ${sideLabel} ${priceText}`;
  }

  if (upperStrategy === "STRADDLE") {
    const strike = legs.length ? fmtStrike(legs[0].strike) : "?";
    return `${upperUl} ${strike}C+P • ${dteText}`;
  }

  if (upperStrategy === "STRANGLE") {
    const callStrike = callLegs.length ? fmtStrike(Math.max(...callLegs.map((leg) => leg.strike))) : "?";
    const putStrike = putLegs.length ? fmtStrike(Math.min(...putLegs.map((leg) => leg.strike))) : "?";
    return `${upperUl} ${putStrike}P/${callStrike}C • ${dteText}`;
  }

  return `${upperUl} ${upperStrategy.replace(/_/g, " ")} • ${dteText} • ${sideLabel} ${priceText}`;
}

