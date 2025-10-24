import { useMemo } from "react";
import clsx from "clsx";

import { useMsbCurrent } from "../hooks/useMsbCurrent";
import type { MsbReading } from "../lib/types";

const MAX_STRESS = 100;
const GAUGE_CENTER = 60;
const GAUGE_RADIUS = 52;
const GAUGE_BG_PATH = `M ${GAUGE_CENTER - GAUGE_RADIUS} ${GAUGE_CENTER} A ${GAUGE_RADIUS} ${GAUGE_RADIUS} 0 0 0 ${GAUGE_CENTER + GAUGE_RADIUS} ${GAUGE_CENTER}`;

type ColorTheme = { stroke: string; text: string; dot: string; label: string };

const COLOR_THEME: Record<string, ColorTheme> = {
  green: { stroke: "stroke-emerald-400", text: "text-emerald-300", dot: "bg-emerald-400", label: "Green" },
  yellow: { stroke: "stroke-amber-300", text: "text-amber-200", dot: "bg-amber-300", label: "Yellow" },
  orange: { stroke: "stroke-orange-400", text: "text-orange-300", dot: "bg-orange-400", label: "Orange" },
  red: { stroke: "stroke-rose-500", text: "text-rose-400", dot: "bg-rose-500", label: "Red" },
};

const LEGEND = [
  { key: "green", note: "Normal conditions" },
  { key: "yellow", note: "Caution — monitor hedges" },
  { key: "orange", note: "High stress — prepare actions" },
  { key: "red", note: "Extreme stress — execute hedges" },
];

const clamp01 = (value: number) => (value <= 0 ? 0 : value >= 1 ? 1 : value);
const normalizedStress = (reading?: MsbReading) =>
  reading ? clamp01(reading.msb / MAX_STRESS) : 0;
const describeArc = (fraction: number) => {
  const value = clamp01(fraction);
  if (value <= 0) {
    return `M ${GAUGE_CENTER - GAUGE_RADIUS} ${GAUGE_CENTER}`;
  }
  const angle = Math.PI + value * Math.PI;
  const endX = GAUGE_CENTER + GAUGE_RADIUS * Math.cos(angle);
  const endY = GAUGE_CENTER + GAUGE_RADIUS * Math.sin(angle);
  const largeArc = value > 0.5 ? 1 : 0;
  return `M ${GAUGE_CENTER - GAUGE_RADIUS} ${GAUGE_CENTER} A ${GAUGE_RADIUS} ${GAUGE_RADIUS} 0 ${largeArc} 0 ${endX.toFixed(2)} ${endY.toFixed(2)}`;
};
const formatRatio = (value: number | null | undefined) =>
  value !== null && value !== undefined && Number.isFinite(value)
    ? `${value.toFixed(2)}×`
    : "—";
const formatPercent = (value: number | null | undefined) =>
  value !== null && value !== undefined && Number.isFinite(value)
    ? `${(value * 100).toFixed(2)}%`
    : "—";

export default function MSBCard(): JSX.Element {
  const { data, isLoading, error } = useMsbCurrent();
  const fraction = useMemo(() => normalizedStress(data), [data]);
  const path = useMemo(() => describeArc(fraction), [fraction]);
  const theme = COLOR_THEME[data?.color ?? "green"] ?? COLOR_THEME.green;
  const gaugeText = data ? `Stress: ${data.msb} — ${theme.label}` : "Stress: —";
  const stats = [
    { key: "hy", label: "HY Score", value: data?.hy_score ?? "—" },
    { key: "vix", label: "VIX Score", value: data?.vix_score ?? "—" },
    { key: "term", label: "Term Ratio", value: formatRatio(data?.term_ratio) },
    { key: "cal", label: "Cal Spread %", value: formatPercent(data?.cal_spread_pct) },
  ];

  return (
    <section
      role="region"
      aria-label="Market Stress Barometer"
      className="rounded-3xl border border-slate-800/70 bg-slate-950/60 p-5 shadow-md"
    >
      <div className="flex flex-col gap-6 lg:flex-row">
        <div className="flex flex-col items-center gap-3 lg:w-1/3">
          <svg viewBox="0 0 120 70" className="w-40" aria-hidden="true">
            <path d={GAUGE_BG_PATH} className="fill-none stroke-slate-700" strokeWidth={8} />
            <path
              d={path}
              className={clsx("fill-none", theme.stroke)}
              strokeWidth={8}
              strokeLinecap="round"
            />
          </svg>
          <p aria-live="polite" className={clsx("text-lg font-semibold", theme.text)}>
            {gaugeText}
          </p>
          {isLoading ? <p className="text-sm text-slate-400">Loading…</p> : null}
          {error ? (
            <p className="text-sm text-rose-300" role="alert">
              {error.message}
            </p>
          ) : null}
        </div>
        <div className="flex flex-1 flex-col gap-4">
          <dl className="grid grid-cols-2 gap-3 text-sm text-slate-300 sm:grid-cols-4">
            {stats.map((item) => (
              <div
                key={item.key}
                className="rounded-2xl border border-slate-800/60 bg-slate-900/40 px-3 py-2"
              >
                <dt className="text-[11px] uppercase tracking-wide text-slate-400">
                  {item.label}
                </dt>
                <dd className="mt-1 text-base font-semibold text-slate-100">{item.value}</dd>
              </div>
            ))}
          </dl>
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
              Legend
            </h3>
            <ul className="mt-2 space-y-1 text-sm text-slate-300">
              {LEGEND.map((item) => {
                const itemTheme = COLOR_THEME[item.key] ?? COLOR_THEME.green;
                return (
                  <li key={item.key} className="flex items-center gap-2">
                    <span className={clsx("h-2 w-2 rounded-full", itemTheme.dot)} aria-hidden="true" />
                    <span className="font-semibold text-slate-100">{itemTheme.label}</span>
                    <span className="text-slate-400">{item.note}</span>
                  </li>
                );
              })}
            </ul>
          </div>
          {data?.triggers?.length ? (
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-400">
                Triggers
              </h3>
              <div className="mt-2 flex flex-wrap gap-2">
                {data.triggers.map((trigger) => (
                  <span
                    key={trigger}
                    className="rounded-full border border-slate-700 bg-slate-900/60 px-3 py-1 text-xs font-semibold uppercase tracking-wide text-slate-200"
                  >
                    {trigger}
                  </span>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </section>
  );
}
