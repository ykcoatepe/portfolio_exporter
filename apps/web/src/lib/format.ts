type MoneyFormatOptions = {
  currency?: string;
  signDisplay?: "auto" | "always" | "never" | "exceptZero";
  minimumFractionDigits?: number;
  maximumFractionDigits?: number;
};

const moneyFormatters = new Map<string, Intl.NumberFormat>();
const percentFormatters = new Map<string, Intl.NumberFormat>();

const DEFAULT_CURRENCY = "USD";

function getMoneyFormatter(options: MoneyFormatOptions): Intl.NumberFormat {
  const currency = options.currency ?? DEFAULT_CURRENCY;
  const signDisplay = options.signDisplay ?? "auto";
  const minimumFractionDigits = options.minimumFractionDigits ?? 2;
  const maximumFractionDigits = options.maximumFractionDigits ?? 2;
  const key = [currency, signDisplay, minimumFractionDigits, maximumFractionDigits].join("|");
  let formatter = moneyFormatters.get(key);
  if (!formatter) {
    formatter = new Intl.NumberFormat("en-US", {
      style: "currency",
      currency,
      signDisplay,
      minimumFractionDigits,
      maximumFractionDigits,
    });
    moneyFormatters.set(key, formatter);
  }
  return formatter;
}

export function formatMoney(
  value: number | null | undefined,
  options: MoneyFormatOptions = {},
): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  const formatter = getMoneyFormatter(options);
  return formatter.format(value);
}

type PercentFormatOptions = {
  alreadyScaled?: boolean;
  signDisplay?: "auto" | "always" | "never" | "exceptZero";
  minimumFractionDigits?: number;
  maximumFractionDigits?: number;
};

function getPercentFormatter(options: PercentFormatOptions): Intl.NumberFormat {
  const signDisplay = options.signDisplay ?? "auto";
  const minimumFractionDigits = options.minimumFractionDigits ?? 2;
  const maximumFractionDigits = options.maximumFractionDigits ?? 2;
  const key = [signDisplay, minimumFractionDigits, maximumFractionDigits].join("|");
  let formatter = percentFormatters.get(key);
  if (!formatter) {
    formatter = new Intl.NumberFormat("en-US", {
      style: "percent",
      signDisplay,
      minimumFractionDigits,
      maximumFractionDigits,
    });
    percentFormatters.set(key, formatter);
  }
  return formatter;
}

export function formatPercent(
  value: number | null | undefined,
  options: PercentFormatOptions = {},
): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  const scaled = options.alreadyScaled ? value : value / 100;
  const formatter = getPercentFormatter(options);
  return formatter.format(scaled);
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) {
    return "—";
  }
  const absSeconds = Math.abs(seconds);
  const totalSeconds = Math.floor(absSeconds);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const secs = totalSeconds % 60;
  const sign = seconds < 0 ? "-" : "";
  if (hours > 0) {
    return `${sign}${hours}:${minutes.toString().padStart(2, "0")}:${secs
      .toString()
      .padStart(2, "0")}`;
  }
  return `${sign}${minutes.toString().padStart(2, "0")}:${secs
    .toString()
    .padStart(2, "0")}`;
}
