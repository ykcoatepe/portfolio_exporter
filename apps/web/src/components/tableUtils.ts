export function valueTone(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value) || value === 0) {
    return "text-slate-300";
  }
  return value > 0 ? "text-emerald-300" : "text-rose-300";
}

export function stalenessTone(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) {
    return "text-slate-300";
  }
  if (seconds >= 900) {
    return "text-rose-300";
  }
  if (seconds >= 300) {
    return "text-amber-300";
  }
  return "text-emerald-300";
}

export function deriveStalenessSeconds(
  markTime: string | null | undefined,
  now: number,
): number | null {
  if (!markTime) {
    return null;
  }
  const ts = Date.parse(markTime);
  if (Number.isNaN(ts)) {
    return null;
  }
  return Math.max(0, Math.floor((now - ts) / 1000));
}

export function formatSigned(
  value: number | null | undefined,
  fractionDigits = 2,
): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  const fixed = value.toFixed(fractionDigits);
  if (value > 0 && !fixed.startsWith("+")) {
    return `+${fixed}`;
  }
  return fixed;
}
